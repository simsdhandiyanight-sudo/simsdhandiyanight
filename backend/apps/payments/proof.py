import hashlib
import logging
import uuid
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError

from apps.audit.models import AuditLog
from apps.registrations.models import (
    InventoryReservation,
    Registration,
    TicketIdSequence,
)
from apps.registrations.services import (
    IdempotencyConflict,
    create_reserved_registration,
    issue_registration_tickets,
)
from .cloudinary_storage import (
    delete_unreferenced_payment_proof,
    get_payment_proof_content,
    upload_payment_proof,
)
from .models import (
    Payment,
    PaymentIntent,
    PaymentProofDecision,
)

logger = logging.getLogger(__name__)

MAX_PROOF_UPLOAD_BYTES = 5 * 1024 * 1024
VALID_PROOF_IMAGE_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


class PaymentProofConflict(APIException):
    status_code = 409
    default_detail = "The payment proof cannot be submitted in the current registration state."
    default_code = "PAYMENT_PROOF_CONFLICT"


class PaymentInstructionsUnavailable(APIException):
    status_code = 503
    default_detail = (
        "UPI payment instructions are not configured. Please contact the event team."
    )
    default_code = "PAYMENT_INSTRUCTIONS_UNAVAILABLE"


def _validate_payment_instructions():
    upi_id = settings.PAYMENT_UPI_ID
    qr_url = settings.PAYMENT_UPI_QR_IMAGE_URL
    parsed_qr_url = urlsplit(qr_url)
    valid_upi = bool(
        "@" in upi_id
        and 3 <= len(upi_id) <= 256
        and all(character.isalnum() or character in "._+-@" for character in upi_id)
    )
    valid_qr_url = (
        parsed_qr_url.scheme == "https" and bool(parsed_qr_url.netloc)
    ) or (
        settings.DEBUG
        and parsed_qr_url.scheme == "http"
        and parsed_qr_url.hostname in ("localhost", "127.0.0.1")
    )
    if not valid_upi or not valid_qr_url or parsed_qr_url.username:
        raise PaymentInstructionsUnavailable()


def validate_payment_proof_image(upload):
    if upload is None or upload.size <= 0:
        raise ValidationError({"screenshot": "A non-empty payment screenshot is required."})
    if upload.size > MAX_PROOF_UPLOAD_BYTES:
        raise ValidationError({"screenshot": "The screenshot must be 5 MB or smaller."})

    try:
        from PIL import Image, UnidentifiedImageError

        upload.seek(0)
        image = Image.open(upload)
        image.verify()
        image_format = image.format
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise ValidationError(
            {"screenshot": "Upload a valid JPEG, PNG, or WebP image."}
        ) from error
    finally:
        upload.seek(0)

    content_type = VALID_PROOF_IMAGE_FORMATS.get(image_format)
    if content_type is None:
        raise ValidationError({"screenshot": "Upload a valid JPEG, PNG, or WebP image."})
    return content_type


def _payment_instructions(tier):
    _validate_payment_instructions()
    return {
        "upi_id": settings.PAYMENT_UPI_ID,
        "upi_qr_image_url": settings.PAYMENT_UPI_QR_IMAGE_URL,
        "amount": float(tier.price),
        "currency": tier.currency,
        "reservation_hours": settings.PAYMENT_PROOF_RESERVATION_HOURS,
    }


def start_payment_proof_registration(
    *,
    idempotency_key,
    event_id,
    tier_id,
    buyer,
    attendee_names,
):
    _validate_payment_instructions()
    registration, intent, created = create_reserved_registration(
        idempotency_key=idempotency_key,
        event_id=event_id,
        tier_id=tier_id,
        buyer=buyer,
        attendee_names=attendee_names,
    )
    reservation = registration.inventory_reservation
    return {
        "registration_id": str(registration.pk),
        "proof_access_token": str(intent.proof_access_token),
        "registration_code": registration.registration_code,
        "ticket_id": registration.ticket_id,
        "registration_status": registration.status,
        "payment_status": (
            intent.payments.order_by("-created_at").values_list("status", flat=True).first()
            or Payment.Status.PENDING
        ),
        "reservation_expires_at": (
            reservation.expires_at.isoformat() if reservation.expires_at else None
        ),
        "rejection_deadline": None,
        **_payment_instructions(registration.ticket_tier),
        "replayed": not created,
    }


def _proof_result(payment):
    registration = payment.intent.registration
    return {
        "payment_id": str(payment.pk),
        "ticket_id": registration.ticket_id,
        "registration_id": str(registration.pk),
        "registration_code": registration.registration_code,
        "registration_status": registration.status,
        "payment_status": payment.status,
        "utr_reference": payment.utr_reference,
        "transaction_id": payment.transaction_id,
        "submitted_at": payment.submitted_at.isoformat() if payment.submitted_at else None,
        "rejection_reason": payment.rejection_reason,
        "rejection_deadline": (
            payment.rejection_deadline.isoformat()
            if payment.rejection_deadline
            else None
        ),
        "rejection_email_status": payment.rejection_email_status,
    }


def submit_payment_proof(
    *,
    registration_id,
    proof_access_token,
    submission_key,
    utr_reference,
    transaction_id,
    screenshot,
    screenshot_content_type,
):
    uploaded_assets = []
    try:
        return _submit_payment_proof_transaction(
            registration_id=registration_id,
            proof_access_token=proof_access_token,
            submission_key=submission_key,
            utr_reference=utr_reference,
            transaction_id=transaction_id,
            screenshot=screenshot,
            screenshot_content_type=screenshot_content_type,
            uploaded_assets=uploaded_assets,
        )
    except Exception:
        for asset in uploaded_assets:
            delete_unreferenced_payment_proof(asset["public_id"])
        raise


@transaction.atomic
def _submit_payment_proof_transaction(
    *,
    registration_id,
    proof_access_token,
    submission_key,
    utr_reference,
    transaction_id,
    screenshot,
    screenshot_content_type,
    uploaded_assets,
):
    try:
        registration = (
            Registration.objects.select_for_update()
            .select_related("event", "ticket_tier")
            .get(pk=registration_id, source=Registration.Source.ONLINE)
        )
    except Registration.DoesNotExist as error:
        raise NotFound("The registration was not found.") from error
    try:
        intent = PaymentIntent.objects.select_for_update().get(
            proof_access_token=proof_access_token,
            registration=registration,
        )
    except PaymentIntent.DoesNotExist as error:
        raise NotFound("The registration proof access key is invalid.") from error

    content = screenshot.read()
    screenshot.seek(0)
    proof_hash = hashlib.sha256(
        b"\0".join(
            (
                str(registration.pk).encode(),
                utr_reference.encode(),
                transaction_id.encode(),
                hashlib.sha256(content).digest(),
                screenshot_content_type.encode(),
            )
        )
    ).hexdigest()

    existing = Payment.objects.filter(submission_key=submission_key).first()
    if existing is not None:
        if existing.proof_hash != proof_hash or existing.intent_id != intent.pk:
            raise IdempotencyConflict()
        return _proof_result(existing)
    previous_submission = Payment.objects.filter(
        intent=intent,
        provider=Payment.Provider.UPI_MANUAL,
        utr_reference=utr_reference,
    ).first()
    if previous_submission is not None:
        if previous_submission.proof_hash == proof_hash:
            return _proof_result(previous_submission)
        raise ValidationError(
            {"utr_reference": "This UTR/reference has already been submitted."}
        )
    previous_transaction = Payment.objects.filter(
        intent=intent,
        provider=Payment.Provider.UPI_MANUAL,
        transaction_id=transaction_id,
    ).first()
    if previous_transaction is not None:
        if previous_transaction.proof_hash == proof_hash:
            return _proof_result(previous_transaction)
        raise ValidationError(
            {"transaction_id": "This transaction ID has already been submitted."}
        )

    try:
        reservation = (
            InventoryReservation.objects.select_for_update()
            .get(registration=registration)
        )
    except InventoryReservation.DoesNotExist as error:
        raise PaymentProofConflict("This registration has no active ticket reservation.") from error

    now = timezone.now()
    if reservation.status != InventoryReservation.Status.RESERVED:
        raise PaymentProofConflict("The ticket reservation has already been released or consumed.")
    if reservation.expires_at is not None and reservation.expires_at <= now:
        raise PaymentProofConflict("The reservation expired. Please start a new registration.")
    if registration.status not in (
        Registration.Status.REGISTERED,
        Registration.Status.REJECTED,
    ):
        raise PaymentProofConflict("Payment proof is not expected in the current registration state.")

    previous = None
    if registration.status == Registration.Status.REJECTED:
        previous = intent.payments.filter(
            provider=Payment.Provider.UPI_MANUAL,
            status=Payment.Status.REJECTED,
        ).order_by("-submitted_at").first()
        if (
            previous is None
            or previous.rejection_deadline is None
            or previous.rejection_deadline <= now
            or reservation.expires_at is None
            or reservation.expires_at <= now
        ):
            raise PaymentProofConflict(
                "The 12-hour correction window has expired. Please contact the event team."
            )

    amount = int(registration.ticket_tier.price * 100)
    screenshot.seek(0)
    cloudinary_asset = upload_payment_proof(
        screenshot,
        image_format=screenshot_content_type.split("/", 1)[1],
        image_size=len(content),
    )
    uploaded_assets.append(cloudinary_asset)
    try:
        with transaction.atomic():
            payment = Payment.objects.create(
                intent=intent,
                provider=Payment.Provider.UPI_MANUAL,
                amount=amount,
                currency=registration.ticket_tier.currency,
                status=Payment.Status.PENDING_VERIFICATION,
                verification_status=Payment.VerificationStatus.PENDING,
                ticket_issuance_status=Payment.TicketIssuanceStatus.PENDING,
                submission_key=submission_key,
                proof_hash=proof_hash,
                utr_reference=utr_reference,
                transaction_id=transaction_id,
                proof_content_type=screenshot_content_type,
                proof_cloudinary_public_id=cloudinary_asset["public_id"],
                proof_cloudinary_asset_id=cloudinary_asset["asset_id"],
                proof_cloudinary_version=cloudinary_asset["version"],
                proof_format=cloudinary_asset["format"],
                proof_size_bytes=cloudinary_asset["size"],
                submitted_at=now,
            )
    except IntegrityError as error:
        if Payment.objects.filter(utr_reference=utr_reference).exists():
            raise ValidationError(
                {"utr_reference": "This UTR/reference has already been submitted."}
            ) from error
        if Payment.objects.filter(transaction_id=transaction_id).exists():
            raise ValidationError(
                {"transaction_id": "This transaction ID has already been submitted."}
            ) from error
        existing = Payment.objects.filter(submission_key=submission_key).first()
        if existing is not None and existing.proof_hash == proof_hash:
            delete_unreferenced_payment_proof(cloudinary_asset["public_id"])
            uploaded_assets.remove(cloudinary_asset)
            return _proof_result(existing)
        raise

    if registration.ticket_id is None:
        registration.ticket_id = TicketIdSequence.next_ticket_id(
            registration.event.start_at.year
        )
    registration.status = Registration.Status.PENDING_VERIFICATION
    registration.save(update_fields=("ticket_id", "status", "updated_at"))
    reservation.expires_at = None
    reservation.save(update_fields=("expires_at", "updated_at"))
    intent.status = PaymentIntent.Status.REVIEW_REQUIRED
    intent.expires_at = None
    intent.save(update_fields=("status", "expires_at", "updated_at"))

    if previous is not None:
        PaymentProofDecision.objects.create(
            payment=payment,
            registration=registration,
            action=PaymentProofDecision.Action.RESUBMITTED,
            metadata={
                "previous_payment_id": str(previous.pk),
                "ticket_id": registration.ticket_id,
                "utr_reference": utr_reference,
                "transaction_id": transaction_id,
            },
        )

    AuditLog.objects.create(
        action="PAYMENT_PROOF_SUBMITTED",
        resource_type="payment",
        resource_id=str(payment.pk),
        metadata={
            "registration_id": str(registration.pk),
            "ticket_id": registration.ticket_id,
            "utr_reference": utr_reference,
            "transaction_id": transaction_id,
            "amount_paise": amount,
        },
    )
    return _proof_result(payment)


def get_payment_proof_status(*, registration_id, proof_access_token):
    try:
        intent = (
            PaymentIntent.objects.select_related(
                "registration__event",
                "registration__ticket_tier",
            )
            .get(
                proof_access_token=proof_access_token,
                registration_id=registration_id,
            )
        )
    except PaymentIntent.DoesNotExist as error:
        raise NotFound("The registration was not found.") from error
    registration = intent.registration
    latest_payment = intent.payments.filter(
        provider=Payment.Provider.UPI_MANUAL
    ).order_by("-submitted_at", "-created_at").first()
    reservation = registration.inventory_reservation
    reservation_active = (
        reservation.status == InventoryReservation.Status.RESERVED
        and (reservation.expires_at is None or reservation.expires_at > timezone.now())
    )
    can_submit_proof = (
        registration.status == Registration.Status.REGISTERED and reservation_active
    )
    if registration.status == Registration.Status.REJECTED and latest_payment:
        can_submit_proof = bool(
            reservation_active
            and latest_payment.rejection_deadline
            and latest_payment.rejection_deadline > timezone.now()
        )
    email_status = ""
    if latest_payment and latest_payment.status == Payment.Status.VERIFIED:
        from .models import TicketDelivery

        delivery_statuses = list(
            TicketDelivery.objects.filter(
                ticket__registration=registration,
            ).values_list("status", flat=True)
        )
        if delivery_statuses and all(
            status in (
                TicketDelivery.Status.SENT,
                TicketDelivery.Status.DELIVERED,
            )
            for status in delivery_statuses
        ):
            email_status = "SENT"
        elif any(
            status in (
                TicketDelivery.Status.FAILED,
                TicketDelivery.Status.RECONCILIATION_REQUIRED,
            )
            for status in delivery_statuses
        ):
            email_status = "FAILED"
        else:
            email_status = "PENDING"
    instructions = _payment_instructions(registration.ticket_tier)
    result = {
        "registration_id": str(registration.pk),
        "registration_code": registration.registration_code,
        "ticket_id": registration.ticket_id,
        "registration_status": registration.status,
        "can_submit_proof": can_submit_proof,
        "email_status": email_status,
        "event_name": registration.event.name,
        "applicant_name": registration.buyer_name,
        "applicant_email": registration.buyer_email,
        "ticket_tier_name": registration.ticket_tier.name,
        "amount": float(registration.ticket_tier.price),
        "currency": registration.ticket_tier.currency,
        "reservation_expires_at": (
            reservation.expires_at.isoformat()
            if reservation.expires_at
            else None
        ),
        **instructions,
    }
    if latest_payment is not None:
        result.update(_proof_result(latest_payment))
    else:
        result.update(
            {
                "payment_id": None,
                "payment_status": Payment.Status.PENDING,
                "utr_reference": "",
                "transaction_id": "",
                "submitted_at": None,
                "rejection_reason": "",
                "rejection_deadline": None,
                "rejection_email_status": "",
                "email_status": "",
            }
        )
    return result


def get_manual_payment_proof_dashboard():
    payments = (
        Payment.objects.filter(
            provider=Payment.Provider.UPI_MANUAL,
        )
        .select_related(
            "intent__registration__event",
            "intent__registration__ticket_tier",
            "intent__ticket_tier",
            "verified_by",
            "rejected_by",
        )
        .defer("proof_screenshot")
        .order_by("-submitted_at", "-created_at")[:200]
    )
    return [
        {
            "payment_id": str(payment.pk),
            "registration_id": str(payment.intent.registration_id),
            "registration_code": payment.intent.registration.registration_code,
            "ticket_id": payment.intent.registration.ticket_id,
            "registration_status": payment.intent.registration.status,
            "applicant_name": payment.intent.buyer_name,
            "applicant_email": payment.intent.buyer_email,
            "event_name": payment.intent.event.name,
            "ticket_tier_name": payment.intent.ticket_tier.name,
            "expected_amount": payment.amount,
            "currency": payment.currency,
            "utr_reference": payment.utr_reference,
            "transaction_id": payment.transaction_id,
            "screenshot_url": f"/payments/proof/{payment.pk}/screenshot/",
            "submitted_at": payment.submitted_at.isoformat(),
            "payment_status": payment.status,
            "rejection_reason": payment.rejection_reason,
            "rejection_deadline": (
                payment.rejection_deadline.isoformat()
                if payment.rejection_deadline
                else None
            ),
            "verified_by": (
                payment.verified_by.name or payment.verified_by.email
                if payment.verified_by
                else None
            ),
            "verified_at": payment.verified_at.isoformat() if payment.verified_at else None,
            "rejected_by": (
                payment.rejected_by.name or payment.rejected_by.email
                if payment.rejected_by
                else None
            ),
            "rejected_at": payment.rejected_at.isoformat() if payment.rejected_at else None,
            "rejection_email_status": payment.rejection_email_status,
        }
        for payment in payments
    ]


@transaction.atomic
def approve_manual_payment(*, payment_id, administrator, confirmed_received):
    if not confirmed_received:
        raise ValidationError(
            {"confirmed_received": "Confirm actual receipt in the bank/UPI records."}
        )
    try:
        payment_ref = Payment.objects.select_related("intent").get(pk=payment_id)
    except Payment.DoesNotExist as error:
        raise NotFound("The payment proof was not found.") from error
    registration = (
        Registration.objects.select_for_update()
        .select_related("event", "ticket_tier")
        .get(pk=payment_ref.intent.registration_id)
    )
    reservation = InventoryReservation.objects.select_for_update().get(
        registration=registration
    )
    intent = PaymentIntent.objects.select_for_update().get(
        pk=payment_ref.intent_id,
        registration=registration,
    )
    payment = Payment.objects.select_for_update().get(pk=payment_id)
    if payment.provider != Payment.Provider.UPI_MANUAL:
        raise PaymentProofConflict("Only manual UPI payment proofs can be approved here.")
    if (
        payment.status == Payment.Status.VERIFIED
        and registration.status == Registration.Status.TICKET_ISSUED
    ):
        return {
            "payment_status": payment.status,
            "registration_status": registration.status,
            "ticket_id": registration.ticket_id,
            "ticket_count": registration.tickets.count(),
            "replayed": True,
        }
    if payment.status != Payment.Status.PENDING_VERIFICATION:
        raise PaymentProofConflict("Only pending payment proofs can be approved.")
    if registration.status != Registration.Status.PENDING_VERIFICATION:
        raise PaymentProofConflict("The registration is not awaiting payment verification.")
    if reservation.status != InventoryReservation.Status.RESERVED:
        raise PaymentProofConflict("This registration no longer has an active reservation.")
    if reservation.expires_at is not None and reservation.expires_at <= timezone.now():
        raise PaymentProofConflict("The reservation expired before payment approval.")
    if not payment.utr_reference or not (
        payment.proof_cloudinary_public_id or payment.proof_screenshot is not None
    ):
        raise PaymentProofConflict("A complete payment proof is required before approval.")
    if payment.amount != int(registration.ticket_tier.price * 100):
        raise PaymentProofConflict("The submitted amount does not match the expected ticket fee.")

    now = timezone.now()
    payment.status = Payment.Status.VERIFIED
    payment.verification_status = Payment.VerificationStatus.VERIFIED
    payment.provider_status = "MANUALLY_VERIFIED"
    payment.verified_by = administrator
    payment.verified_at = now
    payment.ticket_issuance_status = Payment.TicketIssuanceStatus.PENDING
    payment.save(
        update_fields=(
            "status",
            "verification_status",
            "provider_status",
            "verified_by",
            "verified_at",
            "ticket_issuance_status",
            "updated_at",
        )
    )
    intent.status = PaymentIntent.Status.VERIFIED
    intent.save(update_fields=("status", "updated_at"))
    registration.status = Registration.Status.PAYMENT_VERIFIED
    registration.save(update_fields=("status", "updated_at"))

    tickets = issue_registration_tickets(
        registration=registration,
        attendee_names=intent.attendee_names,
    )
    if len(tickets) != reservation.units_reserved:
        raise PaymentProofConflict("Ticket count does not match the reserved inventory.")
    reservation.status = InventoryReservation.Status.CONSUMED
    reservation.consumed_at = now
    reservation.expires_at = None
    reservation.save(
        update_fields=("status", "consumed_at", "expires_at", "updated_at")
    )
    registration.status = Registration.Status.TICKET_ISSUED
    registration.save(update_fields=("status", "updated_at"))
    payment.ticket_issuance_status = Payment.TicketIssuanceStatus.ISSUED
    payment.ticket_issuance_failure = ""
    payment.save(
        update_fields=(
            "ticket_issuance_status",
            "ticket_issuance_failure",
            "updated_at",
        )
    )

    PaymentProofDecision.objects.create(
        payment=payment,
        registration=registration,
        actor=administrator,
        action=PaymentProofDecision.Action.APPROVED,
        metadata={
            "ticket_id": registration.ticket_id,
            "utr_reference": payment.utr_reference,
            "transaction_id": payment.transaction_id,
            "amount_paise": payment.amount,
            "bank_upi_transaction_confirmed": True,
            "screenshot_size_bytes": payment.proof_size_bytes,
        },
    )
    PaymentProofDecision.objects.create(
        payment=payment,
        registration=registration,
        actor=administrator,
        action=PaymentProofDecision.Action.TICKET_ISSUED,
        metadata={"ticket_ids": [str(ticket.pk) for ticket in tickets]},
    )
    AuditLog.objects.create(
        actor=administrator,
        action="MANUAL_PAYMENT_VERIFIED",
        resource_type="payment",
        resource_id=str(payment.pk),
        metadata={
            "registration_id": str(registration.pk),
            "ticket_id": registration.ticket_id,
            "utr_reference": payment.utr_reference,
            "transaction_id": payment.transaction_id,
            "amount_paise": payment.amount,
            "ticket_ids": [str(ticket.pk) for ticket in tickets],
        },
    )
    return {
        "payment_status": payment.status,
        "registration_status": registration.status,
        "ticket_id": registration.ticket_id,
        "ticket_count": len(tickets),
        "email_status": "PENDING",
        "replayed": False,
    }


def reject_manual_payment(*, payment_id, administrator, reason):
    reason = reason.strip()
    if not reason:
        raise ValidationError({"reason": "A rejection reason is required."})

    with transaction.atomic():
        try:
            payment_ref = Payment.objects.select_related("intent").get(pk=payment_id)
        except Payment.DoesNotExist as error:
            raise NotFound("The payment proof was not found.") from error
        registration = Registration.objects.select_for_update().get(
            pk=payment_ref.intent.registration_id
        )
        reservation = InventoryReservation.objects.select_for_update().get(
            registration=registration
        )
        intent = PaymentIntent.objects.select_for_update().get(
            pk=payment_ref.intent_id,
            registration=registration,
        )
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        if payment.provider != Payment.Provider.UPI_MANUAL:
            raise PaymentProofConflict("Only manual UPI payment proofs can be rejected here.")
        if payment.status != Payment.Status.PENDING_VERIFICATION:
            raise PaymentProofConflict("Only pending payment proofs can be rejected.")
        if registration.status != Registration.Status.PENDING_VERIFICATION:
            raise PaymentProofConflict("The registration is not awaiting payment verification.")
        if reservation.status != InventoryReservation.Status.RESERVED:
            raise PaymentProofConflict("This registration no longer has an active reservation.")

        now = timezone.now()
        deadline = now + timedelta(hours=settings.PAYMENT_PROOF_RESUBMISSION_HOURS)
        payment.status = Payment.Status.REJECTED
        payment.rejected_by = administrator
        payment.rejected_at = now
        payment.rejection_reason = reason[:1000]
        payment.rejection_deadline = deadline
        payment.rejection_email_status = "PENDING"
        payment.save(
            update_fields=(
                "status",
                "rejected_by",
                "rejected_at",
                "rejection_reason",
                "rejection_deadline",
                "rejection_email_status",
                "updated_at",
            )
        )
        registration.status = Registration.Status.REJECTED
        registration.save(update_fields=("status", "updated_at"))
        reservation.expires_at = deadline
        reservation.save(update_fields=("expires_at", "updated_at"))
        intent.status = PaymentIntent.Status.PENDING
        intent.expires_at = deadline
        intent.save(update_fields=("status", "expires_at", "updated_at"))

        PaymentProofDecision.objects.create(
            payment=payment,
            registration=registration,
            actor=administrator,
            action=PaymentProofDecision.Action.REJECTED,
            reason=reason[:1000],
            metadata={
                "ticket_id": registration.ticket_id,
                "resubmission_deadline": deadline.isoformat(),
            },
        )
        AuditLog.objects.create(
            actor=administrator,
            action="MANUAL_PAYMENT_REJECTED",
            resource_type="payment",
            resource_id=str(payment.pk),
            metadata={
                "registration_id": str(registration.pk),
                "ticket_id": registration.ticket_id,
                "reason": reason[:1000],
                "rejection_deadline": deadline.isoformat(),
            },
        )

    from .delivery import send_payment_rejection_email

    email_status = send_payment_rejection_email(payment.pk)
    return {
        "payment_status": Payment.Status.REJECTED,
        "registration_status": Registration.Status.REJECTED,
        "ticket_id": registration.ticket_id,
        "rejection_deadline": deadline.isoformat(),
        "rejection_email_status": email_status,
    }


def retry_payment_rejection_email(*, payment_id):
    payment = Payment.objects.filter(
        pk=payment_id,
        provider=Payment.Provider.UPI_MANUAL,
        status=Payment.Status.REJECTED,
        rejection_email_status="FAILED",
    ).first()
    if payment is None:
        raise PaymentProofConflict("Only failed rejection emails can be retried.")
    claimed = Payment.objects.filter(
        pk=payment.pk,
        rejection_email_status="FAILED",
    ).update(
        rejection_email_status="PENDING",
        updated_at=timezone.now(),
    )
    if not claimed:
        raise PaymentProofConflict("The rejection email is already being retried.")
    from .delivery import send_payment_rejection_email

    result = send_payment_rejection_email(payment.pk)
    return {"payment_id": str(payment.pk), "email_status": result}


def expire_payment_proof_reservations(*, now=None, limit=500):
    now = now or timezone.now()
    due_registration_ids = list(
        InventoryReservation.objects.filter(
            status=InventoryReservation.Status.RESERVED,
            expires_at__lte=now,
        )
        .order_by("expires_at")
        .values_list("registration_id", flat=True)[:limit]
    )
    expired = 0
    for registration_id in due_registration_ids:
        with transaction.atomic():
            registration = (
                Registration.objects.select_for_update()
                .filter(pk=registration_id)
                .first()
            )
            if registration is None:
                continue
            reservation = (
                InventoryReservation.objects.select_for_update()
                .filter(
                    registration=registration,
                    status=InventoryReservation.Status.RESERVED,
                    expires_at__lte=now,
                )
                .first()
            )
            if reservation is None or registration.status not in (
                Registration.Status.REGISTERED,
                Registration.Status.REJECTED,
            ):
                continue

            reservation.status = InventoryReservation.Status.RELEASED
            reservation.released_at = now
            reservation.save(
                update_fields=("status", "released_at", "updated_at")
            )
            registration.status = Registration.Status.EXPIRED
            registration.save(update_fields=("status", "updated_at"))
            intent = PaymentIntent.objects.select_for_update().filter(
                registration=registration,
            ).first()
            if intent:
                intent.status = PaymentIntent.Status.FAILED
                intent.save(update_fields=("status", "updated_at"))
            latest_payment = (
                Payment.objects.select_for_update()
                .filter(
                    intent=intent,
                    provider=Payment.Provider.UPI_MANUAL,
                )
                .order_by("-submitted_at", "-created_at")
                .first()
                if intent
                else None
            )
            PaymentProofDecision.objects.create(
                payment=latest_payment,
                registration=registration,
                action=PaymentProofDecision.Action.RESERVATION_RELEASED,
                reason="The reservation expired before payment proof was accepted or corrected.",
                metadata={
                    "ticket_id": registration.ticket_id,
                    "units_released": reservation.units_reserved,
                },
            )
            AuditLog.objects.create(
                action="PAYMENT_PROOF_RESERVATION_RELEASED",
                resource_type="registration",
                resource_id=str(registration.pk),
                metadata={
                    "ticket_id": registration.ticket_id,
                    "units_released": reservation.units_reserved,
                    "previous_status": (
                        Registration.Status.REJECTED
                        if latest_payment
                        else Registration.Status.REGISTERED
                    ),
                },
            )
            expired += 1
    return expired


def payment_proof_screenshot(payment_id):
    try:
        payment = Payment.objects.only(
            "proof_cloudinary_public_id",
            "proof_format",
            "proof_cloudinary_version",
            "proof_size_bytes",
            "proof_screenshot",
            "proof_content_type",
        ).get(pk=payment_id, provider=Payment.Provider.UPI_MANUAL)
    except Payment.DoesNotExist as error:
        raise Http404 from error
    if not payment.proof_cloudinary_public_id and payment.proof_screenshot is None:
        raise Http404
    content = get_payment_proof_content(payment)
    content_type = payment.proof_content_type
    return content, content_type


def generate_payment_proof_confirmation_pdf(registration):
    from apps.payments.pdf import generate_ticket_id_confirmation_pdf

    return generate_ticket_id_confirmation_pdf(registration)
