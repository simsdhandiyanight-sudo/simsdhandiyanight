from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.events.models import Event
from apps.registrations.models import Registration
from apps.tickets.models import CollegeStudentTicket, Ticket
from .models import StaffAssignment, TicketScan


class ScannerConfigurationError(Exception):
    pass


def assigned_gate_for(user):
    assignments = list(
        StaffAssignment.objects.filter(user=user, gate__is_active=True)
        .select_related("gate", "gate__event")
        .order_by("assigned_at")[:2]
    )
    if len(assignments) != 1:
        raise ScannerConfigurationError(
            "An active scanner must have exactly one active gate assignment."
        )
    return assignments[0].gate


@transaction.atomic
def scan_ticket(*, token, scanner):
    gate = assigned_gate_for(scanner)
    ticket = (
        Ticket.objects.select_for_update()
        .select_related("registration", "registration__event", "registration__ticket_tier")
        .filter(token=token)
        .first()
    )
    college_ticket = (
        CollegeStudentTicket.objects.select_for_update()
        .select_related("event")
        .filter(token=token)
        .first()
    )
    if ticket is not None and college_ticket is not None:
        ticket = None
        college_ticket = None
        result = TicketScan.Result.INVALID_TICKET
    elif ticket is None and college_ticket is None:
        result = TicketScan.Result.INVALID_TICKET
    elif ticket is not None and ticket.status == Ticket.Status.USED:
        result = TicketScan.Result.ALREADY_USED
    elif ticket is not None and ticket.status == Ticket.Status.CANCELLED:
        result = TicketScan.Result.CANCELLED
    elif college_ticket is not None and college_ticket.status == CollegeStudentTicket.Status.USED:
        result = TicketScan.Result.ALREADY_USED
    elif college_ticket is not None and college_ticket.status == CollegeStudentTicket.Status.CANCELLED:
        result = TicketScan.Result.CANCELLED
    elif (
        ticket is not None and ticket.registration.event_id != gate.event_id
    ) or (
        college_ticket is not None and college_ticket.event_id != gate.event_id
    ):
        result = TicketScan.Result.WRONG_EVENT
    elif gate.event.status != Event.Status.OPEN:
        result = TicketScan.Result.EVENT_CLOSED
    elif ticket is not None and ticket.registration.source != Registration.Source.ON_SPOT and (
        ticket.registration.status != Registration.Status.TICKET_ISSUED
    ):
        result = TicketScan.Result.PAYMENT_NOT_VERIFIED
    else:
        result = TicketScan.Result.ENTRY_GRANTED
        if ticket is not None:
            ticket.status = Ticket.Status.USED
            ticket.used_at = timezone.now()
            ticket.save(update_fields=("status", "used_at", "updated_at"))
            from apps.payments.sheets import request_ticket_sheet_sync

            request_ticket_sheet_sync(ticket)
        else:
            college_ticket.status = CollegeStudentTicket.Status.USED
            college_ticket.used_at = timezone.now()
            college_ticket.save(update_fields=("status", "used_at", "updated_at"))

    scan = TicketScan.objects.create(
        ticket=ticket,
        college_ticket=college_ticket,
        event=gate.event,
        gate=gate,
        scanned_by=scanner,
        result=result,
    )
    AuditLog.objects.create(
        actor=scanner,
        action="TICKET_SCAN",
        resource_type=(
            "ticket"
            if ticket
            else "college_student_ticket"
            if college_ticket
            else "scan"
        ),
        resource_id=(
            str(ticket.id)
            if ticket
            else str(college_ticket.id)
            if college_ticket
            else str(scan.id)
        ),
        metadata={"result": result, "gate_id": str(gate.id)},
    )
    return scan
