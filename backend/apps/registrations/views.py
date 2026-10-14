from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from rest_framework import serializers, status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.events.models import Event
from apps.tickets.models import Ticket
from .models import Registration
from .serializers import (
    CreateRegistrationSerializer,
    RegistrationListSerializer,
    RegistrationSerializer,
)
from apps.payments.models import Payment, TicketSheetSync


class PaymentRequired(APIException):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_detail = "Online tickets are issued only after backend payment verification."
    default_code = "PAYMENT_REQUIRED"


class RegistrationListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [AllowAny()]
        return [IsAuthenticated()]

    def post(self, request):
        raise PaymentRequired()

    def get(self, request):
        if request.user.role not in ("ADMIN", "REGISTRATION_STAFF"):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Registration staff access is required.")
        registrations = Registration.objects.select_related("event", "ticket_tier").prefetch_related("tickets")
        event_id = request.query_params.get("event_id")
        if event_id:
            try:
                event_uuid = serializers.UUIDField().run_validation(event_id)
                event = Event.objects.get(pk=event_uuid)
            except (Event.DoesNotExist, serializers.ValidationError) as error:
                raise serializers.ValidationError({"event_id": "Unknown event."}) from error
            registrations = registrations.filter(event=event)
        source = request.query_params.get("source")
        if source:
            if source not in Registration.Source.values:
                raise serializers.ValidationError({"source": "Unknown registration source."})
            registrations = registrations.filter(source=source)
        search = request.query_params.get("search", "").strip()
        if search:
            registrations = registrations.filter(
                Q(id__icontains=search)
                | Q(registration_code__icontains=search)
                | Q(buyer_name__icontains=search)
                | Q(buyer_email__icontains=search)
                | Q(buyer_phone__icontains=search)
                | Q(tickets__id__icontains=search)
            ).distinct()
        page = self.paginate_queryset(request, registrations)
        return self.get_paginated_response(RegistrationListSerializer(page, many=True).data)

    def paginate_queryset(self, request, queryset):
        from config.pagination import StandardPagination

        paginator = StandardPagination()
        self.paginator = paginator
        return paginator.paginate_queryset(queryset, request, view=self)

    def get_paginated_response(self, data):
        return self.paginator.get_paginated_response(data)

    def _created_response(self, registration, *, created=True):
        registration = (
            Registration.objects.select_related("event", "ticket_tier")
            .prefetch_related(Prefetch("tickets", queryset=Ticket.objects.select_related("registration__event", "registration__ticket_tier")))
            .get(pk=registration.pk)
        )
        data = RegistrationSerializer(registration).data
        tickets = data["tickets"]
        sync_statuses = list(
            TicketSheetSync.objects.filter(ticket__registration=registration)
            .values_list("status", flat=True)
        )
        if not sync_statuses:
            sheet_sync_status = "NOT_QUEUED"
        elif TicketSheetSync.Status.FAILED in sync_statuses:
            sheet_sync_status = TicketSheetSync.Status.FAILED
        elif any(
            status != TicketSheetSync.Status.SYNCED for status in sync_statuses
        ):
            sheet_sync_status = TicketSheetSync.Status.PENDING
        else:
            sheet_sync_status = TicketSheetSync.Status.SYNCED
        payment = Payment.objects.filter(intent__registration=registration).first()
        ticket_issuance_status = (
            payment.ticket_issuance_status if payment else "ISSUED"
        )
        response = Response(
            {
                "registration": data,
                "ticket": tickets[0] if tickets else None,
                "tickets": tickets,
                "sheet_sync_status": sheet_sync_status,
                "ticket_issuance_status": ticket_issuance_status,
            },
            status=(
                status.HTTP_202_ACCEPTED
                if not tickets
                else status.HTTP_201_CREATED
                if created
                else status.HTTP_200_OK
            ),
        )
        response["Idempotency-Replayed"] = "false" if created else "true"
        return response


class RegistrationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, registration_id):
        if request.user.role not in ("ADMIN", "REGISTRATION_STAFF"):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Registration staff access is required.")
        registration = get_object_or_404(
            Registration.objects.select_related("event", "ticket_tier").prefetch_related(
                "tickets__registration__event",
                "tickets__registration__ticket_tier",
            ),
            pk=registration_id,
        )
        return Response(RegistrationSerializer(registration).data)
