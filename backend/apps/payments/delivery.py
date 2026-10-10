import base64
import html
import logging
import uuid
from datetime import timedelta

import requests
from django.conf import settings
from django.db import models, transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone

from apps.registrations.models import Registration
from apps.tickets.models import Ticket

from .models import EmailDailyUsage, Payment, TicketDelivery
from .pdf import generate_tickets_pdf

logger = logging.getLogger(__name__)

BREVO_DAILY_LIMIT = 300
BREVO_REGULAR_DAILY_LIMIT = 295
BREVO_PRIORITY_DAILY_LIMIT = 5
BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"
BREVO_REQUEST_TIMEOUT = (5, 20)
ABANDONED_CLAIM_TIMEOUT = timedelta(minutes=5)


class BrevoConfigurationError(RuntimeError):
    pass


def ensure_ticket_deliveries(registration, tickets=None):
    tickets = list(tickets if tickets is not None else registration.tickets.all())
    TicketDelivery.objects.bulk_create(
        [
            TicketDelivery(
                ticket=ticket,
                recipient=registration.buyer_email,
                priority=TicketDelivery.Priority.REGULAR,
            )
            for ticket in tickets
        ],
        ignore_conflicts=True,
    )


def _daily_usage_for_update(day):
    EmailDailyUsage.objects.get_or_create(date=day)
    return EmailDailyUsage.objects.select_for_update().get(date=day)


def _reconcile_abandoned_claims(now):
    stale_claims = TicketDelivery.objects.filter(
        status=TicketDelivery.Status.SENDING,
    ).filter(
        Q(last_attempt_at__isnull=True)
        | Q(last_attempt_at__lte=now - ABANDONED_CLAIM_TIMEOUT)
    ).select_for_update(
        skip_locked=True,
        of=("self",),
    )
    stale_ids = list(stale_claims.values_list("pk", flat=True))
    if stale_ids:
        TicketDelivery.objects.filter(
            pk__in=stale_ids,
            status=TicketDelivery.Status.SENDING,
        ).update(
            status=TicketDelivery.Status.RECONCILIATION_REQUIRED,
            claim_token=None,
            failure_reason=(
                "Worker stopped while the provider outcome may have been in flight. "
                "Check Brevo before taking any manual action; automatic retry is blocked."
            ),
            updated_at=now,
        )


def claim_next_ticket_email():
    if not settings.BREVO_API_KEY or not settings.BREVO_SENDER_EMAIL:
        raise BrevoConfigurationError(
            "Configure BREVO_API_KEY and BREVO_SENDER_EMAIL before running the worker."
        )
    day = timezone.localdate()
    now = timezone.now()
    claim_token = uuid.uuid4()
    with transaction.atomic():
        usage = _daily_usage_for_update(day)
        _reconcile_abandoned_claims(now)
        available_priorities = []
        if usage.priority_slots_used < BREVO_PRIORITY_DAILY_LIMIT:
            available_priorities.extend(
                (
                    TicketDelivery.Priority.STAFF,
                    TicketDelivery.Priority.COMPLIMENTARY,
                )
            )
        if usage.regular_slots_used < BREVO_REGULAR_DAILY_LIMIT:
            available_priorities.append(TicketDelivery.Priority.REGULAR)
        if not available_priorities:
            return None
        candidates = (
            TicketDelivery.objects.filter(
                status=TicketDelivery.Status.PENDING,
                ticket__status=Ticket.Status.ISSUED,
                priority__in=available_priorities,
            )
            .filter(Q(retry_after__isnull=True) | Q(retry_after__lte=now))
            .filter(
                Q(ticket__registration__source=Registration.Source.ON_SPOT)
                | Q(
                    ticket__registration__payment_intent__status="VERIFIED",
                )
            )
            .annotate(
                priority_order=Case(
                    When(priority=TicketDelivery.Priority.STAFF, then=Value(0)),
                    When(
                        priority=TicketDelivery.Priority.COMPLIMENTARY,
                        then=Value(1),
                    ),
                    default=Value(2),
                    output_field=IntegerField(),
                )
            )
            .order_by("priority_order", "created_at", "id")
        )
        delivery = candidates.select_for_update(
            skip_locked=True,
            of=("self",),
        ).first()
        if delivery is None:
            return None

        if delivery.priority == TicketDelivery.Priority.REGULAR:
            usage.regular_slots_used += 1
        else:
            usage.priority_slots_used += 1
        usage.save(
            update_fields=(
                "regular_slots_used",
                "priority_slots_used",
                "updated_at",
            )
        )

        delivery.status = TicketDelivery.Status.SENDING
        delivery.quota_date = day
        delivery.quota_reserved = True
        delivery.claim_token = claim_token
        delivery.attempt_count += 1
        delivery.last_attempt_at = now
        delivery.failure_reason = ""
        delivery.retry_after = None
        delivery.save(
            update_fields=(
                "status",
                "quota_date",
                "quota_reserved",
                "claim_token",
                "attempt_count",
                "last_attempt_at",
                "failure_reason",
                "retry_after",
                "updated_at",
            )
        )
        return delivery.id, claim_token


def _ticket_email_content(ticket):
    registration = ticket.registration
    event = registration.event
    local_start = timezone.localtime(event.start_at)
    local_end = timezone.localtime(event.end_at)
    event_date = local_start.strftime("%A, %d %B %Y")
    event_time = (
        f"{local_start.strftime('%I:%M %p').lstrip('0')} – "
        f"{local_end.strftime('%I:%M %p').lstrip('0')}"
    )
    attendee = ticket.attendee_name or registration.buyer_name
    manual_payment_verified = Payment.objects.filter(
        intent__registration=registration,
        provider="UPI_MANUAL",
        status="VERIFIED",
    ).exists()
    ticket_id = registration.ticket_id or registration.registration_code
    details = [
        ("Event", event.name),
        ("Date", event_date),
        ("Time", event_time),
        ("Reporting time", event.reporting_time or "Please arrive one hour before the event."),
        ("Venue", event.venue),
        ("Location", event.address),
        ("Attendee", attendee),
        ("Ticket ID", ticket_id if manual_payment_verified else ticket.ticket_code),
        ("Ticket type", registration.ticket_tier.name),
    ]
    plain = [
        f"Dear {attendee},",
        "",
        (
            f"Payment for your registration for {event.name} has been verified."
            if manual_payment_verified
            else f"Your registration for {event.name} has been confirmed."
        ),
        "",
        "EVENT DETAILS",
        *(f"{label}: {value}" for label, value in details),
    ]
    markup = [
        f"<p>Dear {html.escape(attendee)},</p>",
        f"<p>Your registration for <strong>{html.escape(event.name)}</strong> "
        "has been successfully confirmed.</p>",
        "<h3>Event details</h3><dl>",
        *(
            f"<dt><strong>{html.escape(label)}</strong></dt>"
            f"<dd>{html.escape(value)}</dd>"
            for label, value in details
        ),
        "</dl>",
    ]
    if event.location_url:
        plain.append(f"Map: {event.location_url}")
        markup.append(
            f'<p><a href="{html.escape(event.location_url, quote=True)}">Open event location map</a></p>'
        )
    if event.rules_and_regulations:
        plain.extend(("", "RULES & REGULATIONS"))
        markup.append("<h3>Rules &amp; Regulations</h3><ul>")
        for rule in event.rules_and_regulations:
            plain.append(f"- {rule}")
            markup.append(f"<li>{html.escape(str(rule))}</li>")
        markup.append("</ul>")
    if event.instructions:
        plain.extend(("", "IMPORTANT INSTRUCTIONS"))
        markup.append("<h3>Important Instructions</h3><ul>")
        for instruction in event.instructions:
            plain.append(f"- {instruction}")
            markup.append(f"<li>{html.escape(str(instruction))}</li>")
        markup.append("</ul>")
    plain.extend(
        (
            "",
            "Please carry this ticket and present its QR code at the entry gate.",
            "Your individual ticket PDF is attached.",
            "",
            f"Regards,\n{event.name}",
        )
    )
    if manual_payment_verified:
        plain.extend(
            (
                "",
                "Your final admission ticket is attached. Download it and present its QR code at the entry gate.",
            )
        )
        markup.append(
            "<p>Your payment has been verified. Download the attached final admission ticket "
            "and present its QR code at the entry gate.</p>"
        )
    markup.extend(
        (
            "<p>Please carry this ticket and present its QR code at the entry gate.</p>",
            "<p>Your individual ticket PDF is attached.</p>",
            f"<p>Regards,<br>{html.escape(event.name)}</p>",
        )
    )
    return (
        (
            f"Payment Verified – Your Admission Ticket [{ticket_id}]"
            if manual_payment_verified
            else f"Your Ticket – {event.name} | {local_start.strftime('%d %B %Y')}"
        ),
        "\n".join(plain),
        "<html><body>" + "".join(markup) + "</body></html>",
    )


def send_payment_rejection_email(payment_id):
    payment = Payment.objects.select_related(
        "intent__registration__event",
    ).filter(
        pk=payment_id,
        provider=Payment.Provider.UPI_MANUAL,
        status=Payment.Status.REJECTED,
    ).first()
    if payment is None:
        raise Payment.DoesNotExist
    claimed = Payment.objects.filter(
        pk=payment.pk,
        rejection_email_status="PENDING",
    ).update(
        rejection_email_status="SENDING",
        updated_at=timezone.now(),
    )
    if not claimed:
        return payment.rejection_email_status or "FAILED"

    registration = payment.intent.registration
    subject = f"Action required for payment proof – {registration.ticket_id}"
    registration_url = (
        f"{settings.PAYU_FRONTEND_URL.rstrip('/')}/registration/success"
        f"?registration_id={registration.pk}"
        f"#token={payment.intent.proof_access_token}"
        if settings.PAYU_FRONTEND_URL
        else ""
    )
    deadline = (
        timezone.localtime(payment.rejection_deadline).strftime("%d %b %Y, %I:%M %p")
        if payment.rejection_deadline
        else "within 12 hours"
    )
    text_content = "\n".join(
        (
            f"Hello {registration.buyer_name},",
            "",
            "Your payment proof could not be verified.",
            f"Reason: {payment.rejection_reason}",
            f"Please submit corrected payment proof by {deadline}.",
            f"Ticket ID: {registration.ticket_id}",
            *(("", f"Submit corrected proof here: {registration_url}") if registration_url else ()),
        )
    )
    payload = {
        "sender": {
            "name": settings.BREVO_SENDER_NAME,
            "email": settings.BREVO_SENDER_EMAIL,
        },
        "to": [{"email": registration.buyer_email, "name": registration.buyer_name}],
        "subject": subject,
        "textContent": text_content,
        "tags": [f"payment-proof-rejection-{payment.id}"],
    }
    result = "FAILED"
    try:
        if not settings.BREVO_API_KEY or not settings.BREVO_SENDER_EMAIL:
            raise BrevoConfigurationError(
                "Configure BREVO_API_KEY and BREVO_SENDER_EMAIL before sending rejection email."
            )
        response = requests.post(
            BREVO_SEND_URL,
            headers={
                "accept": "application/json",
                "api-key": settings.BREVO_API_KEY,
                "content-type": "application/json",
            },
            json=payload,
            timeout=BREVO_REQUEST_TIMEOUT,
        )
        if 200 <= response.status_code < 300:
            result = "SENT"
        else:
            logger.error(
                "Brevo rejected payment-proof rejection email %s with HTTP %s.",
                payment_id,
                response.status_code,
            )
    except (requests.RequestException, BrevoConfigurationError):
        logger.exception(
            "Could not send payment-proof rejection email for payment %s.",
            payment_id,
        )
    Payment.objects.filter(
        pk=payment.pk,
        rejection_email_status="SENDING",
    ).update(rejection_email_status=result, updated_at=timezone.now())
    return result


def _release_reservation(
    delivery_id,
    claim_token,
    *,
    status,
    reason,
    retry_after=None,
):
    quota_date = TicketDelivery.objects.values_list("quota_date", flat=True).get(
        pk=delivery_id
    )
    if quota_date:
        EmailDailyUsage.objects.select_for_update().get(date=quota_date)
    delivery = TicketDelivery.objects.select_for_update().get(pk=delivery_id)
    if (
        delivery.status != TicketDelivery.Status.SENDING
        or delivery.claim_token != claim_token
    ):
        logger.error("Email delivery claim changed before reservation release.")
        return False
    if delivery.quota_reserved and delivery.quota_date:
        usage = EmailDailyUsage.objects.select_for_update().get(
            date=delivery.quota_date
        )
        if delivery.priority == TicketDelivery.Priority.REGULAR:
            usage.regular_slots_used -= 1
            field = "regular_slots_used"
        else:
            usage.priority_slots_used -= 1
            field = "priority_slots_used"
        usage.save(update_fields=(field, "updated_at"))
    delivery.status = status
    delivery.quota_reserved = False
    delivery.claim_token = None
    delivery.failure_reason = reason[:500]
    delivery.retry_after = retry_after
    if status == TicketDelivery.Status.FAILED:
        delivery.failed_at = timezone.now()
    delivery.save(
        update_fields=(
            "status",
            "quota_reserved",
            "claim_token",
            "failure_reason",
            "retry_after",
            "failed_at",
            "updated_at",
        )
    )
    return True


def _current_delivery_status(delivery_id):
    return TicketDelivery.objects.values_list("status", flat=True).get(
        pk=delivery_id
    )


def _finish_accepted_delivery(delivery_id, claim_token, message_id):
    with transaction.atomic():
        day = TicketDelivery.objects.values_list("quota_date", flat=True).get(
            pk=delivery_id
        )
        usage = EmailDailyUsage.objects.select_for_update().get(date=day)
        delivery = TicketDelivery.objects.select_for_update().get(pk=delivery_id)
        if (
            delivery.status != TicketDelivery.Status.SENDING
            or delivery.claim_token != claim_token
            or not delivery.quota_reserved
        ):
            logger.error("Email delivery claim changed before Brevo result was stored.")
            return False
        if delivery.priority == TicketDelivery.Priority.REGULAR:
            usage.regular_sent += 1
            field = "regular_sent"
        else:
            usage.priority_sent += 1
            field = "priority_sent"
        usage.save(update_fields=(field, "updated_at"))
        delivery.status = TicketDelivery.Status.SENT
        delivery.provider_message_id = message_id or None
        delivery.sent_at = timezone.now()
        delivery.quota_reserved = False
        delivery.claim_token = None
        delivery.failure_reason = ""
        delivery.save(
            update_fields=(
                "status",
                "provider_message_id",
                "sent_at",
                "quota_reserved",
                "claim_token",
                "failure_reason",
                "updated_at",
            )
        )
        return True


def _mark_unknown_outcome(delivery_id, claim_token, reason):
    TicketDelivery.objects.filter(
        pk=delivery_id,
        status=TicketDelivery.Status.SENDING,
        claim_token=claim_token,
    ).update(
        status=TicketDelivery.Status.RECONCILIATION_REQUIRED,
        claim_token=None,
        failure_reason=reason[:500],
        updated_at=timezone.now(),
    )
    logger.error(
        "Brevo delivery outcome is unknown for ticket email %s; quota remains reserved.",
        delivery_id,
    )


def process_ticket_email(delivery_id, claim_token):
    delivery = (
        TicketDelivery.objects.select_related(
            "ticket__registration__event",
            "ticket__registration__ticket_tier",
        )
        .get(pk=delivery_id)
    )
    ticket = delivery.ticket
    if delivery.pdf_content is None:
        try:
            pdf_content = generate_tickets_pdf([ticket])
        except Exception as error:
            logger.exception("Could not generate ticket PDF for delivery %s.", delivery_id)
            with transaction.atomic():
                released = _release_reservation(
                    delivery_id,
                    claim_token,
                    status=TicketDelivery.Status.FAILED,
                    reason=f"PDF generation failed: {type(error).__name__}",
                )
            if not released:
                return _current_delivery_status(delivery_id)
            return TicketDelivery.Status.FAILED
        pdf_saved = TicketDelivery.objects.filter(
            pk=delivery_id,
            status=TicketDelivery.Status.SENDING,
            claim_token=claim_token,
        ).update(pdf_content=pdf_content, updated_at=timezone.now())
        if not pdf_saved:
            logger.warning(
                "Email delivery claim was lost before its PDF could be saved."
            )
            return _current_delivery_status(delivery_id)
        delivery.pdf_content = pdf_content

    if not TicketDelivery.objects.filter(
        pk=delivery_id,
        status=TicketDelivery.Status.SENDING,
        claim_token=claim_token,
        quota_reserved=True,
    ).exists():
        logger.warning("Email delivery claim was lost before the provider request.")
        return _current_delivery_status(delivery_id)

    if not settings.BREVO_API_KEY:
        raise BrevoConfigurationError("BREVO_API_KEY is not configured.")
    if not settings.BREVO_SENDER_EMAIL:
        raise BrevoConfigurationError("BREVO_SENDER_EMAIL is not configured.")

    subject, text_content, html_content = _ticket_email_content(ticket)
    payload = {
        "sender": {
            "name": settings.BREVO_SENDER_NAME,
            "email": settings.BREVO_SENDER_EMAIL,
        },
        "to": [{"email": delivery.recipient, "name": ticket.attendee_name or ticket.registration.buyer_name}],
        "subject": subject,
        "textContent": text_content,
        "htmlContent": html_content,
        "tags": [f"ticket-delivery-{delivery.id}"],
        "attachment": [
            {
                "name": f"ticket-{ticket.id}.pdf",
                "content": base64.b64encode(bytes(delivery.pdf_content)).decode("ascii"),
            }
        ],
    }
    try:
        response = requests.post(
            BREVO_SEND_URL,
            headers={
                "accept": "application/json",
                "api-key": settings.BREVO_API_KEY,
                "content-type": "application/json",
            },
            json=payload,
            timeout=BREVO_REQUEST_TIMEOUT,
        )
    except requests.RequestException as error:
        _mark_unknown_outcome(
            delivery_id,
            claim_token,
            f"Brevo request outcome is unknown ({type(error).__name__}); "
            "automatic retry is blocked to prevent duplicate ticket emails.",
        )
        return TicketDelivery.Status.RECONCILIATION_REQUIRED

    if response.status_code == 429:
        with transaction.atomic():
            _release_reservation(
                delivery_id,
                claim_token,
                status=TicketDelivery.Status.PENDING,
                reason="Brevo rate-limited the request; retry will be attempted later.",
                retry_after=timezone.now() + timedelta(minutes=1),
            )
        return TicketDelivery.Status.PENDING
    if response.status_code >= 500:
        _mark_unknown_outcome(
            delivery_id,
            claim_token,
            f"Brevo returned HTTP {response.status_code}; outcome is unknown and "
            "automatic retry is blocked to prevent duplicate ticket emails.",
        )
        return TicketDelivery.Status.RECONCILIATION_REQUIRED
    if response.status_code >= 400:
        with transaction.atomic():
            _release_reservation(
                delivery_id,
                claim_token,
                status=TicketDelivery.Status.FAILED,
                reason=f"Brevo rejected the request with HTTP {response.status_code}.",
            )
        return TicketDelivery.Status.FAILED

    try:
        response_payload = response.json()
    except ValueError:
        response_payload = {}
    message_id = response_payload.get("messageId")
    if message_id is not None:
        message_id = str(message_id)[:120]
    if not _finish_accepted_delivery(delivery_id, claim_token, message_id):
        return _current_delivery_status(delivery_id)
    return TicketDelivery.Status.SENT


def process_next_ticket_email():
    claim = claim_next_ticket_email()
    if claim is None:
        return None
    delivery_id, claim_token = claim
    return process_ticket_email(delivery_id, claim_token)


def get_delivery_dashboard():
    today = timezone.localdate()
    usage = EmailDailyUsage.objects.filter(date=today).first()
    regular_slots_used = usage.regular_slots_used if usage else 0
    priority_slots_used = usage.priority_slots_used if usage else 0
    regular_sent = usage.regular_sent if usage else 0
    priority_sent = usage.priority_sent if usage else 0
    delivery_counts = {
        row["status"]: row["count"]
        for row in TicketDelivery.objects.values("status").annotate(
            count=models.Count("id")
        )
    }
    priority_counts = {
        row["priority"]: row["count"]
        for row in TicketDelivery.objects.values("priority").annotate(
            count=models.Count("id")
        )
    }
    queue = (
        TicketDelivery.objects.filter(
            status__in=(
                TicketDelivery.Status.PENDING,
                TicketDelivery.Status.SENDING,
                TicketDelivery.Status.FAILED,
                TicketDelivery.Status.RECONCILIATION_REQUIRED,
            )
        )
        .defer("pdf_content")
        .select_related("ticket__registration__event")
        .order_by("created_at")[:100]
    )
    return {
        "total_ticket_emails": sum(delivery_counts.values()),
        "provider_configured": bool(
            settings.BREVO_API_KEY and settings.BREVO_SENDER_EMAIL
        ),
        "statuses": delivery_counts,
        "priorities": priority_counts,
        "quota": {
            "brevo_limit": BREVO_DAILY_LIMIT,
            "regular_allocation": BREVO_REGULAR_DAILY_LIMIT,
            "priority_allocation": BREVO_PRIORITY_DAILY_LIMIT,
            "regular_sent": regular_sent,
            "priority_sent": priority_sent,
            "regular_reserved": regular_slots_used - regular_sent,
            "priority_reserved": priority_slots_used - priority_sent,
            "total_sent": regular_sent + priority_sent,
            "remaining_regular": BREVO_REGULAR_DAILY_LIMIT - regular_slots_used,
            "remaining_priority": BREVO_PRIORITY_DAILY_LIMIT - priority_slots_used,
            "date": today.isoformat(),
        },
        "queue": [
            {
                "id": str(delivery.id),
                "ticket_id": str(delivery.ticket_id),
                "attendee_name": delivery.ticket.attendee_name
                or delivery.ticket.registration.buyer_name,
                "event_name": delivery.ticket.registration.event.name,
                "recipient": delivery.recipient,
                "priority": delivery.priority,
                "status": delivery.status,
                "attempt_count": delivery.attempt_count,
                "failure_reason": delivery.failure_reason,
                "provider_message_id": delivery.provider_message_id,
                "created_at": delivery.created_at.isoformat(),
                "last_attempt_at": (
                    delivery.last_attempt_at.isoformat()
                    if delivery.last_attempt_at
                    else None
                ),
            }
            for delivery in queue
        ],
    }


def handle_brevo_webhook(*, message_id, event_name):
    event_name = event_name.casefold()
    with transaction.atomic():
        delivery = (
            TicketDelivery.objects.select_for_update()
            .filter(provider_message_id=message_id)
            .first()
        )
        if delivery is None:
            return False
        if delivery.status == TicketDelivery.Status.DELIVERED:
            return True
        if event_name == "delivered":
            delivery.status = TicketDelivery.Status.DELIVERED
            delivery.delivered_at = timezone.now()
            delivery.failed_at = None
            delivery.failure_reason = ""
        elif event_name in {"hardbounce", "blocked", "invalid", "error", "spam"}:
            if delivery.status != TicketDelivery.Status.DELIVERED:
                delivery.status = TicketDelivery.Status.FAILED
                delivery.failed_at = timezone.now()
                delivery.failure_reason = f"Brevo delivery event: {event_name}"[:500]
        else:
            return True
        delivery.save(
            update_fields=(
                "status",
                "delivered_at",
                "failed_at",
                "failure_reason",
                "updated_at",
            )
        )
        return True
