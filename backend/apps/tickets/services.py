from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.audit.models import AuditLog
from .models import Ticket


class TicketStateConflict(APIException):
    status_code = 409
    default_detail = "The ticket is not in a cancellable state."
    default_code = "TICKET_STATE_CONFLICT"


@transaction.atomic
def cancel_ticket(ticket_id, actor):
    ticket = (
        Ticket.objects.select_for_update()
        .select_related("registration")
        .get(pk=ticket_id)
    )
    if ticket.status != Ticket.Status.ISSUED:
        raise TicketStateConflict(
            f"A ticket in {ticket.status} status cannot be cancelled."
        )

    ticket.status = Ticket.Status.CANCELLED
    ticket.cancelled_at = timezone.now()
    ticket.save(update_fields=("status", "cancelled_at", "updated_at"))
    AuditLog.objects.create(
        actor=actor,
        action="TICKET_CANCELLED",
        resource_type="ticket",
        resource_id=str(ticket.id),
        metadata={"registration_id": str(ticket.registration_id)},
    )
    return ticket
