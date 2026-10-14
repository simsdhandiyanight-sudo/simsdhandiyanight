from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.payments.models import Payment
from apps.registrations.models import Registration
from apps.tickets.models import Ticket

from .models import TicketDelivery, TicketSheetSync

SHEET_HEADERS = (
    "ticket_id",
    "ticket_number",
    "registration_id",
    "ticket_type",
    "booking_quantity",
    "ticket_quantity",
    "unit_price",
    "name",
    "email",
    "phone",
    "amount_due",
    "payment_method",
    "provider_order_id",
    "provider_payment_id",
    "upi_id",
    "transaction_id_utr",
    "payment_status",
    "verified_by",
    "verified_at",
    "ticket_status",
    "ticket_generated_at",
    "email_status",
    "email_sent_at",
    "scan_status",
    "checked_in_at",
    "checked_in_by",
    "created_at",
    "updated_at",
    "last_synced_at",
)
SHEET_NAME_BY_SOURCE = {
    Registration.Source.ONLINE: "Online_Tickets",
    Registration.Source.ON_SPOT: "OnSpot_Tickets",
}
MAX_SHEET_SYNC_ATTEMPTS = 5


def ticket_sheet_sync_source(sync):
    if bool(sync.ticket_id) == bool(sync.college_ticket_id):
        raise ValueError("Ticket sheet sync must reference exactly one ticket source.")
    if sync.college_ticket_id:
        return sync.college_ticket, "COLLEGE_STUDENT"
    ticket = sync.ticket
    if ticket.registration.source not in (
        Registration.Source.ONLINE,
        Registration.Source.ON_SPOT,
    ):
        raise ValueError("Ticket sheet sync has an unsupported registration source.")
    return ticket, ticket.registration.source


def ticket_sheet_sync_is_eligible(sync):
    ticket, source = ticket_sheet_sync_source(sync)
    if source not in (Registration.Source.ONLINE, Registration.Source.ON_SPOT):
        return False
    if (
        ticket.status not in (
            Ticket.Status.ISSUED,
            Ticket.Status.USED,
            Ticket.Status.CANCELLED,
        )
        or ticket.registration.status != Registration.Status.TICKET_ISSUED
        or not ticket.ticket_code
        or not ticket.token
    ):
        return False
    eligible_payments = Payment.objects.filter(
        intent__registration_id=ticket.registration_id,
        provider__in=(
            (Payment.Provider.ON_SPOT,)
            if source == Registration.Source.ON_SPOT
            else (Payment.Provider.UPI_MANUAL, Payment.Provider.PAYU)
        ),
        status__in=(Payment.Status.VERIFIED, Payment.Status.CAPTURED),
        verification_status=Payment.VerificationStatus.VERIFIED,
        ticket_issuance_status=Payment.TicketIssuanceStatus.ISSUED,
        verified_at__isnull=False,
    )
    if source == Registration.Source.ON_SPOT:
        eligible_payments = eligible_payments.filter(verified_by__isnull=False)
    return eligible_payments.exists()


def ensure_ticket_sheet_syncs(registration, tickets=None):
    if registration.status != Registration.Status.TICKET_ISSUED:
        return
    tickets = list(tickets if tickets is not None else registration.tickets.all())
    if registration.source not in (
        Registration.Source.ONLINE,
        Registration.Source.ON_SPOT,
    ):
        return
    if not tickets:
        return
    eligible_payments = Payment.objects.filter(
        intent__registration_id=registration.id,
        provider__in=(
            (Payment.Provider.ON_SPOT,)
            if registration.source == Registration.Source.ON_SPOT
            else (Payment.Provider.UPI_MANUAL, Payment.Provider.PAYU)
        ),
        status__in=(Payment.Status.VERIFIED, Payment.Status.CAPTURED),
        verification_status=Payment.VerificationStatus.VERIFIED,
        ticket_issuance_status=Payment.TicketIssuanceStatus.ISSUED,
        verified_at__isnull=False,
    )
    if registration.source == Registration.Source.ON_SPOT:
        eligible_payments = eligible_payments.filter(verified_by__isnull=False)
    if not eligible_payments.exists():
        return
    TicketSheetSync.objects.bulk_create(
        [
            TicketSheetSync(ticket=ticket)
            for ticket in tickets
            if ticket.status == Ticket.Status.ISSUED
        ],
        ignore_conflicts=True,
    )


@transaction.atomic
def request_ticket_sheet_sync_for_delivery(delivery):
    if not delivery.ticket_id:
        return
    request_ticket_sheet_sync(delivery.ticket)


@transaction.atomic
def request_ticket_sheet_sync(ticket):
    sync = (
        TicketSheetSync.objects.select_for_update()
        .filter(ticket_id=ticket.id)
        .first()
    )
    if sync is None:
        sync, _created = TicketSheetSync.objects.get_or_create(
            ticket_id=ticket.id
        )
    if sync.status == TicketSheetSync.Status.PROCESSING:
        sync.resync_requested = True
        sync.save(update_fields=("resync_requested", "updated_at"))
    elif sync.status == TicketSheetSync.Status.PENDING:
        sync.retry_after = None
        sync.failure_reason = ""
        sync.save(
            update_fields=("retry_after", "failure_reason", "updated_at")
        )
    elif sync.status in (
        TicketSheetSync.Status.SYNCED,
        TicketSheetSync.Status.FAILED,
    ):
        sync.status = TicketSheetSync.Status.PENDING
        sync.attempt_count = 0
        sync.retry_after = None
        sync.failure_reason = ""
        sync.failed_at = None
        sync.save(
            update_fields=(
                "status",
                "attempt_count",
                "retry_after",
                "failure_reason",
                "failed_at",
                "updated_at",
            )
        )


def sheet_sync_data(sync):
    ticket, source = ticket_sheet_sync_source(sync)
    if not ticket_sheet_sync_is_eligible(sync):
        return None
    registration = ticket.registration
    event = registration.event
    payment_queryset = Payment.objects.filter(
            intent__registration_id=registration.id,
            provider__in=(
                (Payment.Provider.ON_SPOT,)
                if source == Registration.Source.ON_SPOT
                else (Payment.Provider.UPI_MANUAL, Payment.Provider.PAYU)
            ),
            status__in=(Payment.Status.VERIFIED, Payment.Status.CAPTURED),
            verification_status=Payment.VerificationStatus.VERIFIED,
            ticket_issuance_status=Payment.TicketIssuanceStatus.ISSUED,
            verified_at__isnull=False,
        )
    if source == Registration.Source.ON_SPOT:
        payment_queryset = payment_queryset.filter(verified_by__isnull=False)
    payment = (
        payment_queryset.select_related("verified_by")
        .order_by("-verified_at")
        .first()
    )
    if payment is None:
        return None
    delivery = TicketDelivery.objects.filter(ticket=ticket).first()
    check_in = (
        ticket.scan_history.filter(result="ENTRY_GRANTED")
        .select_related("scanned_by")
        .order_by("-scanned_at")
        .first()
    )
    verified_by = (
        payment.verified_by.name or payment.verified_by.email
        if payment.verified_by
        else "Payment gateway"
    )
    amount_due = f"{payment.amount // 100}.{payment.amount % 100:02d}"
    return {
        "job_id": str(sync.id),
        "attempt": sync.attempt_count,
        "sheet_name": SHEET_NAME_BY_SOURCE[source],
        "headers": list(SHEET_HEADERS),
        "row": {
            "ticket_id": str(ticket.id),
            "ticket_number": ticket.ticket_code,
            "registration_id": str(registration.id),
            "ticket_type": registration.ticket_tier.name,
            "booking_quantity": registration.quantity,
            "ticket_quantity": registration.tickets.count(),
            "unit_price": f"{registration.ticket_tier.price:.2f}",
            "name": ticket.attendee_name or registration.buyer_name,
            "email": registration.buyer_email,
            "phone": registration.buyer_phone,
            "amount_due": amount_due,
            "payment_method": payment.payment_method or payment.provider,
            "provider_order_id": payment.provider_order_id or "",
            "provider_payment_id": payment.provider_payment_id or "",
            "upi_id": "",
            "transaction_id_utr": payment.utr_reference or payment.transaction_id,
            "payment_status": payment.status,
            "verified_by": verified_by,
            "verified_at": payment.verified_at.isoformat(),
            "ticket_status": ticket.status,
            "ticket_generated_at": ticket.issued_at.isoformat(),
            "email_status": delivery.status if delivery else "DISABLED",
            "email_sent_at": (
                delivery.sent_at.isoformat()
                if delivery and delivery.sent_at
                else ""
            ),
            "scan_status": "CHECKED_IN"
            if ticket.status == Ticket.Status.USED
            else "NOT_CHECKED_IN",
            "checked_in_at": check_in.scanned_at.isoformat() if check_in else "",
            "checked_in_by": (
                check_in.scanned_by.name or check_in.scanned_by.email
                if check_in
                else ""
            ),
            "created_at": registration.created_at.isoformat(),
            "updated_at": ticket.updated_at.isoformat(),
            "last_synced_at": timezone.now().isoformat(),
        },
    }


def sheet_sync_retry_time(attempt_count, now=None):
    now = now or timezone.now()
    delay_minutes = min(5 * (2 ** max(attempt_count - 1, 0)), 360)
    return now + timedelta(minutes=delay_minutes)


def sheet_sync_lease_expiry(now=None):
    now = now or timezone.now()
    return now + timedelta(minutes=settings.N8N_SHEET_SYNC_JOB_LEASE_MINUTES)


def backfill_ticket_sheet_syncs(batch_size=500):
    ticket_count = 0
    tickets = Ticket.objects.filter(
        status__in=(
            Ticket.Status.ISSUED,
            Ticket.Status.USED,
            Ticket.Status.CANCELLED,
        ),
        registration__status=Registration.Status.TICKET_ISSUED,
    ).select_related("registration__event").order_by("id")
    for ticket in tickets.iterator(chunk_size=batch_size):
        if not ticket_sheet_sync_is_eligible(TicketSheetSync(ticket=ticket)):
            continue
        request_ticket_sheet_sync(ticket)
        ticket_count += 1
    return ticket_count
