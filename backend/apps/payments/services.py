import hashlib
import hmac
import json
import logging
from datetime import timedelta

import razorpay
import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, F, OuterRef, Q, Sum
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException, NotFound

from apps.registrations.models import Registration
from apps.registrations.serializers import RegistrationSerializer
from apps.registrations.services import (
    IdempotencyConflict,
    RegistrationConflict,
    create_registration,
)
from apps.audit.models import AuditLog
from apps.tickets.models import Ticket
from .models import Payment, PaymentIntent, TicketDelivery

logger = logging.getLogger(__name__)
ORDER_LIFETIME = timedelta(minutes=15)


class PaymentConflict(APIException):
    status_code = 409
    default_detail = "The payment cannot be processed in its current state."
    default_code = "PAYMENT_CONFLICT"


class PaymentVerificationError(APIException):
    status_code = 400
    default_detail = "Payment verification failed."
    default_code = "PAYMENT_VERIFICATION_FAILED"


class PaymentProviderUnavailable(APIException):
    status_code = 502
    default_detail = "The payment provider is temporarily unavailable. Retry with the same idempotency key."
    default_code = "PAYMENT_PROVIDER_UNAVAILABLE"


class PaymentReviewRequired(APIException):
    status_code = 409
    default_detail = (
        "The payment was captured, but ticket issuance requires administrator review."
    )
    default_code = "PAYMENT_REVIEW_REQUIRED"


def payment_client():
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise PaymentProviderUnavailable(
            "Razorpay test credentials are not configured."
        )
    return razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )


def payment_request_hash(*, event_id, tier_id, buyer, attendee_names):
    payload = {
        "event_id": str(event_id),
        "ticket_tier_id": str(tier_id),
        "buyer": {
            "name": buyer["name"].strip(),
            "email": buyer["email"].strip().lower(),
            "phone": buyer["phone"],
            "organization": buyer.get("organization", "").strip(),
            "job_title": buyer.get("job_title", "").strip(),
        },
        "attendee_names": [name.strip() for name in attendee_names],
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _intent_result(intent, payment, *, replayed):
    if intent.status == PaymentIntent.Status.VERIFIED and intent.registration_id:
        registration = (
            Registration.objects.select_related("event", "ticket_tier")
            .prefetch_related("tickets")
            .get(pk=intent.registration_id)
        )
        serialized = RegistrationSerializer(registration).data
        delivery_status = TicketDelivery.objects.filter(
            ticket__registration_id=registration.id
        ).order_by("created_at").values_list("status", flat=True).first()
        return {
            "payment_verified": True,
            "order_id": payment.razorpay_order_id,
            "payment_id": payment.razorpay_payment_id,
            "registration": serialized,
            "ticket": serialized["tickets"][0],
            "tickets": serialized["tickets"],
            "delivery_status": delivery_status,
            "replayed": replayed,
        }
    return {
        "payment_verified": False,
        "order_id": payment.razorpay_order_id,
        "amount": payment.amount,
        "currency": payment.currency,
        "display_amount": float(payment.amount) / 100,
        "key_id": settings.RAZORPAY_KEY_ID,
        "replayed": replayed,
    }


def create_payment_order(*, idempotency_key, event_id, tier_id, buyer, attendee_names):
    from apps.events.models import Event, TicketTier

    request_hash = payment_request_hash(
        event_id=event_id,
        tier_id=tier_id,
        buyer=buyer,
        attendee_names=attendee_names,
    )
    provider_error = None
    result = None

    with transaction.atomic():
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
        if len(attendee_names) != tier.admission_count:
            raise serializers.ValidationError(
                {
                    "attendee_names": (
                        f"Enter a name for each of the {tier.admission_count} attendees."
                    )
                }
            )

        try:
            with transaction.atomic():
                intent = PaymentIntent.objects.create(
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    event=event,
                    ticket_tier=tier,
                    buyer_name=buyer["name"].strip(),
                    buyer_email=buyer["email"].strip().lower(),
                    buyer_phone=buyer["phone"],
                    buyer_organization=buyer.get("organization", "").strip(),
                    buyer_job_title=buyer.get("job_title", "").strip(),
                    attendee_names=[name.strip() for name in attendee_names],
                    expires_at=timezone.now() + ORDER_LIFETIME,
                )
                is_new_intent = True
        except IntegrityError:
            intent = PaymentIntent.objects.select_for_update().get(
                pk=idempotency_key
            )
            if intent.request_hash != request_hash:
                raise IdempotencyConflict()
            is_new_intent = False
            if intent.registration_id:
                verified_payment = intent.payments.filter(
                    verification_status=Payment.VerificationStatus.VERIFIED
                ).first()
                if verified_payment:
                    return _intent_result(intent, verified_payment, replayed=True)

        if not is_new_intent:
            current_payment = intent.payments.order_by("-created_at").first()
            if current_payment and current_payment.status == Payment.Status.CAPTURED:
                raise PaymentReviewRequired()
            if (
                current_payment
                and current_payment.status == Payment.Status.CREATED
                and current_payment.expires_at > timezone.now()
            ):
                return _intent_result(intent, current_payment, replayed=True)
            if (
                current_payment
                and current_payment.status == Payment.Status.CREATING
                and current_payment.created_at > timezone.now() - timedelta(minutes=2)
            ):
                raise PaymentConflict("The payment order is still being created; retry shortly.")

        active_ticket_count = (
            Ticket.objects.filter(registration__event=event)
            .exclude(status=Ticket.Status.CANCELLED)
            .count()
        )
        reserved_count = (
            PaymentIntent.objects.filter(
                event=event,
                status=PaymentIntent.Status.PENDING,
                expires_at__gt=timezone.now(),
            )
            .exclude(pk=idempotency_key)
            .aggregate(total=Sum("ticket_tier__admission_count"))["total"]
            or 0
        )
        if active_ticket_count + reserved_count + tier.admission_count > event.capacity:
            raise RegistrationConflict(
                "Not enough event capacity remains for this ticket offer."
            )

        expires_at = timezone.now() + ORDER_LIFETIME
        intent.status = PaymentIntent.Status.PENDING
        intent.expires_at = expires_at
        intent.save(update_fields=("status", "expires_at", "updated_at"))
        amount = int(tier.price * 100)
        payment = Payment.objects.create(
            intent=intent,
            amount=amount,
            currency=tier.currency,
            expires_at=expires_at,
        )

        try:
            order = payment_client().order.create(
                {
                    "amount": amount,
                    "currency": tier.currency,
                    "receipt": f"pay-{payment.id.hex}",
                    "notes": {
                        "payment_id": str(payment.id),
                        "event_id": str(event.id),
                        "ticket_tier_id": str(tier.id),
                    },
                }
            )
        except (
            razorpay.errors.BadRequestError,
            razorpay.errors.GatewayError,
            razorpay.errors.ServerError,
            requests.RequestException,
        ) as error:
            payment.status = Payment.Status.FAILED
            payment.failure_message = "Payment order creation failed."
            payment.save(
                update_fields=("status", "failure_message", "updated_at")
            )
            intent.status = PaymentIntent.Status.FAILED
            intent.save(update_fields=("status", "updated_at"))
            logger.exception("Razorpay order creation failed for payment %s.", payment.id)
            provider_error = error
        else:
            payment.razorpay_order_id = order["id"]
            payment.status = Payment.Status.CREATED
            payment.save(
                update_fields=("razorpay_order_id", "status", "updated_at")
            )
            result = _intent_result(intent, payment, replayed=False)

    if provider_error:
        raise PaymentProviderUnavailable() from provider_error
    return result


def _set_verification_failure(payment, message):
    payment.verification_status = Payment.VerificationStatus.FAILED
    payment.failure_message = message[:500]
    payment.save(
        update_fields=("verification_status", "failure_message", "updated_at")
    )


def _mark_payment_review_required(
    payment,
    intent,
    reason,
    *,
    payment_id=None,
    verification_status=Payment.VerificationStatus.FAILED,
):
    if payment_id and not Payment.objects.filter(
        razorpay_payment_id=payment_id
    ).exclude(pk=payment.pk).exists():
        payment.razorpay_payment_id = payment_id
    payment.status = Payment.Status.CAPTURED
    payment.captured_at = payment.captured_at or timezone.now()
    payment.verification_status = verification_status
    payment.ticket_issuance_status = (
        Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED
    )
    payment.ticket_issuance_failure = reason[:1000]
    payment.failure_message = reason[:500]
    payment.save(
        update_fields=(
            "razorpay_payment_id",
            "status",
            "captured_at",
            "verification_status",
            "ticket_issuance_status",
            "ticket_issuance_failure",
            "failure_message",
            "updated_at",
        )
    )
    intent.status = PaymentIntent.Status.REVIEW_REQUIRED
    intent.save(update_fields=("status", "updated_at"))
    AuditLog.objects.create(
        action="PAYMENT_REVIEW_REQUIRED",
        resource_type="payment",
        resource_id=str(payment.id),
        metadata={
            "payment_id": str(payment.id),
            "payment_intent_id": str(intent.idempotency_key),
            "razorpay_order_id": payment.razorpay_order_id,
            "razorpay_payment_id": payment_id or payment.razorpay_payment_id,
            "event_id": str(intent.event_id),
            "ticket_tier_id": str(intent.ticket_tier_id),
            "amount": payment.amount,
            "currency": payment.currency,
            "reason": reason[:1000],
        },
    )


def _lock_payment_context(order_id):
    from apps.events.models import Event, TicketTier

    try:
        payment_ref = Payment.objects.select_related("intent").get(
            razorpay_order_id=order_id
        )
    except Payment.DoesNotExist as error:
        raise NotFound("The payment order was not found.") from error

    # Keep the same lock order as order creation to prevent payment/event deadlocks.
    Event.objects.select_for_update().get(pk=payment_ref.intent.event_id)
    TicketTier.objects.select_for_update().get(
        pk=payment_ref.intent.ticket_tier_id,
        event_id=payment_ref.intent.event_id,
    )
    intent = PaymentIntent.objects.select_for_update().get(
        pk=payment_ref.intent_id
    )
    payment = Payment.objects.select_for_update().get(pk=payment_ref.pk)
    return payment, intent


def verify_payment(*, order_id, payment_id, signature):
    if not settings.RAZORPAY_KEY_SECRET:
        raise PaymentProviderUnavailable(
            "Razorpay test credentials are not configured."
        )

    try:
        signature_bytes = signature.encode("ascii")
    except UnicodeEncodeError:
        signature_bytes = b""
    expected_signature = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode("utf-8"),
        f"{order_id}|{payment_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    failure = None
    provider_error = None
    review_required = False
    should_issue_tickets = False
    result = None
    with transaction.atomic():
        payment, intent = _lock_payment_context(order_id)
        if (
            payment.status == Payment.Status.CAPTURED
            and payment.ticket_issuance_status
            == Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED
        ):
            if payment.razorpay_payment_id and payment.razorpay_payment_id != payment_id:
                raise PaymentConflict("This order was already verified with another payment.")
            review_required = True
        elif (
            payment.status == Payment.Status.CAPTURED
            and payment.ticket_issuance_status
            == Payment.TicketIssuanceStatus.PENDING
            and payment.verification_status == Payment.VerificationStatus.VERIFIED
            and payment.razorpay_payment_id == payment_id
        ):
            should_issue_tickets = True
        elif payment.verification_status == Payment.VerificationStatus.VERIFIED:
            if payment.razorpay_payment_id != payment_id:
                raise PaymentConflict("This order was already verified with another payment.")
            if (
                payment.ticket_issuance_status
                == Payment.TicketIssuanceStatus.ISSUED
                and intent.registration_id
            ):
                return _intent_result(intent, payment, replayed=True)
            review_required = True
        elif not hmac.compare_digest(
            expected_signature,
            signature_bytes.decode("ascii", errors="ignore"),
        ):
            _set_verification_failure(payment, "Razorpay signature verification failed.")
            failure = "Payment signature verification failed."
        else:
            try:
                client = payment_client()
                provider_order = client.order.fetch(order_id)
                provider_payment = client.payment.fetch(payment_id)
            except razorpay.errors.BadRequestError:
                _set_verification_failure(
                    payment,
                    "The payment provider rejected the order or payment identifier.",
                )
                failure = "The payment details could not be verified."
            except (
                razorpay.errors.GatewayError,
                razorpay.errors.ServerError,
                requests.RequestException,
            ) as error:
                _set_verification_failure(payment, "Payment provider verification failed.")
                provider_error = error
            else:
                order_matches = (
                    provider_order.get("id") == payment.razorpay_order_id
                    and provider_order.get("amount") == payment.amount
                    and provider_order.get("currency") == payment.currency
                )
                payment_matches = (
                    provider_payment.get("id") == payment_id
                    and provider_payment.get("order_id") == payment.razorpay_order_id
                    and provider_payment.get("amount") == payment.amount
                    and provider_payment.get("currency") == payment.currency
                    and provider_payment.get("status") == "captured"
                )
                provider_confirmed_capture = (
                    provider_payment.get("status") == "captured"
                )
                duplicate_payment_id = Payment.objects.filter(
                    razorpay_payment_id=payment_id
                ).exclude(pk=payment.pk).exists()
                duplicate_intent_capture = Payment.objects.filter(
                    intent=intent,
                    status=Payment.Status.CAPTURED,
                    verification_status=Payment.VerificationStatus.VERIFIED,
                ).exclude(pk=payment.pk).exists()
                if provider_confirmed_capture and (
                    not order_matches
                    or not payment_matches
                    or duplicate_payment_id
                    or duplicate_intent_capture
                    or intent.registration_id
                ):
                    reasons = []
                    if not order_matches or not payment_matches:
                        reasons.append(
                            "The captured provider payment does not match the expected order, amount, currency, or payment identifier."
                        )
                    if duplicate_payment_id or duplicate_intent_capture:
                        reasons.append(
                            "A duplicate captured payment was detected for this payment identifier or registration."
                        )
                    if intent.registration_id:
                        reasons.append(
                            "The registration already exists for another payment."
                        )
                    _mark_payment_review_required(
                        payment,
                        intent,
                        " ".join(reasons),
                        payment_id=payment_id,
                    )
                    review_required = True
                elif not order_matches or not payment_matches:
                    _set_verification_failure(
                        payment,
                        "The provider payment did not match the expected order, amount, currency, or captured status.",
                    )
                    failure = "The payment details could not be verified."
                else:
                    payment.razorpay_payment_id = payment_id
                    payment.status = Payment.Status.CAPTURED
                    payment.captured_at = timezone.now()
                    payment.verification_status = Payment.VerificationStatus.VERIFIED
                    payment.verified_at = timezone.now()
                    payment.ticket_issuance_status = Payment.TicketIssuanceStatus.PENDING
                    payment.ticket_issuance_failure = ""
                    payment.failure_message = ""
                    payment.save(
                        update_fields=(
                            "razorpay_payment_id",
                            "status",
                            "captured_at",
                            "verification_status",
                            "verified_at",
                            "ticket_issuance_status",
                            "ticket_issuance_failure",
                            "failure_message",
                            "updated_at",
                        )
                    )
                    intent.status = PaymentIntent.Status.PENDING
                    intent.save(update_fields=("status", "updated_at"))
                    AuditLog.objects.create(
                        action="PAYMENT_CAPTURED",
                        resource_type="payment",
                        resource_id=str(payment.id),
                        metadata={
                            "payment_id": str(payment.id),
                            "payment_intent_id": str(intent.idempotency_key),
                            "razorpay_order_id": order_id,
                            "razorpay_payment_id": payment_id,
                            "event_id": str(intent.event_id),
                            "ticket_tier_id": str(intent.ticket_tier_id),
                            "amount": payment.amount,
                            "currency": payment.currency,
                        },
                    )
                    should_issue_tickets = True

    if provider_error:
        logger.exception("Razorpay verification failed for order %s.", order_id)
        raise PaymentProviderUnavailable() from provider_error
    if failure:
        raise PaymentVerificationError(failure)
    if review_required:
        raise PaymentReviewRequired()

    if should_issue_tickets:
        issue_error = None
        with transaction.atomic():
            payment, intent = _lock_payment_context(order_id)
            if (
                payment.ticket_issuance_status
                == Payment.TicketIssuanceStatus.ISSUED
                and intent.registration_id
            ):
                return _intent_result(intent, payment, replayed=True)
            if (
                payment.ticket_issuance_status
                == Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED
            ):
                raise PaymentReviewRequired()
            if (
                payment.status != Payment.Status.CAPTURED
                or payment.verification_status
                != Payment.VerificationStatus.VERIFIED
            ):
                raise PaymentConflict(
                    "The captured payment is not ready for ticket issuance."
                )
            try:
                with transaction.atomic():
                    registration, tickets = create_registration(
                        event_id=intent.event_id,
                        tier_id=intent.ticket_tier_id,
                        buyer={
                            "name": intent.buyer_name,
                            "email": intent.buyer_email,
                            "phone": intent.buyer_phone,
                            "organization": intent.buyer_organization,
                            "job_title": intent.buyer_job_title,
                        },
                        source=Registration.Source.ONLINE,
                        attendee_names=intent.attendee_names,
                        exclude_payment_intent_id=intent.idempotency_key,
                    )
                    if len(tickets) != intent.ticket_tier.admission_count:
                        raise RuntimeError(
                            "Ticket issuance did not create the required admission count."
                        )
            except Exception as error:
                issue_error = error
                reason = f"Ticket issuance failed ({type(error).__name__}): {error}"
                _mark_payment_review_required(
                    payment,
                    intent,
                    reason,
                    payment_id=payment.razorpay_payment_id,
                    verification_status=Payment.VerificationStatus.VERIFIED,
                )
            else:
                intent.registration = registration
                intent.status = PaymentIntent.Status.VERIFIED
                intent.save(
                    update_fields=("registration", "status", "updated_at")
                )
                payment.ticket_issuance_status = (
                    Payment.TicketIssuanceStatus.ISSUED
                )
                payment.ticket_issuance_failure = ""
                payment.failure_message = ""
                payment.save(
                    update_fields=(
                        "ticket_issuance_status",
                        "ticket_issuance_failure",
                        "failure_message",
                        "updated_at",
                    )
                )
                AuditLog.objects.create(
                    action="PAYMENT_TICKETS_ISSUED",
                    resource_type="payment",
                    resource_id=str(payment.id),
                    metadata={
                        "payment_id": str(payment.id),
                        "payment_intent_id": str(intent.idempotency_key),
                        "registration_id": str(registration.id),
                        "ticket_ids": [str(ticket.id) for ticket in tickets],
                    },
                )
                serialized = RegistrationSerializer(registration).data
                ticket_data = serialized["tickets"]
                result = {
                    "payment_verified": True,
                    "order_id": order_id,
                    "payment_id": payment_id,
                    "registration": serialized,
                    "ticket": ticket_data[0],
                    "tickets": ticket_data,
                    "replayed": False,
                }

        if issue_error:
            logger.exception(
                "Captured payment %s could not issue tickets; admin review is required.",
                payment.id,
                exc_info=(
                    type(issue_error),
                    issue_error,
                    issue_error.__traceback__,
                ),
            )
            raise PaymentReviewRequired() from issue_error

    if intent.registration_id:
        result["delivery_status"] = TicketDelivery.objects.filter(
            ticket__registration_id=intent.registration_id
        ).values_list("status", flat=True).first()
    return result


def record_payment_failure(*, order_id):
    with transaction.atomic():
        payment, _ = _lock_payment_context(order_id)
        if payment.verification_status == Payment.VerificationStatus.VERIFIED:
            return payment
        payment.failure_message = (
            "The browser reported a failed payment attempt; provider status is unverified."
        )
        payment.save(update_fields=("failure_message", "updated_at"))
        return payment


def get_payment_review_dashboard():
    captured_payment_queryset = (
        Payment.objects.filter(status=Payment.Status.CAPTURED)
        .select_related("intent__event", "intent__ticket_tier", "intent__registration")
        .annotate(
            ticket_count=Count("intent__registration__tickets", distinct=True),
            captured_for_intent=Count(
                "intent__payments",
                filter=Q(intent__payments__status=Payment.Status.CAPTURED),
                distinct=True,
            ),
        )
    )
    needs_review = (
        Q(ticket_issuance_status__in=(
            Payment.TicketIssuanceStatus.PENDING,
            Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED,
        ))
        | ~Q(verification_status=Payment.VerificationStatus.VERIFIED)
        | Q(intent__registration__isnull=True)
        | ~Q(ticket_count=F("intent__ticket_tier__admission_count"))
        | Q(captured_for_intent__gt=1)
    )
    payment_review_queryset = captured_payment_queryset.filter(needs_review)
    captured_payments_raw = list(payment_review_queryset.order_by("-updated_at")[:201])
    has_more_payments = len(captured_payments_raw) > 200
    captured_payments = captured_payments_raw[:200]
    payment_cases = []
    issue_counts_agg = captured_payment_queryset.aggregate(
        PAYMENT_REVIEW_REQUIRED=Count(
            "id",
            filter=(
                Q(ticket_issuance_status__in=(
                    Payment.TicketIssuanceStatus.PENDING,
                    Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED,
                ))
                | ~Q(verification_status=Payment.VerificationStatus.VERIFIED)
                | Q(intent__registration__isnull=True)
                | ~Q(ticket_count=F("intent__ticket_tier__admission_count"))
            ),
        ),
        TICKET_ISSUANCE_FAILED=Count(
            "id",
            filter=Q(ticket_issuance_status=Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED),
        ),
        PAYMENT_CAPTURED_WITHOUT_TICKET=Count(
            "id",
            filter=Q(intent__registration__isnull=True) | Q(ticket_count=0),
        ),
        PAYMENT_CAPTURED_WITH_INCOMPLETE_REGISTRATION=Count(
            "id",
            filter=(
                Q(intent__registration__isnull=True)
                | ~Q(ticket_count=F("intent__ticket_tier__admission_count"))
            ),
        ),
        DUPLICATE_PAYMENT=Count(
            "id",
            filter=Q(captured_for_intent__gt=1),
        ),
    )
    issue_counts = {
        "PAYMENT_REVIEW_REQUIRED": issue_counts_agg["PAYMENT_REVIEW_REQUIRED"] or 0,
        "TICKET_ISSUANCE_FAILED": issue_counts_agg["TICKET_ISSUANCE_FAILED"] or 0,
        "PAYMENT_CAPTURED_WITHOUT_TICKET": issue_counts_agg["PAYMENT_CAPTURED_WITHOUT_TICKET"] or 0,
        "PAYMENT_CAPTURED_WITH_INCOMPLETE_REGISTRATION": issue_counts_agg["PAYMENT_CAPTURED_WITH_INCOMPLETE_REGISTRATION"] or 0,
        "DUPLICATE_PAYMENT": issue_counts_agg["DUPLICATE_PAYMENT"] or 0,
    }
    for payment in captured_payments:
        intent = payment.intent
        registration = intent.registration
        issue_codes = []
        if payment.ticket_issuance_status != Payment.TicketIssuanceStatus.ISSUED:
            issue_codes.append("PAYMENT_REVIEW_REQUIRED")
        if payment.ticket_issuance_status == Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED:
            issue_codes.append("TICKET_ISSUANCE_FAILED")
        if registration is None or payment.ticket_count == 0:
            issue_codes.append("PAYMENT_CAPTURED_WITHOUT_TICKET")
        if (
            registration is None
            or payment.ticket_count != intent.ticket_tier.admission_count
        ):
            issue_codes.append("PAYMENT_CAPTURED_WITH_INCOMPLETE_REGISTRATION")
        if payment.captured_for_intent > 1:
            issue_codes.append("DUPLICATE_PAYMENT")
        if payment.verification_status != Payment.VerificationStatus.VERIFIED:
            issue_codes.append("PAYMENT_REVIEW_REQUIRED")
        if not issue_codes:
            continue
        payment_cases.append(
            {
                "payment_id": str(payment.id),
                "payment_intent_id": str(intent.idempotency_key),
                "order_id": payment.razorpay_order_id,
                "provider_payment_id": payment.razorpay_payment_id,
                "amount": payment.amount,
                "currency": payment.currency,
                "event_id": str(intent.event_id),
                "event_name": intent.event.name,
                "ticket_tier_id": str(intent.ticket_tier_id),
                "ticket_tier_name": intent.ticket_tier.name,
                "buyer_name": intent.buyer_name,
                "buyer_email": intent.buyer_email,
                "registration_id": str(registration.id) if registration else None,
                "ticket_count": payment.ticket_count,
                "expected_ticket_count": intent.ticket_tier.admission_count,
                "verification_status": payment.verification_status,
                "ticket_issuance_status": payment.ticket_issuance_status,
                "failure": payment.ticket_issuance_failure or payment.failure_message,
                "issue_codes": sorted(set(issue_codes)),
                "updated_at": payment.updated_at.isoformat(),
            }
        )

    valid_payment_intents = PaymentIntent.objects.filter(
        registration_id=OuterRef("pk"),
        status=PaymentIntent.Status.VERIFIED,
        payments__status=Payment.Status.CAPTURED,
        payments__verification_status=Payment.VerificationStatus.VERIFIED,
        payments__ticket_issuance_status=Payment.TicketIssuanceStatus.ISSUED,
    )
    registrations_without_valid_payment_queryset = (
        Registration.objects.filter(source=Registration.Source.ONLINE)
        .annotate(
            ticket_count=Count("tickets", distinct=True),
            has_valid_payment=Exists(valid_payment_intents),
        )
        .filter(has_valid_payment=False, ticket_count__gt=0)
        .select_related("event", "ticket_tier")
        .order_by("-created_at")
    )
    registration_rows = list(registrations_without_valid_payment_queryset[:201])
    has_more_registrations = len(registration_rows) > 200
    registration_cases = [
        {
            "registration_id": str(registration.id),
            "event_id": str(registration.event_id),
            "event_name": registration.event.name,
            "ticket_tier_id": str(registration.ticket_tier_id),
            "ticket_tier_name": registration.ticket_tier.name,
            "buyer_name": registration.buyer_name,
            "buyer_email": registration.buyer_email,
            "ticket_count": registration.ticket_count,
            "expected_ticket_count": registration.ticket_tier.admission_count,
            "created_at": registration.created_at.isoformat(),
            "issue_code": "TICKET_WITHOUT_VALID_PAYMENT",
        }
        for registration in registration_rows[:200]
    ]
    if has_more_registrations:
        issue_counts["TICKET_WITHOUT_VALID_PAYMENT"] = (
            registrations_without_valid_payment_queryset.count()
        )
    else:
        issue_counts["TICKET_WITHOUT_VALID_PAYMENT"] = len(registration_rows)
    return {
        "issue_counts": issue_counts,
        "payments": payment_cases,
        "registrations_without_valid_payment": registration_cases,
        "has_more_payments": has_more_payments,
        "has_more_registrations": has_more_registrations,
    }
