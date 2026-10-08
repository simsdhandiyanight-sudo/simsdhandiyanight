import csv

from django.db.models import Count, Q
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import CanScan, IsAdministrator
from apps.events.models import Event
from apps.registrations.models import Registration
from apps.tickets.models import Ticket
from .models import TicketScan
from .serializers import (
    ScanRequestSerializer,
    ScannedTicketSerializer,
    TicketScanSerializer,
)
from .services import ScannerConfigurationError, assigned_gate_for, scan_ticket


class ScanListCreateView(APIView):
    def get_permissions(self):
        return [CanScan()] if self.request.method == "POST" else [IsAuthenticated()]

    def get_throttles(self):
        return [UserRateThrottle()] if self.request.method == "POST" else []

    @method_decorator(csrf_protect)
    def post(self, request):
        serializer = ScanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            scan = scan_ticket(token=serializer.validated_data["token"], scanner=request.user)
        except ScannerConfigurationError as error:
            raise PermissionDenied(str(error)) from error

        success = scan.result == TicketScan.Result.ENTRY_GRANTED
        response_status = (
            status.HTTP_200_OK
            if success
            else status.HTTP_404_NOT_FOUND
            if scan.result == TicketScan.Result.INVALID_TICKET
            else status.HTTP_409_CONFLICT
        )
        scan = TicketScan.objects.select_related(
            "ticket__registration",
            "event",
            "gate",
            "scanned_by",
        ).get(pk=scan.pk)
        return Response(
            {
                "success": success,
                "result": scan.result,
                "ticket": (
                    ScannedTicketSerializer(
                        scan.ticket,
                        context={"request": request},
                    ).data
                    if scan.ticket_id
                    else None
                ),
                "scan_record": TicketScanSerializer(scan).data,
                "scanned_at": scan.scanned_at,
            },
            status=response_status,
        )

    def get(self, request):
        if request.user.role not in ("ADMIN", "SCANNER_STAFF"):
            raise PermissionDenied(
                "Scan history access is restricted to administrators and scanner staff."
            )

        scans = TicketScan.objects.select_related(
            "ticket__registration",
            "event",
            "gate",
            "scanned_by",
        )
        if request.user.role == "SCANNER_STAFF":
            try:
                gate = assigned_gate_for(request.user)
            except ScannerConfigurationError as error:
                raise PermissionDenied(str(error)) from error
            scans = scans.filter(gate=gate)
        event_id = request.query_params.get("event_id")
        if event_id:
            try:
                event_uuid = serializers.UUIDField().run_validation(event_id)
            except serializers.ValidationError as error:
                raise serializers.ValidationError({"event_id": "Unknown event."}) from error
            scans = scans.filter(event_id=event_uuid)
        result = request.query_params.get("result")
        if result:
            if result not in TicketScan.Result.values:
                raise serializers.ValidationError({"result": "Unknown scan result."})
            scans = scans.filter(result=result)
        search = request.query_params.get("search", "").strip()
        if search:
            scans = scans.filter(
                Q(ticket__id__icontains=search)
                | Q(ticket__registration__buyer_name__icontains=search)
                | Q(ticket__attendee_name__icontains=search)
                | Q(gate__name__icontains=search)
                | Q(scanned_by__name__icontains=search)
            )

        from config.pagination import StandardPagination

        paginator = StandardPagination()
        page = paginator.paginate_queryset(scans, request, view=self)
        return paginator.get_paginated_response(TicketScanSerializer(page, many=True).data)


class DashboardSummaryView(APIView):
    permission_classes = [IsAdministrator]

    def get(self, request):
        event_id = request.query_params.get("event_id")
        event_query = Event.objects.all()
        if event_id:
            try:
                event_uuid = serializers.UUIDField().run_validation(event_id)
            except serializers.ValidationError as error:
                raise serializers.ValidationError({"event_id": "Unknown event."}) from error
            event_query = event_query.filter(pk=event_uuid)
        event = event_query.first()
        if event is None:
            return Response(
                {
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "Event not found.",
                        "details": {},
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        registrations = Registration.objects.filter(event=event)
        tickets = Ticket.objects.filter(registration__event=event)
        scans = TicketScan.objects.filter(event=event)
        return Response(
            {
                "event_id": str(event.id),
                "registrations": registrations.count(),
                "online_registrations": registrations.filter(
                    source=Registration.Source.ONLINE
                ).count(),
                "on_spot_registrations": registrations.filter(
                    source=Registration.Source.ON_SPOT
                ).count(),
                "active_tickets": tickets.exclude(status=Ticket.Status.CANCELLED).count(),
                "used_tickets": tickets.filter(status=Ticket.Status.USED).count(),
                "cancelled_tickets": tickets.filter(status=Ticket.Status.CANCELLED).count(),
                "scan_attempts": scans.count(),
                "entry_granted": scans.filter(
                    result=TicketScan.Result.ENTRY_GRANTED
                ).count(),
                "scan_results": list(
                    scans.values("result")
                    .annotate(count=Count("id"))
                    .order_by("result")
                ),
            }
        )


class ReportsView(APIView):
    permission_classes = [IsAdministrator]

    def get(self, request):
        event_id = request.query_params.get("event_id")
        if not event_id:
            raise serializers.ValidationError(
                {"event_id": "This query parameter is required."}
            )
        try:
            event_uuid = serializers.UUIDField().run_validation(event_id)
        except serializers.ValidationError as error:
            raise serializers.ValidationError({"event_id": "Unknown event."}) from error
        event = get_object_or_404(Event, pk=event_uuid)
        return Response(
            {
                "event_id": str(event.id),
                "registration_sources": list(
                    Registration.objects.filter(event=event)
                    .values("source")
                    .annotate(count=Count("id"))
                    .order_by("source")
                ),
                "ticket_statuses": list(
                    Ticket.objects.filter(registration__event=event)
                    .values("status")
                    .annotate(count=Count("id"))
                    .order_by("status")
                ),
                "scan_results": list(
                    TicketScan.objects.filter(event=event)
                    .values("result")
                    .annotate(count=Count("id"))
                    .order_by("result")
                ),
                "tiers": [
                    {
                        "tier_id": str(item["registration__ticket_tier_id"]),
                        "tier_name": item["registration__ticket_tier__name"],
                        "count": item["count"],
                    }
                    for item in Ticket.objects.filter(registration__event=event)
                    .values("registration__ticket_tier_id", "registration__ticket_tier__name")
                    .annotate(count=Count("id"))
                    .order_by("registration__ticket_tier__name")
                ],
                "gates": [
                    {
                        "gate": item["gate__name"],
                        "attempts": item["attempts"],
                        "granted": item["granted"],
                    }
                    for item in TicketScan.objects.filter(event=event)
                    .values("gate__name")
                    .annotate(
                        attempts=Count("id"),
                        granted=Count("id", filter=Q(result=TicketScan.Result.ENTRY_GRANTED)),
                    )
                    .order_by("gate__name")
                ],
            }
        )


class Echo:
    def write(self, value):
        return value


class ManifestExportView(APIView):
    permission_classes = [IsAdministrator]

    def get(self, request):
        event_id = request.query_params.get("event_id")
        if not event_id:
            raise serializers.ValidationError({"event_id": "This query parameter is required."})
        try:
            event_uuid = serializers.UUIDField().run_validation(event_id)
        except serializers.ValidationError as error:
            raise serializers.ValidationError({"event_id": "Unknown event."}) from error
        event = get_object_or_404(Event, pk=event_uuid)
        tickets = (
            Ticket.objects.filter(registration__event=event)
            .select_related("registration", "registration__event", "registration__ticket_tier")
            .order_by("issued_at")
        )
        writer = csv.writer(Echo())

        def rows():
            yield writer.writerow(
                (
                    "Registration ID",
                    "Ticket ID",
                    "Attendee Name",
                    "Buyer Name",
                    "Email",
                    "Phone",
                    "Event",
                    "Tier",
                    "Source",
                    "Ticket Status",
                    "Issued At",
                    "Used At",
                )
            )
            for ticket in tickets.iterator(chunk_size=500):
                registration = ticket.registration
                yield writer.writerow(
                    (
                        registration.id,
                        ticket.id,
                        ticket.attendee_name or registration.buyer_name,
                        registration.buyer_name,
                        registration.buyer_email,
                        registration.buyer_phone,
                        registration.event.name,
                        registration.ticket_tier.name,
                        registration.source,
                        ticket.status,
                        ticket.issued_at.isoformat(),
                        ticket.used_at.isoformat() if ticket.used_at else "",
                    )
                )

        response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="Soundarya_Dhandiya_{event.slug}_Report.csv"'
        )
        return response
