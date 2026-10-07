from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdministrator
from apps.scanning.models import TicketScan
from .models import Ticket
from .serializers import TicketSerializer
from .services import cancel_ticket


def ticket_queryset():
    return Ticket.objects.select_related(
        "registration",
        "registration__event",
        "registration__ticket_tier",
    ).prefetch_related(
        Prefetch(
            "scan_history",
            queryset=TicketScan.objects.filter(
                result=TicketScan.Result.ENTRY_GRANTED
            ).select_related("gate"),
        )
    )


class TicketListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ("ADMIN", "REGISTRATION_STAFF"):
            raise PermissionDenied("Ticket management access is required.")
        tickets = ticket_queryset()
        event_id = request.query_params.get("event_id")
        if event_id:
            try:
                event_uuid = serializers.UUIDField().run_validation(event_id)
            except serializers.ValidationError as error:
                raise serializers.ValidationError({"event_id": "Unknown event."}) from error
            tickets = tickets.filter(registration__event_id=event_uuid)
        ticket_status = request.query_params.get("status")
        if ticket_status:
            if ticket_status not in Ticket.Status.values:
                raise serializers.ValidationError({"status": "Unknown ticket status."})
            tickets = tickets.filter(status=ticket_status)
        search = request.query_params.get("search", "").strip()
        if search:
            tickets = tickets.filter(
                Q(id__icontains=search)
                | Q(registration__buyer_name__icontains=search)
                | Q(registration__buyer_email__icontains=search)
                | Q(registration__buyer_phone__icontains=search)
                | Q(registration__event__name__icontains=search)
            )
        paginator = self.paginator
        page = paginator.paginate_queryset(tickets, request, view=self)
        return paginator.get_paginated_response(
            TicketSerializer(page, many=True, context={"request": request}).data
        )

    @property
    def paginator(self):
        if not hasattr(self, "_paginator"):
            from config.pagination import StandardPagination

            self._paginator = StandardPagination()
        return self._paginator


class TicketDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, ticket_id):
        ticket = get_object_or_404(ticket_queryset(), pk=ticket_id)
        return Response(TicketSerializer(ticket, context={"request": request}).data)


class TicketCancelView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    @method_decorator(csrf_protect)
    def post(self, request, ticket_id):
        ticket = cancel_ticket(ticket_id, request.user)
        ticket = ticket_queryset().get(pk=ticket.pk)
        return Response(
            TicketSerializer(ticket, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )
