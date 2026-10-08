import hashlib
import json

from django.db import IntegrityError, transaction
from rest_framework.exceptions import APIException, ValidationError
from django.db.models import Sum
from django.utils import timezone

from apps.events.models import Event, TicketTier
from apps.tickets.models import Ticket
from .models import Registration


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

    if not tier.is_available:
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
        status=PaymentIntent.Status.PENDING,
        expires_at__gt=timezone.now(),
    )
    if exclude_payment_intent_id is not None:
        reservations = reservations.exclude(pk=exclude_payment_intent_id)
    reserved_count = reservations.aggregate(
        total=Sum("ticket_tier__admission_count")
    )["total"] or 0
    if active_count + reserved_count + tier.admission_count > event.capacity:
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
        created_by=created_by,
    )
    tickets = [
        Ticket(registration=registration, attendee_name=attendee_name)
        for attendee_name in names
    ]
    Ticket.objects.bulk_create(tickets)
    from apps.payments.delivery import ensure_ticket_deliveries

    ensure_ticket_deliveries(registration, tickets)
    from apps.audit.models import AuditLog

    AuditLog.objects.create(
        actor=created_by,
        action="REGISTRATION_CREATED",
        resource_type="registration",
        resource_id=str(registration.id),
        metadata={"source": source, "ticket_count": len(tickets)},
    )
    return registration, tickets


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
