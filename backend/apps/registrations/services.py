from django.db import transaction
from rest_framework.exceptions import APIException

from apps.events.models import Event, TicketTier
from apps.tickets.models import Ticket
from .models import Registration


class RegistrationConflict(APIException):
    status_code = 409
    default_detail = "The selected ticket offer is no longer available."
    default_code = "REGISTRATION_CONFLICT"


@transaction.atomic
def create_registration(*, event_id, tier_id, buyer, source, created_by=None):
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

    active_count = Ticket.objects.filter(registration__event=event).exclude(
        status=Ticket.Status.CANCELLED
    ).count()
    if active_count + tier.admission_count > event.capacity:
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
        Ticket(registration=registration)
        for _ in range(tier.admission_count)
    ]
    Ticket.objects.bulk_create(tickets)
    from apps.audit.models import AuditLog

    AuditLog.objects.create(
        actor=created_by,
        action="REGISTRATION_CREATED",
        resource_type="registration",
        resource_id=str(registration.id),
        metadata={"source": source, "ticket_count": len(tickets)},
    )
    return registration, tickets
