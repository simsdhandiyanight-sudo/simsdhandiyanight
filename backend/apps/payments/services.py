import hashlib
import hmac
import json
import logging
import re
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, F, OuterRef, Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException, NotFound

from apps.audit.models import AuditLog
from apps.registrations.models import Registration
from apps.registrations.serializers import RegistrationSerializer
from apps.registrations.services import (
    IdempotencyConflict,
    RegistrationConflict,
    create_registration,
)
from apps.tickets.models import Ticket
from .models import (
    Payment,
    PaymentIntent,
    PaymentVerificationAttempt,
    TicketDelivery,
)

logger = logging.getLogger(__name__)
ORDER_LIFETIME = timedelta(minutes=15)
ADDITIONAL_CHARGE_PER_ADMISSION_PAISE = 400
PAYU_TIMEOUT = (5, 15)
PAYU_MAX_AUTOMATIC_VERIFICATION_ATTEMPTS = 5
PAYU_MAX_TOTAL_VERIFICATION_ATTEMPTS = 8
PAYU_INITIAL_RETRY_DELAY_SECONDS = 15
PAYU_MAX_RETRY_DELAY_SECONDS = 900


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
    default_detail = "The payment provider is temporarily unavailable. Retry safely."
    default_code = "PAYMENT_PROVIDER_UNAVAILABLE"


class PaymentReviewRequired(APIException):
    status_code = 409
    default_detail = (
        "Payment verification or ticket issuance requires administrator review. "
        "No tickets have been issued. Do not retry payment; contact event support "
        "with the transaction reference."
    )
    default_code = "PAYMENT_REVIEW_REQUIRED"


class PayUVerificationFailure(PaymentProviderUnavailable):
    def __init__(self, observation):
        self.observation = observation
        super().__init__(
            "PayU verification is unresolved. The booking remains unconfirmed."
        )


def require_payu_configuration():
    if not settings.PAYU_MERCHANT_KEY or not settings.PAYU_MERCHANT_SALT:
        raise PaymentProviderUnavailable(
            "PayU payments are not configured for this event."
        )
    if settings.PAYU_ENVIRONMENT not in ("test", "production"):
        raise PaymentProviderUnavailable(
            "PayU environment must be configured as test or production."
        )


def payu_payment_url():
    return (
        "https://secure.payu.in/_payment"
        if settings.PAYU_ENVIRONMENT == "production"
        else "https://test.payu.in/_payment"
    )


def payu_verification_url():
    return (
        "https://info.payu.in/merchant/postservice.php?form=2"
        if settings.PAYU_ENVIRONMENT == "production"
        else "https://test.payu.in/merchant/postservice.php?form=2"
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


def payu_request_hash_for_params(params):
    fields = [
        params["key"],
        params["txnid"],
        params["amount"],
        params["productinfo"],
        params["firstname"],
        params["email"],
        params.get("udf1", ""),
        params.get("udf2", ""),
        params.get("udf3", ""),
        params.get("udf4", ""),
        params.get("udf5", ""),
        "",
        "",
        "",
        "",
        "",
        settings.PAYU_MERCHANT_SALT,
    ]
    return hashlib.sha512("|".join(fields).encode("utf-8")).hexdigest()


def payu_response_hash(payload):
    fields = [
        settings.PAYU_MERCHANT_SALT,
        payload.get("status", ""),
        "",
        "",
        "",
        "",
        "",
        payload.get("udf5", ""),
        payload.get("udf4", ""),
        payload.get("udf3", ""),
        payload.get("udf2", ""),
        payload.get("udf1", ""),
        payload.get("email", ""),
        payload.get("firstname", ""),
        payload.get("productinfo", ""),
        payload.get("amount", ""),
        payload.get("txnid", ""),
        payload.get("key", ""),
    ]
    return hashlib.sha512("|".join(fields).encode("utf-8")).hexdigest()


def build_payu_payment_params(payment, intent, *, success_url, failure_url):
    require_payu_configuration()
    if not success_url or not failure_url:
        raise PaymentProviderUnavailable(
            "PayU callback URLs are not configured."
        )
    email = intent.buyer_email.strip().lower()
    if len(email) > 50:
        raise serializers.ValidationError(
            {"buyer.email": "PayU checkout supports email addresses up to 50 characters."}
        )
    if len(intent.buyer_phone) > 50:
        raise serializers.ValidationError(
            {"buyer.phone": "The phone number exceeds PayU's supported length."}
        )

    name_parts = intent.buyer_name.strip().split(maxsplit=1)
    first_name = name_parts[0][:60]
    last_name = name_parts[1][:60] if len(name_parts) > 1 else ""
    params = {
        "key": settings.PAYU_MERCHANT_KEY,
        "txnid": payment.provider_order_id,
        "amount": f"{Decimal(payment.amount) / 100:.2f}",
        "productinfo": "Dhandiya Night Tickets",
        "firstname": first_name,
        "lastname": last_name,
        "email": email,
        "phone": intent.buyer_phone,
        "surl": success_url,
        "furl": failure_url,
        "udf1": str(intent.idempotency_key),
        "udf2": str(payment.id),
        "udf3": "",
        "udf4": "",
        "udf5": "",
    }
    params["hash"] = payu_request_hash_for_params(params)
    return params


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
            "payment_status": payment.status,
            "order_id": payment.provider_order_id,
            "payment_id": payment.provider_payment_id,
            "registration": serialized,
            "ticket": serialized["tickets"][0],
            "tickets": serialized["tickets"],
            "delivery_status": delivery_status,
            "replayed": replayed,
        }
    return {
        "payment_verified": False,
        "payment_status": payment.status,
        "order_id": payment.provider_order_id,
        "amount": payment.amount,
        "currency": payment.currency,
        "display_amount": float(payment.amount) / 100,
        "replayed": replayed,
    }


def _checkout_result(intent, payment, *, replayed, success_url, failure_url):
    result = _intent_result(intent, payment, replayed=replayed)
    if not result["payment_verified"]:
        result.update(
            {
                "checkout_url": payu_payment_url(),
                "payment_params": build_payu_payment_params(
                    payment,
                    intent,
                    success_url=success_url,
                    failure_url=failure_url,
                ),
            }
        )
    return result


def create_payment_order(
    *,
    idempotency_key,
    event_id,
    tier_id,
    buyer,
    attendee_names,
    success_url,
    failure_url,
):
    from apps.events.models import Event, TicketTier

    require_payu_configuration()
    request_hash = payment_request_hash(
        event_id=event_id,
        tier_id=tier_id,
        buyer=buyer,
        attendee_names=attendee_names,
    )

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
        if tier.currency != "INR":
            raise RegistrationConflict("PayU checkout is currently available for INR offers only.")
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
            intent = PaymentIntent.objects.select_for_update().get(pk=idempotency_key)
            if intent.request_hash != request_hash:
                raise IdempotencyConflict()
            is_new_intent = False
            verified_payment = intent.payments.filter(
                verification_status=Payment.VerificationStatus.VERIFIED
            ).first()
            if intent.registration_id and verified_payment:
                return _intent_result(intent, verified_payment, replayed=True)

        if not is_new_intent:
            current_payment = intent.payments.order_by("-created_at").first()
            if (
                current_payment
                and current_payment.status == Payment.Status.CAPTURED
            ):
                raise PaymentReviewRequired()
            if (
                current_payment
                and current_payment.status in (Payment.Status.CREATED, Payment.Status.PENDING)
                and current_payment.expires_at > timezone.now()
            ):
                return _checkout_result(
                    intent,
                    current_payment,
                    replayed=True,
                    success_url=success_url,
                    failure_url=failure_url,
                )
            if (
                current_payment
                and current_payment.status == Payment.Status.CREATING
                and current_payment.created_at > timezone.now() - timedelta(minutes=2)
            ):
                raise PaymentConflict(
                    "The payment request is still being prepared; retry shortly."
                )

        active_ticket_count = (
            Ticket.objects.filter(registration__event=event)
            .exclude(status=Ticket.Status.CANCELLED)
            .count()
        )
        from django.db.models import Sum

        # Sum the reserved admissions, not the number of active reservations.
        reserved_count = (
            PaymentIntent.objects.filter(
                event=event,
            ).filter(
                Q(
                    status=PaymentIntent.Status.PENDING,
                    expires_at__gt=timezone.now(),
                )
                | Q(status=PaymentIntent.Status.REVIEW_REQUIRED)
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
        amount = (
            int(tier.price * 100)
            + ADDITIONAL_CHARGE_PER_ADMISSION_PAISE * tier.admission_count
        )
        payment = Payment.objects.create(
            intent=intent,
            provider=Payment.Provider.PAYU,
            provider_order_id=uuid.uuid4().hex[:24],
            amount=amount,
            currency=tier.currency,
            status=Payment.Status.PENDING,
            expires_at=expires_at,
        )
        result = _checkout_result(
            intent,
            payment,
            replayed=False,
            success_url=success_url,
            failure_url=failure_url,
        )
        return result


def _lock_payment_context(txnid):
    from apps.events.models import Event, TicketTier

    try:
        payment_ref = Payment.objects.select_related("intent").get(
            provider_order_id=txnid,
            provider=Payment.Provider.PAYU,
        )
    except Payment.DoesNotExist as error:
        raise NotFound("The PayU transaction was not found.") from error
    Event.objects.select_for_update().get(pk=payment_ref.intent.event_id)
    TicketTier.objects.select_for_update().get(
        pk=payment_ref.intent.ticket_tier_id,
        event_id=payment_ref.intent.event_id,
    )
    intent = PaymentIntent.objects.select_for_update().get(pk=payment_ref.intent_id)
    payment = Payment.objects.select_for_update().get(pk=payment_ref.pk)
    return payment, intent


def _amount_matches(value, expected_paise):
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return False
    return amount == (Decimal(expected_paise) / 100).quantize(Decimal("0.01"))


def _safe_payu_message(value):
    message = str(value or "")
    for secret in (settings.PAYU_MERCHANT_KEY, settings.PAYU_MERCHANT_SALT):
        if secret:
            message = message.replace(secret, "[redacted]")
    message = re.sub(
        r"(?i)\b(key|salt|hash)\b\s*[:=]\s*\S+",
        r"\1=[redacted]",
        message,
    )
    return message[:300]


def _request_payu_verification(payment):
    require_payu_configuration()
    txnid = payment.provider_order_id
    command = "verify_payment"
    digest = hashlib.sha512(
        (
            f"{settings.PAYU_MERCHANT_KEY}|{command}|{txnid}|"
            f"{settings.PAYU_MERCHANT_SALT}"
        ).encode("utf-8")
    ).hexdigest()
    observation = {
        "http_status": None,
        "api_status": "",
        "api_message": "",
        "response_schema_valid": False,
        "transaction_found": False,
        "returned_txnid": "",
        "returned_status": "",
        "returned_unmappedstatus": "",
        "returned_amount": "",
        "transaction_id_matches": False,
        "amount_matches": False,
        "booking_fields_match": False,
        "currency_matches": None,
        "outcome": PaymentVerificationAttempt.Outcome.NETWORK_ERROR,
        "retry_after": None,
    }
    try:
        response = requests.post(
            payu_verification_url(),
            data={
                "key": settings.PAYU_MERCHANT_KEY,
                "command": command,
                "var1": txnid,
                "hash": digest,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=PAYU_TIMEOUT,
        )
        status_code = response.status_code
        observation["http_status"] = (
            status_code if type(status_code) is int else None
        )
    except requests.RequestException as error:
        logger.warning(
            "PayU Verify Payment request failed.",
            extra={
                "payment_id": str(payment.id),
                "environment": settings.PAYU_ENVIRONMENT,
                "error_type": type(error).__name__,
            },
        )
        raise PayUVerificationFailure(observation) from error

    try:
        payload = response.json()
    except ValueError as error:
        observation["outcome"] = PaymentVerificationAttempt.Outcome.MALFORMED
        logger.warning(
            "PayU Verify Payment returned non-JSON content.",
            extra={
                "payment_id": str(payment.id),
                "environment": settings.PAYU_ENVIRONMENT,
                "http_status": response.status_code,
                "response_bytes": len(response.content),
            },
        )
        raise PayUVerificationFailure(observation) from error

    if not isinstance(payload, dict):
        observation["outcome"] = PaymentVerificationAttempt.Outcome.MALFORMED
        logger.warning(
            "PayU Verify Payment returned an unexpected JSON schema.",
            extra={
                "payment_id": str(payment.id),
                "environment": settings.PAYU_ENVIRONMENT,
                "http_status": response.status_code,
                "response_type": type(payload).__name__,
            },
        )
        raise PayUVerificationFailure(observation)

    observation["api_status"] = str(payload.get("status", ""))[:24]
    observation["api_message"] = _safe_payu_message(
        payload.get("msg")
        or payload.get("message")
        or payload.get("error_Message")
        or payload.get("error")
    )
    if not response.ok:
        message = observation["api_message"].lower()
        if response.status_code == 429:
            observation["outcome"] = PaymentVerificationAttempt.Outcome.API_ERROR
            retry_header = response.headers.get("Retry-After", "")
            if retry_header.isdigit():
                observation["retry_after"] = timezone.now() + timedelta(
                    seconds=min(int(retry_header), PAYU_MAX_RETRY_DELAY_SECONDS)
                )
        elif response.status_code in (401, 403) or any(
            term in message for term in ("invalid hash", "invalid key", "authentication")
        ):
            observation["outcome"] = PaymentVerificationAttempt.Outcome.AUTH_ERROR
        elif response.status_code in (400, 422):
            observation["outcome"] = PaymentVerificationAttempt.Outcome.INVALID_REQUEST
        else:
            observation["outcome"] = PaymentVerificationAttempt.Outcome.API_ERROR
        logger.warning(
            "PayU Verify Payment returned an HTTP error.",
            extra={
                "payment_id": str(payment.id),
                "environment": settings.PAYU_ENVIRONMENT,
                "http_status": response.status_code,
                "api_status": observation["api_status"],
                "api_message": observation["api_message"],
                "outcome": observation["outcome"],
            },
        )
        raise PayUVerificationFailure(observation)

    if observation["api_status"] != "1":
        message = observation["api_message"].lower()
        if any(term in message for term in ("invalid hash", "invalid key", "authentication")):
            observation["outcome"] = PaymentVerificationAttempt.Outcome.AUTH_ERROR
        elif "not found" in message or "0 out of" in message:
            observation["outcome"] = PaymentVerificationAttempt.Outcome.TRANSACTION_NOT_FOUND
        else:
            observation["outcome"] = PaymentVerificationAttempt.Outcome.API_ERROR
        logger.warning(
            "PayU Verify Payment returned an API-level failure.",
            extra={
                "payment_id": str(payment.id),
                "environment": settings.PAYU_ENVIRONMENT,
                "http_status": response.status_code,
                "api_status": observation["api_status"],
                "api_message": observation["api_message"],
                "outcome": observation["outcome"],
            },
        )
        raise PayUVerificationFailure(observation)

    details = payload.get("transaction_details")
    if not isinstance(details, dict):
        observation["outcome"] = PaymentVerificationAttempt.Outcome.MALFORMED
        logger.warning(
            "PayU Verify Payment response is missing transaction_details.",
            extra={
                "payment_id": str(payment.id),
                "environment": settings.PAYU_ENVIRONMENT,
                "http_status": response.status_code,
                "api_status": observation["api_status"],
            },
        )
        raise PayUVerificationFailure(observation)

    observation["response_schema_valid"] = True
    transaction_details = details.get(txnid)
    if not isinstance(transaction_details, dict):
        observation["outcome"] = PaymentVerificationAttempt.Outcome.TRANSACTION_NOT_FOUND
        logger.warning(
            "PayU Verify Payment did not find the requested transaction.",
            extra={
                "payment_id": str(payment.id),
                "environment": settings.PAYU_ENVIRONMENT,
                "http_status": response.status_code,
                "api_status": observation["api_status"],
                "api_message": observation["api_message"],
                "transaction_found": False,
                "requested_txnid": txnid,
            },
        )
        raise PayUVerificationFailure(observation)

    observation["transaction_found"] = True
    observation["returned_txnid"] = str(transaction_details.get("txnid", ""))[:64]
    observation["returned_status"] = str(transaction_details.get("status", ""))[:40]
    observation["returned_unmappedstatus"] = str(
        transaction_details.get("unmappedstatus", "")
    )[:40]
    amount = transaction_details.get(
        "amount",
        transaction_details.get("amt", transaction_details.get("transaction_amount")),
    )
    observation["returned_amount"] = str(amount or "")[:40]
    match_details = _provider_details_match_fields(payment, payment.intent, transaction_details)
    observation.update(
        {
            "transaction_id_matches": match_details["transaction_id"],
            "amount_matches": match_details["amount"],
            "booking_fields_match": match_details["booking_fields"],
            "currency_matches": match_details["currency"],
            "outcome": (
                PaymentVerificationAttempt.Outcome.CAPTURED
                if _normalize_provider_status(transaction_details) == "success"
                and all(
                    match_details[key]
                    for key in ("transaction_id", "amount", "booking_fields", "currency")
                )
                else PaymentVerificationAttempt.Outcome.PENDING
                if _normalize_provider_status(transaction_details) == "pending"
                else PaymentVerificationAttempt.Outcome.FAILED
                if _normalize_provider_status(transaction_details) == "failed"
                else PaymentVerificationAttempt.Outcome.MISMATCH
            ),
        }
    )
    logger.info(
        "PayU Verify Payment response inspected.",
        extra={
            "payment_id": str(payment.id),
            "environment": settings.PAYU_ENVIRONMENT,
            "http_status": response.status_code,
            "api_status": observation["api_status"],
            "api_message": observation["api_message"],
            "transaction_found": True,
            "returned_txnid": observation["returned_txnid"],
            "returned_status": observation["returned_status"],
            "returned_unmappedstatus": observation["returned_unmappedstatus"],
            "returned_amount": observation["returned_amount"],
            "expected_amount_paise": payment.amount,
            "match_details": match_details,
        },
    )
    if observation["returned_status"].lower() == "not found":
        observation["outcome"] = PaymentVerificationAttempt.Outcome.TRANSACTION_NOT_FOUND
        raise PayUVerificationFailure(observation)
    if _normalize_provider_status(transaction_details) == "success" and not all(
        match_details[key]
        for key in ("transaction_id", "amount", "booking_fields", "currency")
    ):
        observation["outcome"] = PaymentVerificationAttempt.Outcome.MISMATCH
        raise PayUVerificationFailure(observation)
    return transaction_details, observation


def _normalize_provider_status(details):
    status_value = str(details.get("status", "")).strip().lower()
    unmapped = str(details.get("unmappedstatus", "")).strip().lower()
    if status_value == "success" and unmapped in ("captured", "settled"):
        return "success"
    if status_value in ("failure", "failed", "cancelled", "canceled"):
        return "failed"
    if unmapped in ("failed", "failure", "bounced", "dropped", "usercancelled"):
        return "failed"
    return "pending"


def _provider_details_match_fields(payment, intent, details):
    provider_txnid = str(details.get("txnid", ""))
    amount = details.get(
        "amount",
        details.get("amt", details.get("transaction_amount")),
    )
    name_parts = intent.buyer_name.strip().split(maxsplit=1)
    expected_first_name = name_parts[0][:60] if name_parts else ""
    optional_fields_match = all(
        not str(details.get(field, "") or "").strip()
        or (
            str(details.get(field, "")).strip().lower()
            == expected.lower()
            if field == "email"
            else str(details.get(field, "")).strip() == expected
        )
        for field, expected in (
            ("firstname", expected_first_name),
            ("email", intent.buyer_email.strip()),
            ("udf1", str(intent.idempotency_key)),
            ("udf2", str(payment.id)),
        )
    )
    currency = details.get("currency", details.get("currency_code"))
    currency_matches = (
        None
        if currency in (None, "")
        else str(currency).strip().upper() == payment.currency.upper()
    )
    return {
        "transaction_id": provider_txnid == payment.provider_order_id,
        "amount": _amount_matches(amount, payment.amount),
        "booking_fields": (
            (
                not str(details.get("productinfo", "") or "").strip()
                or str(details.get("productinfo")).strip()
                == "Dhandiya Night Tickets"
            )
            and optional_fields_match
        ),
        "currency": currency_matches is not False,
    }


def _provider_details_match(payment, intent, details):
    return all(
        _provider_details_match_fields(payment, intent, details)[key]
        for key in ("transaction_id", "amount", "booking_fields", "currency")
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
        provider_payment_id=payment_id
    ).exclude(pk=payment.pk).exists():
        payment.provider_payment_id = payment_id
    payment.status = Payment.Status.CAPTURED
    payment.provider_status = "success"
    payment.captured_at = payment.captured_at or timezone.now()
    payment.verification_status = verification_status
    payment.ticket_issuance_status = Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED
    payment.ticket_issuance_failure = reason[:1000]
    payment.failure_message = reason[:500]
    payment.save(
        update_fields=(
            "provider_payment_id",
            "provider_status",
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
            "provider": Payment.Provider.PAYU,
            "provider_order_id": payment.provider_order_id,
            "provider_payment_id": payment_id or payment.provider_payment_id,
            "event_id": str(intent.event_id),
            "ticket_tier_id": str(intent.ticket_tier_id),
            "amount": payment.amount,
            "currency": payment.currency,
            "reason": reason[:1000],
        },
    )


def _verification_retry_delay(attempt_number):
    seconds = min(
        PAYU_INITIAL_RETRY_DELAY_SECONDS * (2 ** (attempt_number - 1)),
        PAYU_MAX_RETRY_DELAY_SECONDS,
    )
    return timedelta(seconds=seconds)


def _record_verification_observation(attempt, observation):
    attempt.http_status = observation.get("http_status")
    attempt.api_status = str(observation.get("api_status", ""))[:24]
    attempt.api_message = _safe_payu_message(observation.get("api_message", ""))
    attempt.response_schema_valid = observation.get("response_schema_valid")
    attempt.transaction_found = observation.get("transaction_found")
    attempt.returned_txnid = str(observation.get("returned_txnid", ""))[:64]
    attempt.returned_status = str(observation.get("returned_status", ""))[:40]
    attempt.returned_unmappedstatus = str(
        observation.get("returned_unmappedstatus", "")
    )[:40]
    attempt.returned_amount = str(observation.get("returned_amount", ""))[:40]
    attempt.transaction_id_matches = observation.get("transaction_id_matches")
    attempt.amount_matches = observation.get("amount_matches")
    attempt.booking_fields_match = observation.get("booking_fields_match")
    attempt.currency_matches = observation.get("currency_matches")
    if observation.get("retry_after") is not None:
        attempt.retry_after = observation["retry_after"]
    attempt.outcome = observation.get(
        "outcome",
        PaymentVerificationAttempt.Outcome.MALFORMED,
    )
    attempt.save()


def _payment_status_result(payment, *, replayed=True):
    payment.refresh_from_db()
    result = _intent_result(payment.intent, payment, replayed=replayed)
    result.update(
        {
            "verification_status": payment.verification_status,
            "ticket_issuance_status": payment.ticket_issuance_status,
            "verification_attempts": payment.verification_attempt_count,
            "next_verification_at": (
                payment.next_verification_at.isoformat()
                if payment.next_verification_at
                else None
            ),
        }
    )
    if (
        payment.ticket_issuance_status
        == Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED
    ):
        result["verification_message"] = (
            "Payment needs review. No tickets have been issued. Do not pay again; "
            "contact event support with the transaction reference."
        )
    elif payment.status == Payment.Status.FAILED:
        result["verification_message"] = (
            "PayU confirmed that this transaction failed. No tickets have been issued."
        )
    else:
        result["verification_message"] = (
            "PayU has not yet confirmed a captured payment. No tickets have been issued."
        )
    return result


def _verify_payu_payment(payment_id, *, trigger, force=False, requested_by=None):
    attempt = None
    issue_verified_payment = False
    retries_exhausted = False
    with transaction.atomic():
        try:
            payment = Payment.objects.select_for_update().select_related(
                "intent"
            ).get(pk=payment_id, provider=Payment.Provider.PAYU)
        except Payment.DoesNotExist as error:
            raise NotFound("The PayU transaction was not found.") from error

        if (
            payment.verification_status == Payment.VerificationStatus.VERIFIED
            and payment.ticket_issuance_status == Payment.TicketIssuanceStatus.ISSUED
            and payment.intent.registration_id
        ):
            return _intent_result(payment.intent, payment, replayed=True)
        if payment.verification_status == Payment.VerificationStatus.VERIFIED:
            if (
                payment.ticket_issuance_status
                == Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED
                and trigger != PaymentVerificationAttempt.Trigger.ADMIN
            ):
                return _payment_status_result(payment)
            issue_verified_payment = True
        elif (
            payment.status == Payment.Status.FAILED
            and payment.verification_status == Payment.VerificationStatus.FAILED
        ):
            return _payment_status_result(payment)
        else:
            attempt_limit = (
                PAYU_MAX_TOTAL_VERIFICATION_ATTEMPTS
                if force
                else PAYU_MAX_AUTOMATIC_VERIFICATION_ATTEMPTS
            )
            if payment.verification_attempt_count >= attempt_limit:
                payment.ticket_issuance_status = (
                    Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED
                )
                payment.failure_message = (
                    "PayU verification retries are exhausted. Do not pay again; "
                    "an administrator must reconcile this transaction."
                )
                payment.save(
                    update_fields=(
                        "ticket_issuance_status",
                        "failure_message",
                        "updated_at",
                    )
                )
                intent.status = PaymentIntent.Status.REVIEW_REQUIRED
                intent.save(update_fields=("status", "updated_at"))
                AuditLog.objects.create(
                    action="PAYU_VERIFICATION_RETRIES_EXHAUSTED",
                    resource_type="payment",
                    resource_id=str(payment.id),
                    metadata={
                        "payment_id": str(payment.id),
                        "provider_order_id": payment.provider_order_id,
                        "attempt_count": payment.verification_attempt_count,
                        "environment": settings.PAYU_ENVIRONMENT,
                    },
                )
                retries_exhausted = True
            else:
                now = timezone.now()
                if (
                    not force
                    and payment.next_verification_at
                    and payment.next_verification_at > now
                ):
                    return _payment_status_result(payment)

                attempt_number = payment.verification_attempt_count + 1
                payment.verification_attempt_count = attempt_number
                payment.last_verification_attempt_at = now
                payment.next_verification_at = now + _verification_retry_delay(
                    attempt_number
                )
                payment.save(
                    update_fields=(
                        "verification_attempt_count",
                        "last_verification_attempt_at",
                        "next_verification_at",
                        "updated_at",
                    )
                )
                attempt = PaymentVerificationAttempt.objects.create(
                    payment=payment,
                    requested_by=requested_by,
                    trigger=trigger,
                    attempt_number=attempt_number,
                    environment=settings.PAYU_ENVIRONMENT,
                    expected_amount=payment.amount,
                    retry_after=payment.next_verification_at,
                )

    if retries_exhausted:
        raise PaymentReviewRequired(
            "PayU verification retries are exhausted. The transaction is retained "
            "for administrator review; do not pay again."
        )
    if issue_verified_payment:
        return _issue_verified_payment(
            payment.provider_order_id,
            allow_review_retry=trigger == PaymentVerificationAttempt.Trigger.ADMIN,
        )
    if attempt is None:
        return _payment_status_result(payment)

    try:
        details, observation = _request_payu_verification(payment)
    except PayUVerificationFailure as error:
        observation = error.observation
        _record_verification_observation(attempt, observation)
        with transaction.atomic():
            locked_payment, intent = _lock_payment_context(payment.provider_order_id)
            retry_after = observation.get("retry_after")
            if retry_after and (
                not locked_payment.next_verification_at
                or retry_after > locked_payment.next_verification_at
            ):
                locked_payment.next_verification_at = retry_after
                attempt.retry_after = retry_after
                attempt.save(update_fields=("retry_after",))
            locked_payment.failure_message = (
                observation.get("api_message")
                or "PayU verification is unresolved. Retry is scheduled."
            )[:500]
            locked_payment.save(
                update_fields=(
                    "failure_message",
                    "next_verification_at",
                    "updated_at",
                )
            )
            if (
                observation.get("outcome")
                == PaymentVerificationAttempt.Outcome.MISMATCH
            ):
                _mark_payment_review_required(
                    locked_payment,
                    intent,
                    "PayU reported a captured transaction, but its returned "
                    "transaction or booking details did not match the stored order.",
                    payment_id=locked_payment.provider_payment_id,
                    verification_status=Payment.VerificationStatus.FAILED,
                )
        return _payment_status_result(payment)

    _record_verification_observation(attempt, observation)
    try:
        result = _apply_provider_verification(payment.provider_order_id, details)
    except PaymentReviewRequired:
        if (
            observation.get("outcome")
            == PaymentVerificationAttempt.Outcome.CAPTURED
        ):
            attempt.outcome = PaymentVerificationAttempt.Outcome.CAPTURED
            attempt.save(update_fields=("outcome",))
        raise

    payment.refresh_from_db()
    return (
        result
        if payment.ticket_issuance_status == Payment.TicketIssuanceStatus.ISSUED
        else _payment_status_result(payment)
    )


def _issue_verified_payment(txnid, *, allow_review_retry=False):
    issue_error = None
    result = None
    review_required = False
    with transaction.atomic():
        payment, intent = _lock_payment_context(txnid)
        if (
            payment.ticket_issuance_status == Payment.TicketIssuanceStatus.ISSUED
            and intent.registration_id
        ):
            return _intent_result(intent, payment, replayed=True)
        if (
            payment.ticket_issuance_status
            == Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED
            and not allow_review_retry
        ):
            raise PaymentReviewRequired()
        if (
            payment.status != Payment.Status.CAPTURED
            or payment.verification_status != Payment.VerificationStatus.VERIFIED
        ):
            raise PaymentConflict("The verified payment is not ready for ticket issuance.")
        if intent.registration_id:
            _mark_payment_review_required(
                payment,
                intent,
                "A registration already exists for this payment intent.",
                payment_id=payment.provider_payment_id,
                verification_status=Payment.VerificationStatus.VERIFIED,
            )
            review_required = True
        else:
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
                _mark_payment_review_required(
                    payment,
                    intent,
                    f"Ticket issuance failed ({type(error).__name__}): {error}",
                    payment_id=payment.provider_payment_id,
                    verification_status=Payment.VerificationStatus.VERIFIED,
                )
            else:
                intent.registration = registration
                intent.status = PaymentIntent.Status.VERIFIED
                intent.save(update_fields=("registration", "status", "updated_at"))
                payment.ticket_issuance_status = Payment.TicketIssuanceStatus.ISSUED
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
                result = {
                    "payment_verified": True,
                    "payment_status": payment.status,
                    "order_id": payment.provider_order_id,
                    "payment_id": payment.provider_payment_id,
                    "registration": serialized,
                    "ticket": serialized["tickets"][0],
                    "tickets": serialized["tickets"],
                    "replayed": False,
                }

    if review_required:
        raise PaymentReviewRequired()
    if issue_error:
        logger.exception(
            "Verified PayU payment %s could not issue tickets; admin review is required.",
            payment.id,
            exc_info=(
                type(issue_error),
                issue_error,
                issue_error.__traceback__,
            ),
        )
        raise PaymentReviewRequired() from issue_error

    result["delivery_status"] = TicketDelivery.objects.filter(
        ticket__registration_id=intent.registration_id
    ).values_list("status", flat=True).first()
    return result


def _apply_provider_verification(txnid, details):
    should_issue_tickets = False
    review_required = False
    with transaction.atomic():
        payment, intent = _lock_payment_context(txnid)
        if (
            payment.verification_status == Payment.VerificationStatus.VERIFIED
            and payment.ticket_issuance_status == Payment.TicketIssuanceStatus.ISSUED
            and intent.registration_id
        ):
            return _intent_result(intent, payment, replayed=True)

        state = _normalize_provider_status(details)
        provider_payment_id = str(details.get("mihpayid", "")).strip()
        matches = _provider_details_match(payment, intent, details)
        duplicate_payment_id = bool(
            provider_payment_id
            and Payment.objects.filter(provider_payment_id=provider_payment_id)
            .exclude(pk=payment.pk)
            .exists()
        )
        another_capture = Payment.objects.filter(
            intent=intent,
            status=Payment.Status.CAPTURED,
            verification_status=Payment.VerificationStatus.VERIFIED,
        ).exclude(pk=payment.pk).exists()

        payment.provider_status = str(details.get("unmappedstatus") or details.get("status") or "")[:40]
        if state == "success":
            if (
                not matches
                or not provider_payment_id
                or duplicate_payment_id
                or another_capture
                or intent.registration_id
            ):
                reasons = []
                if not matches:
                    reasons.append(
                        "PayU's verified transaction did not match the expected transaction ID, amount, or booking details."
                    )
                if not provider_payment_id or duplicate_payment_id or another_capture:
                    reasons.append("A missing or duplicate captured PayU payment was detected.")
                if intent.registration_id:
                    reasons.append("A registration already exists for this payment intent.")
                _mark_payment_review_required(
                    payment,
                    intent,
                    " ".join(reasons),
                    payment_id=provider_payment_id or None,
                )
                review_required = True
            else:
                payment.provider_payment_id = provider_payment_id
                payment.status = Payment.Status.CAPTURED
                payment.captured_at = payment.captured_at or timezone.now()
                payment.verification_status = Payment.VerificationStatus.VERIFIED
                payment.verified_at = payment.verified_at or timezone.now()
                payment.ticket_issuance_status = Payment.TicketIssuanceStatus.PENDING
                payment.ticket_issuance_failure = ""
                payment.failure_message = ""
                payment.next_verification_at = None
                payment.payment_method = str(details.get("mode", ""))[:40]
                payment.save(
                    update_fields=(
                        "provider_status",
                        "provider_payment_id",
                        "status",
                        "captured_at",
                        "verification_status",
                        "verified_at",
                        "ticket_issuance_status",
                        "ticket_issuance_failure",
                        "failure_message",
                        "payment_method",
                        "next_verification_at",
                        "updated_at",
                    )
                )
                should_issue_tickets = True
        else:
            previously_captured = payment.captured_at is not None
            payment.status = Payment.Status.FAILED if state == "failed" else Payment.Status.PENDING
            payment.verification_status = (
                Payment.VerificationStatus.FAILED
                if state == "failed"
                else Payment.VerificationStatus.PENDING
            )
            payment.failure_message = (
                "PayU reported a failed or cancelled payment."
                if state == "failed"
                else ""
            )
            payment.ticket_issuance_status = (
                Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED
                if state == "pending" and previously_captured
                else Payment.TicketIssuanceStatus.PENDING
            )
            payment.ticket_issuance_failure = (
                "PayU previously reported capture, but the latest verification is "
                "still pending. Administrator reconciliation is required."
                if state == "pending" and previously_captured
                else ""
            )
            payment.next_verification_at = (
                None if state == "failed" else payment.next_verification_at
            )
            payment.save(
                update_fields=(
                    "provider_status",
                    "status",
                    "verification_status",
                    "failure_message",
                    "ticket_issuance_status",
                    "ticket_issuance_failure",
                    "next_verification_at",
                    "updated_at",
                )
            )
            if state == "failed":
                intent.status = PaymentIntent.Status.FAILED
                intent.save(update_fields=("status", "updated_at"))
            else:
                intent.status = (
                    PaymentIntent.Status.REVIEW_REQUIRED
                    if previously_captured
                    else PaymentIntent.Status.PENDING
                )
                intent.save(update_fields=("status", "updated_at"))

    if review_required:
        raise PaymentReviewRequired()
    if should_issue_tickets:
        return _issue_verified_payment(txnid)
    payment = Payment.objects.select_related("intent").get(provider_order_id=txnid)
    return _intent_result(payment.intent, payment, replayed=True)


def process_payu_notification(payload):
    require_payu_configuration()
    txnid = str(payload.get("txnid", "")).strip()
    supplied_hash = str(payload.get("hash", "")).strip().lower()
    if not txnid or len(txnid) > 25 or not supplied_hash:
        raise PaymentVerificationError("PayU returned an incomplete payment response.")
    try:
        payment_ref = Payment.objects.select_related("intent").get(
            provider_order_id=txnid,
            provider=Payment.Provider.PAYU,
        )
    except Payment.DoesNotExist as error:
        raise NotFound("The PayU transaction was not found.") from error

    expected_hash = payu_response_hash(payload)
    if not hmac.compare_digest(expected_hash, supplied_hash):
        raise PaymentVerificationError("The PayU response hash is invalid.")
    if (
        payload.get("key") != settings.PAYU_MERCHANT_KEY
        or payload.get("txnid") != payment_ref.provider_order_id
        or not _amount_matches(payload.get("amount"), payment_ref.amount)
        or payload.get("productinfo") != "Dhandiya Night Tickets"
        or payload.get("email", "").strip().lower()
        != payment_ref.intent.buyer_email.strip().lower()
        or payload.get("udf1") != str(payment_ref.intent.idempotency_key)
        or payload.get("udf2") != str(payment_ref.id)
    ):
        raise PaymentVerificationError(
            "The PayU response does not match the stored booking details."
        )

    return refresh_payu_payment_status(txnid, trigger="CALLBACK")


def refresh_payu_payment_status(
    txnid,
    *,
    trigger=PaymentVerificationAttempt.Trigger.CLIENT,
    force=False,
    requested_by=None,
):
    if len(txnid) > 25:
        raise NotFound("The PayU transaction was not found.")
    payment = Payment.objects.filter(
        provider_order_id=txnid,
        provider=Payment.Provider.PAYU,
    ).only("id").first()
    if payment is None:
        raise NotFound("The PayU transaction was not found.")
    return _verify_payu_payment(
        payment.pk,
        trigger=trigger,
        force=force,
        requested_by=requested_by,
    )


def get_payu_payment_status(txnid, idempotency_key):
    payment = Payment.objects.filter(
        provider_order_id=txnid,
        provider=Payment.Provider.PAYU,
    ).select_related("intent").first()
    if payment is None or str(payment.intent_id) != str(idempotency_key):
        raise NotFound("The PayU transaction was not found.")
    return refresh_payu_payment_status(txnid, trigger="CLIENT")


def get_payment_review_dashboard():
    captured_payment_queryset = (
        Payment.objects.filter(
            Q(status=Payment.Status.CAPTURED)
            | Q(
                provider=Payment.Provider.PAYU,
                status__in=(Payment.Status.CREATED, Payment.Status.PENDING),
                verification_status__in=(
                    Payment.VerificationStatus.PENDING,
                    Payment.VerificationStatus.FAILED,
                ),
            )
        )
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
            filter=Q(
                status=Payment.Status.CAPTURED,
                ticket_issuance_status=Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED,
            ),
        ),
        PAYMENT_CAPTURED_WITHOUT_TICKET=Count(
            "id",
            filter=Q(status=Payment.Status.CAPTURED)
            & (Q(intent__registration__isnull=True) | Q(ticket_count=0)),
        ),
        PAYMENT_CAPTURED_WITH_INCOMPLETE_REGISTRATION=Count(
            "id",
            filter=Q(status=Payment.Status.CAPTURED)
            & (
                Q(intent__registration__isnull=True)
                | ~Q(ticket_count=F("intent__ticket_tier__admission_count"))
            ),
        ),
        DUPLICATE_PAYMENT=Count(
            "id",
            filter=Q(status=Payment.Status.CAPTURED)
            & Q(captured_for_intent__gt=1),
        ),
    )
    issue_counts = {
        key: issue_counts_agg[key] or 0
        for key in (
            "PAYMENT_REVIEW_REQUIRED",
            "TICKET_ISSUANCE_FAILED",
            "PAYMENT_CAPTURED_WITHOUT_TICKET",
            "PAYMENT_CAPTURED_WITH_INCOMPLETE_REGISTRATION",
            "DUPLICATE_PAYMENT",
        )
    }
    for payment in captured_payments:
        intent = payment.intent
        registration = intent.registration
        issue_codes = []
        if payment.ticket_issuance_status != Payment.TicketIssuanceStatus.ISSUED:
            issue_codes.append("PAYMENT_REVIEW_REQUIRED")
        if (
            payment.status == Payment.Status.CAPTURED
            and payment.ticket_issuance_status
            == Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED
        ):
            issue_codes.append("TICKET_ISSUANCE_FAILED")
        if payment.status == Payment.Status.CAPTURED and (
            registration is None or payment.ticket_count == 0
        ):
            issue_codes.append("PAYMENT_CAPTURED_WITHOUT_TICKET")
        if payment.status == Payment.Status.CAPTURED and (
            registration is None
            or payment.ticket_count != intent.ticket_tier.admission_count
        ):
            issue_codes.append("PAYMENT_CAPTURED_WITH_INCOMPLETE_REGISTRATION")
        if (
            payment.status == Payment.Status.CAPTURED
            and payment.captured_for_intent > 1
        ):
            issue_codes.append("DUPLICATE_PAYMENT")
        if payment.verification_status != Payment.VerificationStatus.VERIFIED:
            issue_codes.append("PAYMENT_REVIEW_REQUIRED")
        if issue_codes:
            payment_cases.append(
                {
                    "payment_id": str(payment.id),
                    "payment_intent_id": str(intent.idempotency_key),
                    "provider": payment.provider,
                    "order_id": payment.provider_order_id,
                    "provider_payment_id": payment.provider_payment_id,
                    "payment_status": payment.status,
                    "provider_status": payment.provider_status,
                    "captured_at": payment.captured_at.isoformat() if payment.captured_at else None,
                    "amount": payment.amount,
                    "currency": payment.currency,
                    "event_id": str(intent.event_id),
                    "event_name": intent.event.name,
                    "ticket_tier_id": str(intent.ticket_tier_id),
                    "ticket_tier_name": intent.ticket_tier.name,
                    "buyer_name": intent.buyer_name,
                    "buyer_email": intent.buyer_email,
                    "registration_id": str(registration.id) if registration else None,
                    "registration_code": (
                        registration.registration_code if registration else None
                    ),
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
            "registration_code": registration.registration_code,
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
    issue_counts["TICKET_WITHOUT_VALID_PAYMENT"] = (
        registrations_without_valid_payment_queryset.count()
        if has_more_registrations
        else len(registration_rows)
    )
    return {
        "issue_counts": issue_counts,
        "payments": payment_cases,
        "registrations_without_valid_payment": registration_cases,
        "has_more_payments": has_more_payments,
        "has_more_registrations": has_more_registrations,
    }
