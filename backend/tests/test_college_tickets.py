import io
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.events.models import Event, TicketTier
from apps.payments.sheets import ensure_ticket_sheet_syncs
from apps.payments.models import Payment, PaymentIntent, TicketDelivery
from apps.registrations.models import Registration
from apps.registrations.services import create_registration
from apps.scanning.models import Gate, StaffAssignment, TicketScan
from apps.scanning.services import scan_ticket
from apps.tickets.college_services import (
    CollegeTicketConflict,
    bulk_create_college_student_tickets,
    create_college_student_ticket,
    parse_college_student_csv,
)
from apps.tickets.models import CollegeStudentTicket, Ticket


@override_settings(
    DJANGO_INTERNAL_API_KEY="n8n-test-token",
    COLLEGE_TICKET_ID_PREFIX="SIMS-DN",
)
class CollegeStudentTicketTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        start = timezone.now() + timedelta(days=3)
        self.event = Event.objects.create(
            slug="college-ticket-event",
            name="College Ticket Event",
            start_at=start,
            end_at=start + timedelta(hours=3),
            venue="Soundarya College Campus",
            city="Bengaluru",
            address="Test address",
            status=Event.Status.OPEN,
            registration_open=True,
            capacity=100,
        )
        self.tier = TicketTier.objects.create(
            event=self.event,
            slug="single",
            name="Single Ticket",
            price="149.00",
        )
        self.admin = get_user_model().objects.create_user(
            "college-admin@example.test",
            "Secure-test-pass-123!",
            name="College Admin",
            role="ADMIN",
        )

    def make_registration(self, *, source, email, number):
        registration, tickets = create_registration(
            event_id=self.event.id,
            tier_id=self.tier.id,
            buyer={
                "name": f"Ticket Buyer {number}",
                "email": email,
                "phone": "+919876543210",
            },
            source=source,
            created_by=self.admin if source == Registration.Source.ON_SPOT else None,
            attendee_names=[f"Attendee {number}"],
            payment_confirmation=(
                {"payment_received": True, "payment_method": "CASH"}
                if source == Registration.Source.ON_SPOT
                else None
            ),
        )
        return registration, tickets



    def test_individual_tickets_use_a_locked_sequential_code_and_unique_qr_tokens(self):
        first = create_college_student_ticket(
            event=self.event,
            student_name=" Student One ",
            student_email="Student@One.Example",
        )
        second = create_college_student_ticket(
            event=self.event,
            student_name="Student Two",
            student_email="student2@example.test",
        )

        self.assertEqual(first.ticket_code, f"SIMS-DN-{self.event.start_at.year}-SIMS001")
        self.assertEqual(second.ticket_code, f"SIMS-DN-{self.event.start_at.year}-SIMS002")
        self.assertNotEqual(first.token, second.token)
        self.assertEqual(first.student_name, "Student One")
        self.assertEqual(first.student_email, "student@one.example")
        self.assertFalse(first.email_delivery_enabled)
        self.assertEqual(CollegeStudentTicket.objects.count(), 2)

    def test_duplicate_student_email_for_event_is_rejected(self):
        create_college_student_ticket(
            event=self.event,
            student_name="Student",
            student_email="same@example.test",
        )
        with self.assertRaises(CollegeTicketConflict):
            create_college_student_ticket(
                event=self.event,
                student_name="Same Student",
                student_email="SAME@example.test",
            )
        self.assertEqual(CollegeStudentTicket.objects.count(), 1)

    def test_bulk_import_dry_run_and_invalid_batch_do_not_create_records(self):
        rows = [
            {"student_name": "Valid Student", "student_email": "valid@example.test"},
            {"student_name": "", "student_email": "invalid@example.test"},
        ]
        result = bulk_create_college_student_tickets(
            event=self.event,
            rows=rows,
            dry_run=True,
        )
        self.assertEqual(result["valid_count"], 1)
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(CollegeStudentTicket.objects.count(), 0)

        result = bulk_create_college_student_tickets(event=self.event, rows=rows)
        self.assertEqual(result["created"], [])
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(CollegeStudentTicket.objects.count(), 0)

    def test_bulk_import_reports_duplicates_and_creates_only_a_valid_batch(self):
        result = bulk_create_college_student_tickets(
            event=self.event,
            rows=[
                {"student_name": "One", "student_email": "one@example.test"},
                {"student_name": "Duplicate One", "student_email": "ONE@example.test"},
                {"student_name": "Two", "student_email": "two@example.test"},
            ],
            created_by=self.admin,
            email_delivery_enabled=True,
        )
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["created"], [])
        self.assertEqual(CollegeStudentTicket.objects.count(), 0)

        result = bulk_create_college_student_tickets(
            event=self.event,
            rows=[
                {"student_name": "One", "student_email": "one@example.test"},
                {"student_name": "Two", "student_email": "two@example.test"},
            ],
            created_by=self.admin,
        )
        self.assertEqual(result["valid_count"], 2)
        self.assertEqual(
            [ticket.ticket_code for ticket in result["created"]],
            [
                f"SIMS-DN-{self.event.start_at.year}-SIMS001",
                f"SIMS-DN-{self.event.start_at.year}-SIMS002",
            ],
        )

    def test_csv_parser_requires_headers_and_normalizes_header_whitespace(self):
        rows = parse_college_student_csv(
            b" student_name , student_email \nStudent,student@example.test\n"
        )
        self.assertEqual(
            rows,
            [{"student_name": "Student", "student_email": "student@example.test"}],
        )
        with self.assertRaises(DjangoValidationError):
            parse_college_student_csv(b"name,email\nStudent,student@example.test\n")

    def test_college_pdf_uses_student_code_and_qr_token(self):
        ticket = create_college_student_ticket(
            event=self.event,
            student_name="PDF Student",
            student_email="pdf@example.test",
        )
        with patch("apps.payments.pdf.TicketQr") as qr:
            from apps.payments.pdf import generate_college_student_ticket_pdf

            pdf = generate_college_student_ticket_pdf(ticket)

        self.assertTrue(pdf.startswith(b"%PDF"))
        qr.assert_called_once_with(ticket.token, size=42 * 2.834645669291339)

    def test_delivery_requires_exactly_one_ticket_reference(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TicketDelivery.objects.create(
                    recipient="invalid@example.test",
                )

        registration, tickets = self.make_registration(
            source=Registration.Source.ON_SPOT,
            email="both@example.test",
            number=1,
        )
        college_ticket = create_college_student_ticket(
            event=self.event,
            student_name="College",
            student_email="college@example.test",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TicketDelivery.objects.create(
                    ticket=tickets[0],
                    college_ticket=college_ticket,
                    recipient="both@example.test",
                )


    def test_admin_can_create_view_but_email_delivery_is_disabled(self):
        response = self.client.post(
            "/api/v1/college-student-tickets/",
            {
                "event_id": str(self.event.id),
                "student_name": "API Student",
                "student_email": "api-student@example.test",
                "email_delivery_enabled": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 401)

        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/v1/college-student-tickets/",
            {
                "event_id": str(self.event.id),
                "student_name": "API Student",
                "student_email": "api-student@example.test",
                "email_delivery_enabled": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn("token", response.data)
        ticket_id = response.data["id"]

        detail = self.client.get(f"/api/v1/college-student-tickets/{ticket_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertFalse(response.data["email_delivery_enabled"])
        self.assertEqual(response.data["delivery_status"], "DISABLED")
        self.assertFalse(detail.data["email_delivery_enabled"])
        self.assertEqual(detail.data["delivery_status"], "DISABLED")
        no_email_route = self.client.post(
            f"/api/v1/college-student-tickets/{ticket_id}/queue-email/",
            {},
            format="json",
        )
        self.assertEqual(no_email_route.status_code, 404)
        self.assertFalse(TicketDelivery.objects.exists())

    def test_import_api_validates_csv_and_creates_records(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/v1/college-student-tickets/import/",
            {
                "event_id": str(self.event.id),
                "file": SimpleUploadedFile(
                    "students.csv",
                    b"student_name,student_email\nCSV Student,csv@example.test\n",
                    content_type="text/csv",
                ),
                "dry_run": "false",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["valid_count"], 1)
        self.assertEqual(CollegeStudentTicket.objects.count(), 1)
        self.assertFalse(CollegeStudentTicket.objects.get().email_delivery_enabled)










    def test_college_ticket_qr_scans_through_existing_staff_check_in(self):
        ticket = create_college_student_ticket(
            event=self.event,
            student_name="Scan Student",
            student_email="scan@example.test",
        )
        gate = Gate.objects.create(event=self.event, name="Student Gate")
        scanner = get_user_model().objects.create_user(
            "college-scanner@example.test",
            "Secure-test-pass-123!",
            name="College Scanner",
            role="SCANNER_STAFF",
        )
        StaffAssignment.objects.create(user=scanner, gate=gate)

        scan = scan_ticket(token=ticket.token, scanner=scanner)

        self.assertEqual(scan.result, TicketScan.Result.ENTRY_GRANTED)
        self.assertEqual(scan.college_ticket_id, ticket.id)
        self.assertIsNone(scan.ticket_id)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, CollegeStudentTicket.Status.USED)
