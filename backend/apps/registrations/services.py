import hashlib
import json

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework.exceptions import APIException, ValidationError
from django.db.models import Q, Sum
from django.utils import timezone

from apps.events.models import Event, TicketTier
from apps.tickets.models import Ticket
from .models import (
    InventoryReservation,
    Registration,
    RegistrationIdempotency,
)


class RegistrationConflict(APIException):
    status_code = 409
    default_detail = "The selected ticket offer is no longer available."
    default_code = "REGISTRATION_CONFLICT"


class IdempotencyConflict(APIException):
    status_code = 409
    default_detail = "This idempotency key was already used for a different request."
    default_code = "IDEMPOTENCY_CONFLICT"


@transaction.atomic
def create_registration(
    *,
    event_id,
    tier_id,
    buyer,
    source,
    created_by=None,
    attendee_names=None,
    exclude_payment_intent_id=None,
):
    try:
        event = Event.objects.select_for_update().get(pk=event_id)
    except Event.DoesNotExist as error:
        raise RegistrationConflict("The event is unavailable.") from error

    if event.status != Event.Status.OPEN or not event.registration_open:
        raise RegistrationConflict("Registration is not currently open.")

    try:
        tier = TicketTier.objects.select_for_update().get(pk=tier_id, event=event)
    except TicketTier.DoesNotExist as error:
        raise RegistrationConflict("The selected ticket offer is unavailable.") from error

    if not tier.is_available and exclude_payment_intent_id is None:
        raise RegistrationConflict("The selected ticket offer is unavailable.")

    names = attendee_names or [buyer["name"]]
    if len(names) != tier.admission_count:
        raise ValidationError({
            "attendee_names": f"Enter a name for each of the {tier.admission_count} attendees."
        })
    names = [name.strip() for name in names]
    if any(not name for name in names):
        raise ValidationError({"attendee_names": "Every attendee name is required."})

    active_count = Ticket.objects.filter(registration__event=event).exclude(
        status=Ticket.Status.CANCELLED
    ).count()
    from apps.payments.models import PaymentIntent

    reservations = PaymentIntent.objects.filter(
        event=event,
        registration__isnull=True,
    ).filter(
        Q(
            status=PaymentIntent.Status.PENDING,
            expires_at__gt=timezone.now(),
        )
        | Q(status=PaymentIntent.Status.REVIEW_REQUIRED)
    )
    if exclude_payment_intent_id is not None:
        reservations = reservations.exclude(pk=exclude_payment_intent_id)
    reserved_count = reservations.aggregate(
        total=Sum("ticket_tier__admission_count")
    )["total"] or 0
    if active_count + reserved_count + tier.admission_count > event.capacity:
        raise RegistrationConflict("Not enough event capacity remains for this ticket offer.")

    existing_reservations = InventoryReservation.objects.filter(
        event=event,
        status=InventoryReservation.Status.RESERVED,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
    reserved_inventory = existing_reservations.aggregate(
        total=Sum("units_reserved")
    )["total"] or 0
    if active_count + reserved_count + reserved_inventory + tier.admission_count > event.capacity:
        raise RegistrationConflict("Not enough event capacity remains for this ticket offer.")

    registration = Registration.objects.create(
        event=event,
        ticket_tier=tier,
        buyer_name=buyer["name"].strip(),
        buyer_email=buyer["email"].strip().lower(),
        buyer_phone=buyer["phone"],
        buyer_organization=buyer.get("organization", "").strip(),
        buyer_job_title=buyer.get("job_title", "").strip(),
        source=source,
        status=Registration.Status.TICKET_ISSUED,
        created_by=created_by,
    )
    tickets = issue_registration_tickets(
        registration=registration,
        attendee_names=names,
    )
    from apps.audit.models import AuditLog

    AuditLog.objects.create(
        actor=created_by,
        action="REGISTRATION_CREATED",
        resource_type="registration",
        resource_id=str(registration.id),
        metadata={"source": source, "ticket_count": len(tickets)},
    )
    return registration, tickets


def issue_registration_tickets(*, registration, attendee_names):
    existing_tickets = list(registration.tickets.order_by("ticket_code"))
    if existing_tickets:
        if len(existing_tickets) != registration.ticket_tier.admission_count:
            raise RegistrationConflict(
                "Existing admission tickets do not match the reserved ticket quantity."
            )
        return existing_tickets

    names = [name.strip() for name in attendee_names]
    if len(names) != registration.ticket_tier.admission_count or any(not name for name in names):
        raise ValidationError(
            {
                "attendee_names": (
                    f"Enter a name for each of the "
                    f"{registration.ticket_tier.admission_count} attendees."
                )
            }
        )
    tickets = [
        Ticket(
            registration=registration,
            ticket_code=f"{registration.registration_code}-T{index:02d}",
            attendee_name=attendee_name,
        )
        for index, attendee_name in enumerate(names, start=1)
    ]
    Ticket.objects.bulk_create(tickets)
    tickets = list(registration.tickets.order_by("ticket_code"))
    from apps.payments.delivery import ensure_ticket_deliveries

    ensure_ticket_deliveries(registration, tickets)
    return tickets


def registration_request_hash(
    *,
    event_id,
    tier_id,
    buyer,
    source,
    attendee_names=None,
):
    payload = {
        "event_id": str(event_id),
        "tier_id": str(tier_id),
        "buyer": {
            "name": buyer["name"].strip(),
            "email": buyer["email"].strip().lower(),
            "phone": buyer["phone"],
            "organization": buyer.get("organization", "").strip(),
            "job_title": buyer.get("job_title", "").strip(),
        },
        "source": source,
        "attendee_names": [name.strip() for name in attendee_names or [buyer["name"]]],
    }
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@transaction.atomic
def create_registration_idempotently(
    *,
    idempotency_key,
    event_id,
    tier_id,
    buyer,
    source,
    created_by=None,
    attendee_names=None,
):
    from .models import RegistrationIdempotency

    request_hash = registration_request_hash(
        event_id=event_id,
        tier_id=tier_id,
        buyer=buyer,
        source=source,
        attendee_names=attendee_names,
    )
    try:
        with transaction.atomic():
            idempotency = RegistrationIdempotency.objects.create(
                key=idempotency_key,
                request_hash=request_hash,
            )
    except IntegrityError:
        idempotency = (
            RegistrationIdempotency.objects.select_for_update()
            .filter(pk=idempotency_key)
            .first()
        )
        if idempotency is None:
            raise
        if idempotency.request_hash != request_hash:
            raise IdempotencyConflict()
        if idempotency.registration_id is not None:
            registration = Registration.objects.get(pk=idempotency.registration_id)
            return registration, list(registration.tickets.all()), False

    registration, tickets = create_registration(
        event_id=event_id,
        tier_id=tier_id,
        buyer=buyer,
        source=source,
        created_by=created_by,
        attendee_names=attendee_names,
    )
    idempotency.registration = registration
    idempotency.save(update_fields=("registration",))
    return registration, tickets, True


@transaction.atomic
def create_reserved_registration(
    *,
    idempotency_key,
    event_id,
    tier_id,
    buyer,
    attendee_names,
):
    from datetime import timedelta

    from apps.audit.models import AuditLog
    from apps.payments.models import PaymentIntent

    registration_hash = registration_request_hash(
        event_id=event_id,
        tier_id=tier_id,
        buyer=buyer,
        source=Registration.Source.ONLINE,
        attendee_names=attendee_names,
    )
    try:
        with transaction.atomic():
            registration_idempotency = RegistrationIdempotency.objects.create(
                key=idempotency_key,
                request_hash=registration_hash,
            )
    except IntegrityError:
        registration_idempotency = (
            RegistrationIdempotency.objects.select_for_update()
            .filter(pk=idempotency_key)
            .first()
        )
        if registration_idempotency is None:
            raise
        if registration_idempotency.request_hash != registration_hash:
            raise IdempotencyConflict()
        if registration_idempotency.registration_id is None:
            raise RegistrationConflict(
                "The registration request is still being processed; retry shortly."
            )
        registration = Registration.objects.select_related(
            "event",
            "ticket_tier",
        ).get(pk=registration_idempotency.registration_id)
        intent = PaymentIntent.objects.get(pk=idempotency_key)
        return registration, intent, False

    try:
        event = Event.objects.select_for_update().get(pk=event_id)
    except Event.DoesNotExist as error:
        raise RegistrationConflict("The event is unavailable.") from error
    if event.status != Event.Status.OPEN or not event.registration_open:
        raise RegistrationConflict("Registration is not currently open.")
    try:
        tier = TicketTier.objects.select_for_update().get(pk=tier_id, event=event)
    except TicketTier.DoesNotExist as error:
        raise RegistrationConflict("The selected ticket offer is unavailable.") from error
    if not tier.is_available:
        raise RegistrationConflict("The selected ticket offer is unavailable.")

    names = [name.strip() for name in attendee_names]
    if len(names) != tier.admission_count or any(not name for name in names):
        raise ValidationError(
            {
                "attendee_names": (
                    f"Enter a name for each of the {tier.admission_count} attendees."
                )
            }
        )

    now = timezone.now()
    reservation_expiry = now + timedelta(
        hours=settings.PAYMENT_PROOF_RESERVATION_HOURS
    )
    active_count = Ticket.objects.filter(
        registration__event=event,
        status__in=(Ticket.Status.ISSUED, Ticket.Status.USED),
    ).count()
    active_reservations = InventoryReservation.objects.filter(
        event=event,
        status=InventoryReservation.Status.RESERVED,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    reserved_units = active_reservations.aggregate(total=Sum("units_reserved"))[
        "total"
    ] or 0
    legacy_reservations = PaymentIntent.objects.filter(
        event=event,
        registration__isnull=True,
    ).filter(
        Q(status=PaymentIntent.Status.REVIEW_REQUIRED)
        | Q(status=PaymentIntent.Status.PENDING, expires_at__gt=now)
    )
    legacy_units = legacy_reservations.aggregate(
        total=Sum("ticket_tier__admission_count")
    )["total"] or 0
    if active_count + reserved_units + legacy_units + tier.admission_count > event.capacity:
        raise RegistrationConflict(
            "Not enough event capacity remains for this ticket offer."
        )

    registration = Registration.objects.create(
        event=event,
        ticket_tier=tier,
        buyer_name=buyer["name"].strip(),
        buyer_email=buyer["email"].strip().lower(),
        buyer_phone=buyer["phone"],
        buyer_organization=buyer.get("organization", "").strip(),
        buyer_job_title=buyer.get("job_title", "").strip(),
        source=Registration.Source.ONLINE,
        status=Registration.Status.REGISTERED,
    )
    InventoryReservation.objects.create(
        registration=registration,
        event=event,
        units_reserved=tier.admission_count,
        expires_at=reservation_expiry,
    )
    intent = PaymentIntent.objects.create(
        idempotency_key=idempotency_key,
        request_hash=registration_hash,
        event=event,
        ticket_tier=tier,
        buyer_name=registration.buyer_name,
        buyer_email=registration.buyer_email,
        buyer_phone=registration.buyer_phone,
        buyer_organization=registration.buyer_organization,
        buyer_job_title=registration.buyer_job_title,
        attendee_names=names,
        status=PaymentIntent.Status.PENDING,
        registration=registration,
        expires_at=reservation_expiry,
    )
    registration_idempotency.registration = registration
    registration_idempotency.save(update_fields=("registration",))
    AuditLog.objects.create(
        action="REGISTRATION_CREATED",
        resource_type="registration",
        resource_id=str(registration.id),
        metadata={
            "source": Registration.Source.ONLINE,
            "ticket_count": 0,
            "reservation_expires_at": reservation_expiry.isoformat(),
        },
    )
    return registration, intent, True
