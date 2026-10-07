from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import CanRegisterOnSpot
from apps.events.models import Event
from apps.tickets.models import Ticket
from .models import Registration
from .serializers import (
    CreateRegistrationSerializer,
    RegistrationListSerializer,
    RegistrationSerializer,
)
from .services import create_registration


class RegistrationListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_throttles(self):
        return [AnonRateThrottle()] if self.request.method == "POST" else []

    @method_decorator(csrf_protect)
    def post(self, request):
        serializer = CreateRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        registration, _tickets = create_registration(
            event_id=serializer.validated_data["event_id"],
            tier_id=serializer.validated_data["ticket_tier_id"],
            buyer=serializer.validated_data["buyer"],
            source=Registration.Source.ONLINE,
        )
        return self._created_response(registration)

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

    def _created_response(self, registration):
        registration = (
            Registration.objects.select_related("event", "ticket_tier")
            .prefetch_related(Prefetch("tickets", queryset=Ticket.objects.select_related("registration__event", "registration__ticket_tier")))
            .get(pk=registration.pk)
        )
        data = RegistrationSerializer(registration).data
        return Response({"registration": data, "ticket": data["tickets"][0], "tickets": data["tickets"]}, status=status.HTTP_201_CREATED)


class OnSpotRegistrationView(APIView):
    permission_classes = [CanRegisterOnSpot]

    @method_decorator(csrf_protect)
    def post(self, request):
        serializer = CreateRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        registration, _tickets = create_registration(
            event_id=serializer.validated_data["event_id"],
            tier_id=serializer.validated_data["ticket_tier_id"],
            buyer=serializer.validated_data["buyer"],
            source=Registration.Source.ON_SPOT,
            created_by=request.user,
        )
        response_view = RegistrationListCreateView()
        return response_view._created_response(registration)


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
