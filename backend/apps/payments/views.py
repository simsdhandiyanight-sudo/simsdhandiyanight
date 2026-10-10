import hmac
import logging
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import parsers, serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdministrator
from apps.audit.models import AuditLog
from apps.registrations.serializers import CreateRegistrationSerializer
from .delivery import get_delivery_dashboard, handle_brevo_webhook
from .models import Payment, TicketDelivery
from .proof import (
    approve_manual_payment,
    generate_payment_proof_confirmation_pdf,
    get_manual_payment_proof_dashboard,
    get_payment_proof_status,
    payment_proof_screenshot,
    reject_manual_payment,
    retry_payment_rejection_email,
    start_payment_proof_registration,
    submit_payment_proof,
    validate_payment_proof_image,
)
from .services import (
    PaymentReviewRequired,
    PaymentProviderUnavailable,
    create_payment_order,
    get_payu_payment_status,
    get_payment_review_dashboard,
    process_payu_notification,
    refresh_payu_payment_status,
)

logger = logging.getLogger(__name__)


def get_idempotency_key(request):
    raw_key = request.headers.get("Idempotency-Key")
    if not raw_key:
        raise serializers.ValidationError(
            {"Idempotency-Key": "This header is required."}
        )
    try:
        return serializers.UUIDField().run_validation(raw_key)
    except serializers.ValidationError as error:
        raise serializers.ValidationError(
            {"Idempotency-Key": "Provide a valid UUID."}
        ) from error


class PayUCreatePaymentView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(csrf_protect)
    def post(self, request):
        if not settings.PAYU_FRONTEND_URL:
            raise PaymentProviderUnavailable(
                "The PayU return page is not configured."
            )
        serializer = CreateRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        attendee_names = validated.get("attendee_names") or [
            validated["buyer"]["name"]
        ]
        result = create_payment_order(
            idempotency_key=get_idempotency_key(request),
            event_id=validated["event_id"],
            tier_id=validated["ticket_tier_id"],
            buyer=validated["buyer"],
            attendee_names=attendee_names,
            success_url=settings.PAYU_SUCCESS_URL
            or request.build_absolute_uri(reverse("payu-success-callback")),
            failure_url=settings.PAYU_FAILURE_URL
            or request.build_absolute_uri(reverse("payu-failure-callback")),
        )
        response_status = (
            status.HTTP_200_OK
            if result["replayed"]
            else status.HTTP_201_CREATED
        )
        return Response(result, status=response_status)


class PaymentProofRegistrationView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(csrf_protect)
    def post(self, request):
        serializer = CreateRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        result = start_payment_proof_registration(
            idempotency_key=get_idempotency_key(request),
            event_id=validated["event_id"],
            tier_id=validated["ticket_tier_id"],
            buyer=validated["buyer"],
            attendee_names=validated.get("attendee_names")
            or [validated["buyer"]["name"]],
        )
        response = Response(
            result,
            status=status.HTTP_200_OK if result["replayed"] else status.HTTP_201_CREATED,
        )
        response["Cache-Control"] = "no-store, private"
        return response


class PaymentProofSubmissionSerializer(serializers.Serializer):
    utr_reference = serializers.RegexField(
        r"^[A-Za-z0-9/-]{6,40}$",
        max_length=40,
        trim_whitespace=True,
    )
    transaction_id = serializers.RegexField(
        r"^[A-Za-z0-9/-]{6,40}$",
        max_length=40,
        trim_whitespace=True,
    )
    screenshot = serializers.FileField()


class PaymentProofSubmissionView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    @method_decorator(csrf_protect)
    def post(self, request, registration_id):
        serializer = PaymentProofSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        access_token = serializers.UUIDField().run_validation(
            request.headers.get("X-Proof-Access-Token", "")
        )
        screenshot = serializer.validated_data["screenshot"]
        content_type = validate_payment_proof_image(screenshot)
        submit_payment_proof(
            registration_id=registration_id,
            proof_access_token=access_token,
            submission_key=get_idempotency_key(request),
            utr_reference=serializer.validated_data["utr_reference"].upper(),
            transaction_id=serializer.validated_data["transaction_id"].upper(),
            screenshot=screenshot,
            screenshot_content_type=content_type,
        )
        result = get_payment_proof_status(
            registration_id=registration_id,
            proof_access_token=access_token,
        )
        response = Response(result, status=status.HTTP_201_CREATED)
        response["Cache-Control"] = "no-store, private"
        return response


class PaymentProofStatusView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, registration_id):
        proof_access_token = serializers.UUIDField().run_validation(
            request.headers.get("X-Proof-Access-Token", "")
        )
        response = Response(
            get_payment_proof_status(
                registration_id=registration_id,
                proof_access_token=proof_access_token,
            )
        )
        response["Cache-Control"] = "no-store, private"
        return response


class PaymentProofConfirmationView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, registration_id):
        proof_access_token = serializers.UUIDField().run_validation(
            request.headers.get("X-Proof-Access-Token", "")
        )
        details = get_payment_proof_status(
            registration_id=registration_id,
            proof_access_token=proof_access_token,
        )
        if details["payment_status"] not in (
            Payment.Status.PENDING_VERIFICATION,
            Payment.Status.VERIFIED,
            Payment.Status.REJECTED,
        ):
            raise NotFound("A Ticket ID confirmation is not available yet.")
        from apps.registrations.models import Registration

        registration = Registration.objects.select_related(
            "event",
            "ticket_tier",
        ).get(pk=registration_id)
        response = HttpResponse(
            generate_payment_proof_confirmation_pdf(registration),
            content_type="application/pdf",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="ticket-id-{registration.ticket_id}.pdf"'
        )
        response["Cache-Control"] = "no-store, private"
        return response


class PaymentProofDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request):
        return Response({"proofs": get_manual_payment_proof_dashboard()})


class PaymentProofScreenshotView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request, payment_id):
        content, content_type = payment_proof_screenshot(payment_id)
        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = "inline"
        response["Cache-Control"] = "no-store, private"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class PaymentProofApproveSerializer(serializers.Serializer):
    confirmed_received = serializers.BooleanField()


class PaymentProofApproveView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    @method_decorator(csrf_protect)
    def post(self, request, payment_id):
        serializer = PaymentProofApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data["confirmed_received"]:
            raise ValidationError(
                {"confirmed_received": "Confirm actual receipt in the bank/UPI records."}
            )
        return Response(approve_manual_payment(
            payment_id=payment_id,
            administrator=request.user,
            confirmed_received=serializer.validated_data["confirmed_received"],
        ))


class PaymentProofRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000, trim_whitespace=True)


class PaymentProofRejectView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    @method_decorator(csrf_protect)
    def post(self, request, payment_id):
        serializer = PaymentProofRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(reject_manual_payment(
            payment_id=payment_id,
            administrator=request.user,
            reason=serializer.validated_data["reason"],
        ))


class PaymentProofRejectionEmailRetryView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    @method_decorator(csrf_protect)
    def post(self, request, payment_id):
        return Response(retry_payment_rejection_email(payment_id=payment_id))


class PayUCallbackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        txnid = request.data.get("txnid", "")
        if not isinstance(txnid, str) or not txnid:
            raise serializers.ValidationError({"txnid": "PayU transaction ID is required."})
        try:
            process_payu_notification(request.data)
        except PaymentProviderUnavailable:
            logger.warning("PayU callback could not be reconciled; status refresh remains available.")
        except PaymentReviewRequired:
            logger.warning("PayU callback payment requires administrator review.")
        frontend_url = f"{settings.PAYU_FRONTEND_URL.rstrip('/')}/registration/success"
        return HttpResponseRedirect(
            f"{frontend_url}?{urlencode({'txnid': txnid})}"
        )


class PayUWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        result = process_payu_notification(request.data)
        return Response(
            {"received": True, "payment_status": result["payment_status"]},
            status=status.HTTP_200_OK,
        )


class PayUPaymentStatusView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        txnid = serializers.CharField(max_length=25, trim_whitespace=True).run_validation(
            request.query_params.get("txnid", "")
        )
        idempotency_key = serializers.UUIDField().run_validation(
            request.query_params.get("idempotency_key", "")
        )
        result = get_payu_payment_status(txnid, idempotency_key)
        response = Response(result, status=status.HTTP_200_OK)
        response["Cache-Control"] = "no-store, private"
        return response


class TicketDeliveryRetryView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    @method_decorator(csrf_protect)
    def post(self, request, delivery_id):
        with transaction.atomic():
            try:
                delivery = TicketDelivery.objects.select_for_update().get(
                    pk=delivery_id
                )
            except TicketDelivery.DoesNotExist as error:
                raise NotFound("Ticket email delivery was not found.") from error
            if delivery.status in (
                TicketDelivery.Status.SENDING,
                TicketDelivery.Status.SENT,
                TicketDelivery.Status.DELIVERED,
                TicketDelivery.Status.RECONCILIATION_REQUIRED,
            ):
                raise ValidationError(
                    {"status": "Only failed or pending ticket emails can be queued."}
                )
            if delivery.status == TicketDelivery.Status.FAILED:
                delivery.status = TicketDelivery.Status.PENDING
                delivery.failure_reason = ""
                delivery.failed_at = None
                delivery.retry_after = None
                delivery.save(
                    update_fields=(
                        "status",
                        "failure_reason",
                        "failed_at",
                        "retry_after",
                        "updated_at",
                    )
                )
        return Response(
            {
                "status": TicketDelivery.Status.PENDING,
                "attempt_count": delivery.attempt_count,
                "queued": True,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class TicketDeliveryDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request):
        return Response(get_delivery_dashboard())


class PaymentReviewDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request):
        return Response(get_payment_review_dashboard())


class PaymentReconcileView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    @method_decorator(csrf_protect)
    def post(self, request, payment_id):
        payment = Payment.objects.filter(
            pk=payment_id,
            provider=Payment.Provider.PAYU,
        ).first()
        if payment is None:
            raise NotFound("The PayU payment was not found.")
        AuditLog.objects.create(
            action="PAYU_MANUAL_RECONCILIATION_REQUESTED",
            resource_type="payment",
            resource_id=str(payment.id),
            metadata={
                "payment_id": str(payment.id),
                "provider_order_id": payment.provider_order_id,
                "administrator_id": str(request.user.pk),
            },
        )
        result = refresh_payu_payment_status(
            payment.provider_order_id,
            trigger="ADMIN",
            force=True,
            requested_by=request.user,
        )
        return Response(result)


class TicketDeliveryPriorityView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    @method_decorator(csrf_protect)
    def patch(self, request, delivery_id):
        serializer = TicketDeliveryPrioritySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            try:
                delivery = TicketDelivery.objects.select_for_update().get(
                    pk=delivery_id
                )
            except TicketDelivery.DoesNotExist as error:
                raise NotFound("Ticket email delivery was not found.") from error
            if delivery.status not in (
                TicketDelivery.Status.PENDING,
                TicketDelivery.Status.FAILED,
            ):
                raise ValidationError(
                    {"status": "Priority can only be changed before sending."}
                )
            delivery.priority = serializer.validated_data["priority"]
            delivery.save(update_fields=("priority", "updated_at"))
        return Response({"id": str(delivery.id), "priority": delivery.priority})


class BrevoWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        configured_token = settings.BREVO_WEBHOOK_TOKEN
        supplied_token = request.headers.get("X-Brevo-Webhook-Token", "")
        if not configured_token or not hmac.compare_digest(
            supplied_token,
            configured_token,
        ):
            raise PermissionDenied("The Brevo webhook token is invalid.")
        event_name = request.data.get("event")
        message_id = request.data.get("message-id") or request.data.get("messageId")
        if not isinstance(event_name, str) or not isinstance(message_id, str):
            raise ValidationError(
                {"detail": "The webhook must include event and message-id fields."}
            )
        matched = handle_brevo_webhook(
            message_id=message_id,
            event_name=event_name,
        )
        return Response(
            {"processed": matched},
            status=status.HTTP_200_OK if matched else status.HTTP_202_ACCEPTED,
        )


class TicketDeliveryPrioritySerializer(serializers.Serializer):
    priority = serializers.ChoiceField(choices=TicketDelivery.Priority.choices)
