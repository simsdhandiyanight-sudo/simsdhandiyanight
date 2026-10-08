import hmac

from django.conf import settings
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdministrator
from apps.registrations.serializers import CreateRegistrationSerializer
from .delivery import get_delivery_dashboard, handle_brevo_webhook
from .models import Payment, TicketDelivery
from .services import (
    PaymentProviderUnavailable,
    create_payment_order,
    get_payment_review_dashboard,
    record_payment_failure,
    verify_payment,
)


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


class RazorpayCreateOrderView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(csrf_protect)
    def post(self, request):
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            raise PaymentProviderUnavailable(
                "Razorpay test credentials are not configured."
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
        )
        response_status = (
            status.HTTP_200_OK
            if result["replayed"]
            else status.HTTP_201_CREATED
        )
        result["key_id"] = settings.RAZORPAY_KEY_ID
        return Response(result, status=response_status)


class RazorpayVerifyPaymentView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(csrf_protect)
    def post(self, request):
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            raise PaymentProviderUnavailable(
                "Razorpay test credentials are not configured."
            )
        serializer = RazorpayVerifyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = verify_payment(
            order_id=serializer.validated_data["razorpay_order_id"],
            payment_id=serializer.validated_data["razorpay_payment_id"],
            signature=serializer.validated_data["razorpay_signature"],
        )
        return Response(result, status=status.HTTP_200_OK)


class RazorpayVerifyRequestSerializer(serializers.Serializer):
    razorpay_order_id = serializers.CharField(max_length=64, trim_whitespace=True)
    razorpay_payment_id = serializers.CharField(max_length=64, trim_whitespace=True)
    razorpay_signature = serializers.RegexField(
        r"^[a-fA-F0-9]{64}$",
        max_length=64,
        trim_whitespace=True,
    )


class RazorpayPaymentFailureView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(csrf_protect)
    def post(self, request):
        serializer = RazorpayPaymentFailureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = record_payment_failure(
            order_id=serializer.validated_data["razorpay_order_id"],
        )
        return Response(
            {"status": payment.status},
            status=status.HTTP_200_OK,
        )


class RazorpayPaymentFailureSerializer(serializers.Serializer):
    razorpay_order_id = serializers.CharField(max_length=64, trim_whitespace=True)


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
