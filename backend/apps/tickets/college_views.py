from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdministrator
from apps.audit.models import AuditLog
from apps.events.models import Event
from .college_serializers import (
    CollegeStudentTicketCreateSerializer,
    CollegeStudentTicketImportSerializer,
    CollegeStudentTicketSerializer,
)
from .college_services import (
    CollegeTicketConflict,
    bulk_create_college_student_tickets,
    create_college_student_ticket,
    parse_college_student_csv,
)
from .models import CollegeStudentTicket


class CollegeStudentTicketCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    @method_decorator(csrf_protect)
    def post(self, request):
        serializer = CollegeStudentTicketCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = get_object_or_404(Event, pk=serializer.validated_data["event_id"])
        try:
            ticket = create_college_student_ticket(
                event=event,
                student_name=serializer.validated_data["student_name"],
                student_email=serializer.validated_data["student_email"],
                created_by=request.user,
                email_delivery_enabled=False,
            )
        except CollegeTicketConflict as error:
            raise error
        AuditLog.objects.create(
            actor=request.user,
            action="COLLEGE_STUDENT_TICKET_CREATED",
            resource_type="college_student_ticket",
            resource_id=str(ticket.id),
            metadata={"ticket_code": ticket.ticket_code},
        )
        return Response(
            CollegeStudentTicketSerializer(ticket).data,
            status=status.HTTP_201_CREATED,
        )


class CollegeStudentTicketImportView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @method_decorator(csrf_protect)
    def post(self, request):
        serializer = CollegeStudentTicketImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = get_object_or_404(Event, pk=serializer.validated_data["event_id"])
        try:
            rows = parse_college_student_csv(
                serializer.validated_data["file"].read()
            )
            result = bulk_create_college_student_tickets(
                event=event,
                rows=rows,
                created_by=request.user,
                email_delivery_enabled=False,
                dry_run=serializer.validated_data["dry_run"],
            )
        except DjangoValidationError as error:
            raise ValidationError(error.message_dict) from error

        if result["created"]:
            AuditLog.objects.create(
                actor=request.user,
                action="COLLEGE_STUDENT_TICKETS_IMPORTED",
                resource_type="college_student_ticket",
                metadata={
                    "event_id": str(event.id),
                    "count": len(result["created"]),
                },
            )
        response_data = {
            **result,
            "created": CollegeStudentTicketSerializer(
                result["created"],
                many=True,
            ).data,
        }
        return Response(
            response_data,
            status=status.HTTP_200_OK
            if serializer.validated_data["dry_run"] or result["error_count"]
            else status.HTTP_201_CREATED,
        )


class CollegeStudentTicketDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request, ticket_id):
        ticket = get_object_or_404(
            CollegeStudentTicket.objects.select_related("event", "created_by"),
            pk=ticket_id,
        )
        return Response(CollegeStudentTicketSerializer(ticket).data)


class CollegeStudentTicketPdfView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request, ticket_id):
        ticket = get_object_or_404(CollegeStudentTicket, pk=ticket_id)
        from apps.payments.pdf import generate_college_student_ticket_pdf

        response = HttpResponse(
            generate_college_student_ticket_pdf(ticket),
            content_type="application/pdf",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="ticket-{ticket.ticket_code}.pdf"'
        )
        response["Cache-Control"] = "private, no-store"
        return response
