import base64
import uuid
from datetime import timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

import cloudinary.exceptions
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.events.models import Event, TicketTier
from apps.payments.models import (
    Payment,
    PaymentIntent,
    PaymentProofDecision,
    TicketDelivery,
    TicketSheetSync,
)
from apps.payments.cloudinary_storage import (
    PaymentProofStorageUnavailable,
    delete_unreferenced_payment_proof,
    get_payment_proof_content,
    upload_payment_proof as upload_cloudinary_payment_proof,
)
from apps.payments.proof import (
    PaymentProofConflict,
    expire_payment_proof_reservations,
)
from apps.registrations.models import InventoryReservation, Registration
from apps.scanning.models import Gate, StaffAssignment, TicketScan
from apps.scanning.services import scan_ticket
from apps.tickets.models import Ticket


PNG_IMAGE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAE0lEQVR4nGP8//8/AwMDEwMYAAAkBgMBXaJOiAAAAABJRU5ErkJggg=="
)


@override_settings(
    PAYMENT_PROOF_RESERVATION_HOURS=24,
    PAYMENT_PROOF_RESUBMISSION_HOURS=12,
    DJANGO_INTERNAL_API_KEY="n8n-test-token",
)
class ManualPaymentProofTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.upload_count = 0

        def upload_payment_proof(_image, *, image_format, image_size):
            self.upload_count += 1
            return {
                "public_id": (
                    "college-ticketing/payment-proofs/"
                    f"test-proof-{self.upload_count}"
                ),
                "asset_id": f"test-asset-{self.upload_count}",
                "version": 1,
                "format": image_format,
                "size": image_size,
            }

        upload_patch = patch(
            "apps.payments.proof.upload_payment_proof",
            side_effect=upload_payment_proof,
        )
        self.upload_mock = upload_patch.start()
        self.addCleanup(upload_patch.stop)
        cleanup_patch = patch(
            "apps.payments.proof.delete_unreferenced_payment_proof"
        )
        self.cleanup_mock = cleanup_patch.start()
        self.addCleanup(cleanup_patch.stop)
        start = timezone.now() + timedelta(days=2)
        self.event = Event.objects.create(
            slug="proof-test-event",
            name="Proof Test Event",
            start_at=start,
            end_at=start + timedelta(hours=3),
            venue="Test Venue",
            city="Bengaluru",
            address="Test Address",
            status=Event.Status.OPEN,
            registration_open=True,
            capacity=3,
        )
        self.tier = TicketTier.objects.create(
            event=self.event,
            slug="single",
            name="Single Ticket",
            price="149.00",
            admission_count=1,
        )
        self.admin = get_user_model().objects.create_user(
            "proof-admin@example.test",
            "Secure-test-pass-123!",
            name="Proof Admin",
            role="ADMIN",
        )
        self.payload = {
            "event_id": str(self.event.id),
            "ticket_tier_id": str(self.tier.id),
            "buyer": {
                "name": "Test Buyer",
                "email": "buyer@example.test",
                "phone": "+919876543210",
            },
            "attendee_names": ["Test Buyer"],
        }

    def start_registration(self):
        response = self.client.post(
            "/api/v1/payments/proof/registrations/",
            self.payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn("upi_id", response.data)
        self.assertNotIn("upi_qr_image_url", response.data)
        return response.data

    def submit_proof(
        self,
        registration,
        *,
        utr="UTR12345678",
        transaction_id="TXN123456789",
        key=None,
    ):
        return self.client.post(
            f"/api/v1/payments/proof/registrations/{registration['registration_id']}/submit/",
            {
                "utr_reference": utr,
                "transaction_id": transaction_id,
                "screenshot": SimpleUploadedFile(
                    "payment.png",
                    PNG_IMAGE,
                    content_type="image/png",
                ),
            },
            format="multipart",
            HTTP_X_PROOF_ACCESS_TOKEN=registration["proof_access_token"],
            HTTP_IDEMPOTENCY_KEY=str(key or uuid.uuid4()),
        )

    def test_reservation_and_proof_submission_are_idempotent_and_issue_no_ticket(self):
        key = str(uuid.uuid4())
        first = self.client.post(
            "/api/v1/payments/proof/registrations/",
            self.payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        replay = self.client.post(
            "/api/v1/payments/proof/registrations/",
            self.payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(first.data["registration_id"], replay.data["registration_id"])
        self.assertEqual(first.data["proof_access_token"], replay.data["proof_access_token"])
        self.assertEqual(Ticket.objects.count(), 0)

        reservation = first.data
        submission_key = uuid.uuid4()
        submitted = self.submit_proof(reservation, key=submission_key)
        replayed_submission = self.submit_proof(reservation, key=submission_key)
        self.assertEqual(submitted.status_code, 201, submitted.data)
        self.assertEqual(replayed_submission.status_code, 201, replayed_submission.data)
        self.assertEqual(submitted.data["ticket_id"], replayed_submission.data["ticket_id"])
        self.assertEqual(submitted.data["ticket_id"], "SIMS-DN-20260001")
        registration = Registration.objects.get(pk=reservation["registration_id"])
        payment = Payment.objects.get(intent__registration=registration)
        self.assertEqual(registration.status, Registration.Status.PENDING_VERIFICATION)
        self.assertEqual(payment.status, Payment.Status.PENDING_VERIFICATION)
        self.assertEqual(payment.utr_reference, "UTR12345678")
        self.assertEqual(payment.transaction_id, "TXN123456789")
        self.assertIsNone(payment.proof_screenshot)
        self.assertTrue(payment.proof_cloudinary_public_id.startswith(
            "college-ticketing/payment-proofs/"
        ))
        self.assertEqual(payment.proof_size_bytes, len(PNG_IMAGE))
        self.assertEqual(self.upload_mock.call_count, 1)
        self.assertEqual(registration.tickets.count(), 0)
        self.assertEqual(Ticket.objects.count(), 0)
        self.assertEqual(
            registration.inventory_reservation.status,
            InventoryReservation.Status.RESERVED,
        )
        self.assertIsNone(registration.inventory_reservation.expires_at)

        confirmation = self.client.get(
            f"/api/v1/payments/proof/registrations/{registration.pk}/ticket-id.pdf",
            HTTP_X_PROOF_ACCESS_TOKEN=reservation["proof_access_token"],
        )
        self.assertEqual(confirmation.status_code, 200)
        self.assertEqual(confirmation["Content-Type"], "application/pdf")
        self.assertTrue(confirmation.content.startswith(b"%PDF"))
        self.assertEqual(Ticket.objects.count(), 0)
        self.assertEqual(Payment.objects.filter(intent=payment.intent).count(), 1)

    def test_quantity_reserves_total_manual_amount_and_issues_unique_tickets(self):
        payload = {
            **self.payload,
            "quantity": 2,
            "attendee_names": ["Test Buyer", "Second Attendee"],
        }
        response = self.client.post(
            "/api/v1/payments/proof/registrations/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["amount"], 298)

        registration = Registration.objects.get(pk=response.data["registration_id"])
        self.assertEqual(registration.quantity, 2)
        self.assertEqual(registration.inventory_reservation.units_reserved, 2)
        submitted = self.submit_proof(response.data)
        self.assertEqual(submitted.status_code, 201, submitted.data)
        payment = Payment.objects.get(pk=submitted.data["payment_id"])
        self.assertFalse(TicketSheetSync.objects.exists())
        self.assertEqual(payment.amount, 29_800)

        self.client.force_authenticate(self.admin)
        approved = self.client.post(
            f"/api/v1/payments/proof/{payment.pk}/approve/",
            {"confirmed_received": True},
            format="json",
        )
        self.assertEqual(approved.status_code, 200, approved.data)
        tickets = list(registration.tickets.order_by("ticket_code"))
        self.assertEqual([ticket.attendee_name for ticket in tickets], payload["attendee_names"])
        self.assertEqual(len({ticket.ticket_code for ticket in tickets}), 2)

    def test_manual_quantity_cannot_exceed_remaining_event_capacity(self):
        self.event.capacity = 1
        self.event.save(update_fields=("capacity",))
        response = self.client.post(
            "/api/v1/payments/proof/registrations/",
            {
                **self.payload,
                "quantity": 2,
                "attendee_names": ["Test Buyer", "Second Attendee"],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(Registration.objects.count(), 0)

    def test_ticket_ids_increment_sequentially(self):
        first_registration = self.start_registration()
        first = self.submit_proof(first_registration)
        self.assertEqual(first.status_code, 201, first.data)

        self.payload["buyer"]["email"] = "second-buyer@example.test"
        second_registration = self.start_registration()
        second = self.submit_proof(
            second_registration,
            utr="UTR87654321",
            transaction_id="TXN987654321",
        )
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(first.data["ticket_id"], "SIMS-DN-20260001")
        self.assertEqual(second.data["ticket_id"], "SIMS-DN-20260002")

    def test_multiple_ticket_quantity_reserves_and_issues_unique_tickets(self):
        payload = {
            **self.payload,
            "quantity": 2,
            "attendee_names": ["Test Buyer", "Second Attendee"],
        }
        response = self.client.post(
            "/api/v1/payments/proof/registrations/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["amount"], 298.0)

        registration = Registration.objects.get(pk=response.data["registration_id"])
        intent = PaymentIntent.objects.get(registration=registration)
        self.assertEqual(intent.quantity, 2)
        self.assertEqual(registration.inventory_reservation.units_reserved, 2)

        submitted = self.submit_proof(response.data)
        self.assertEqual(submitted.status_code, 201, submitted.data)
        payment = Payment.objects.get(pk=submitted.data["payment_id"])
        self.client.force_authenticate(self.admin)
        approved = self.client.post(
            f"/api/v1/payments/proof/{payment.pk}/approve/",
            {"confirmed_received": True},
            format="json",
        )
        self.assertEqual(approved.status_code, 200, approved.data)

        tickets = list(registration.tickets.order_by("ticket_code"))
        self.assertEqual(len(tickets), 2)
        self.assertEqual(
            [ticket.attendee_name for ticket in tickets],
            ["Test Buyer", "Second Attendee"],
        )
        self.assertEqual(len({ticket.token for ticket in tickets}), 2)
        self.assertEqual(
            set(
                TicketSheetSync.objects.filter(
                    ticket__registration=registration
                ).values_list("ticket_id", flat=True)
            ),
            {ticket.id for ticket in tickets},
        )
        sheets_client = MagicMock()
        with patch(
            "apps.payments.management.commands.process_ticket_sheet_syncs.create_google_sheets_client",
            return_value=sheets_client,
        ):
            call_command(
                "process_ticket_sheet_syncs",
                "--limit",
                "50",
                stdout=StringIO(),
            )
        self.assertEqual(sheets_client.upsert_ticket_row.call_count, 2)
        self.assertEqual(
            {
                call.args[1]["ticket_id"]
                for call in sheets_client.upsert_ticket_row.call_args_list
            },
            {str(ticket.pk) for ticket in tickets},
        )

    def test_multiple_ticket_quantity_requires_one_name_per_admission(self):
        response = self.client.post(
            "/api/v1/payments/proof/registrations/",
            {**self.payload, "quantity": 2},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Registration.objects.count(), 0)
        self.assertEqual(PaymentIntent.objects.count(), 0)

    def test_rejection_resubmission_keeps_ticket_id_and_expiry_releases_inventory(self):
        registration_result = self.start_registration()
        submitted = self.submit_proof(registration_result)
        self.assertEqual(submitted.status_code, 201, submitted.data)
        original_ticket_id = submitted.data["ticket_id"]
        payment = Payment.objects.get(pk=submitted.data["payment_id"])
        self.client.force_authenticate(self.admin)

        rejected = self.client.post(
            f"/api/v1/payments/proof/{payment.pk}/reject/",
            {"reason": "The bank transaction is not visible."},
            format="json",
        )
        self.assertEqual(rejected.status_code, 200, rejected.data)
        self.assertEqual(rejected.data["rejection_email_status"], "DISABLED")
        n8n = APIClient()
        n8n.credentials(HTTP_AUTHORIZATION="Token n8n-test-token")
        pending = n8n.get("/api/internal/email-jobs/pending")
        self.assertEqual(pending.status_code, 200, pending.data)
        self.assertEqual(pending.data["count"], 0)
        dashboard = self.client.get("/api/v1/payments/proof/dashboard/")
        self.assertEqual(dashboard.status_code, 200, dashboard.data)
        self.assertEqual(dashboard.data["proofs"][0]["rejected_by"], "Proof Admin")
        registration = Registration.objects.get(pk=registration_result["registration_id"])
        payment.refresh_from_db()
        self.assertEqual(registration.ticket_id, original_ticket_id)
        self.assertEqual(registration.status, Registration.Status.REJECTED)
        self.assertEqual(registration.tickets.count(), 0)
        self.assertFalse(TicketSheetSync.objects.exists())
        self.assertEqual(
            registration.inventory_reservation.expires_at,
            payment.rejection_deadline,
        )

        corrected = self.submit_proof(
            registration_result,
            utr="UTR87654321",
            transaction_id="TXN987654321",
        )
        self.assertEqual(corrected.status_code, 201, corrected.data)
        registration.refresh_from_db()
        self.assertEqual(registration.ticket_id, original_ticket_id)
        self.assertEqual(registration.status, Registration.Status.PENDING_VERIFICATION)
        self.assertEqual(
            PaymentProofDecision.objects.filter(
                registration=registration,
                action=PaymentProofDecision.Action.RESUBMITTED,
            ).count(),
            1,
        )
        self.assertEqual(Ticket.objects.count(), 0)

        self.client.force_authenticate(None)
        rejected_again = self.client.post(
            f"/api/v1/payments/proof/{corrected.data['payment_id']}/reject/",
            {"reason": "The transaction amount did not match."},
            format="json",
        )
        self.assertEqual(rejected_again.status_code, 401)

        self.client.force_authenticate(self.admin)
        rejected_corrected = self.client.post(
            f"/api/v1/payments/proof/{corrected.data['payment_id']}/reject/",
            {"reason": "The transaction amount did not match."},
            format="json",
        )
        self.assertEqual(rejected_corrected.status_code, 200, rejected_corrected.data)
        expired = expire_payment_proof_reservations(
            now=timezone.now() + timedelta(hours=13)
        )
        self.assertEqual(expired, 1)
        registration.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.EXPIRED)
        self.assertEqual(
            registration.inventory_reservation.status,
            InventoryReservation.Status.RELEASED,
        )
        self.assertEqual(Ticket.objects.count(), 0)


    def test_admin_approval_checks_confirmation_and_issues_one_final_ticket(self):
        registration_result = self.start_registration()
        submitted = self.submit_proof(registration_result)
        self.assertEqual(submitted.status_code, 201, submitted.data)
        payment = Payment.objects.get(pk=submitted.data["payment_id"])

        n8n = APIClient()
        n8n.credentials(HTTP_AUTHORIZATION="Token n8n-test-token")
        pending = n8n.get("/api/internal/email-jobs/pending")
        self.assertEqual(pending.status_code, 200, pending.data)
        self.assertEqual(pending.data["count"], 0)

        tickets_url = (
            f"/api/v1/payments/proof/registrations/"
            f"{registration_result['registration_id']}/tickets.pdf"
        )
        not_issued = self.client.get(
            tickets_url,
            HTTP_X_PROOF_ACCESS_TOKEN=registration_result["proof_access_token"],
        )
        self.assertEqual(not_issued.status_code, 404)

        unauthorized = self.client.post(
            f"/api/v1/payments/proof/{payment.pk}/approve/",
            {"confirmed_received": True},
            format="json",
        )
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(Ticket.objects.count(), 0)

        self.client.force_authenticate(self.admin)

        not_confirmed = self.client.post(
            f"/api/v1/payments/proof/{payment.pk}/approve/",
            {"confirmed_received": False},
            format="json",
        )
        self.assertEqual(not_confirmed.status_code, 400)
        self.assertEqual(Ticket.objects.count(), 0)

        approved = self.client.post(
            f"/api/v1/payments/proof/{payment.pk}/approve/",
            {"confirmed_received": True},
            format="json",
        )
        repeated = self.client.post(
            f"/api/v1/payments/proof/{payment.pk}/approve/",
            {"confirmed_received": True},
            format="json",
        )
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertFalse(approved.data["replayed"])
        self.assertEqual(repeated.status_code, 200, repeated.data)
        self.assertTrue(repeated.data["replayed"])

        registration = Registration.objects.get(pk=registration_result["registration_id"])
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.VERIFIED)
        self.assertEqual(payment.verified_by, self.admin)
        self.assertIsNotNone(payment.verified_at)
        self.assertEqual(registration.status, Registration.Status.TICKET_ISSUED)
        self.assertEqual(registration.tickets.count(), 1)
        self.assertEqual(TicketDelivery.objects.filter(ticket__registration=registration).count(), 0)
        self.assertEqual(approved.data["email_status"], "DISABLED")
        self.assertEqual(
            TicketSheetSync.objects.filter(
                ticket__registration=registration,
                status=TicketSheetSync.Status.PENDING,
            ).count(),
            1,
        )

        TicketSheetSync.objects.filter(ticket__registration=registration).delete()
        repaired = self.client.post(
            f"/api/v1/payments/proof/{payment.pk}/approve/",
            {"confirmed_received": True},
            format="json",
        )
        self.assertEqual(repaired.status_code, 200, repaired.data)
        self.assertTrue(repaired.data["replayed"])
        self.assertEqual(
            TicketSheetSync.objects.filter(ticket__registration=registration).count(),
            1,
        )

        sheets_client = MagicMock()
        with patch(
            "apps.payments.management.commands.process_ticket_sheet_syncs.create_google_sheets_client",
            return_value=sheets_client,
        ):
            call_command(
                "process_ticket_sheet_syncs",
                "--limit",
                "50",
                stdout=StringIO(),
            )
        sync = TicketSheetSync.objects.get(ticket__registration=registration)
        self.assertEqual(sync.status, TicketSheetSync.Status.SYNCED)
        sheets_client.upsert_ticket_row.assert_called_once()
        sheet_name, sheet_row = sheets_client.upsert_ticket_row.call_args.args
        ticket = registration.tickets.get()
        self.assertEqual(sheet_name, "Online_Tickets")
        self.assertEqual(sheet_row["ticket_id"], str(ticket.pk))
        self.assertEqual(sheet_row["registration_id"], str(registration.pk))
        self.assertEqual(sheet_row["payment_status"], Payment.Status.VERIFIED)
        self.assertEqual(sheet_row["ticket_status"], Ticket.Status.ISSUED)
        self.client.force_authenticate(None)
        with patch(
            "apps.payments.pdf.generate_tickets_pdf",
            return_value=b"%PDF-issued-ticket",
        ):
            downloaded = self.client.get(
                tickets_url,
                HTTP_X_PROOF_ACCESS_TOKEN=registration_result["proof_access_token"],
            )
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded["Content-Type"], "application/pdf")
        self.assertTrue(downloaded.content.startswith(b"%PDF"))
        jobs_response = n8n.get("/api/internal/email-jobs/pending")
        self.assertEqual(jobs_response.status_code, 200, jobs_response.data)
        self.assertEqual(jobs_response.data, {"count": 0, "jobs": []})
        self.assertEqual(
            registration.inventory_reservation.status,
            InventoryReservation.Status.CONSUMED,
        )
        self.assertEqual(
            PaymentProofDecision.objects.filter(
                payment=payment,
                action=PaymentProofDecision.Action.APPROVED,
            ).count(),
            1,
        )

        gate = Gate.objects.create(event=self.event, name="Main gate")
        scanner = get_user_model().objects.create_user(
            "proof-scanner@example.test",
            "Secure-test-pass-123!",
            name="Proof Scanner",
            role="SCANNER_STAFF",
        )
        StaffAssignment.objects.create(user=scanner, gate=gate)
        scan = scan_ticket(token=registration.tickets.get().token, scanner=scanner)
        self.assertEqual(scan.result, TicketScan.Result.ENTRY_GRANTED)

    def test_duplicate_utr_is_rejected_across_registrations(self):
        first = self.start_registration()
        first_result = self.submit_proof(first)
        self.assertEqual(first_result.status_code, 201, first_result.data)

        self.event.capacity = 3
        self.event.save(update_fields=("capacity",))
        self.payload["buyer"]["email"] = "second-buyer@example.test"
        second = self.start_registration()
        duplicate = self.submit_proof(second)
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_duplicate_transaction_id_is_rejected_across_registrations(self):
        first = self.start_registration()
        first_result = self.submit_proof(first, transaction_id="TXN11223344")
        self.assertEqual(first_result.status_code, 201, first_result.data)

        self.event.capacity = 3
        self.event.save(update_fields=("capacity",))
        self.payload["buyer"]["email"] = "second-buyer@example.test"
        second = self.start_registration()
        duplicate = self.submit_proof(
            second,
            utr="UTR87654321",
            transaction_id="TXN11223344",
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_status_capability_is_required(self):
        registration = self.start_registration()
        query_token = self.client.get(
            f"/api/v1/payments/proof/registrations/{registration['registration_id']}/",
            {"token": registration["proof_access_token"]},
        )
        self.assertEqual(query_token.status_code, 400)
        response = self.client.get(
            f"/api/v1/payments/proof/registrations/{registration['registration_id']}/",
            HTTP_X_PROOF_ACCESS_TOKEN=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 404)

    def test_proof_upload_failure_does_not_create_payment_or_ticket_id(self):
        registration = self.start_registration()
        with patch(
            "apps.payments.proof.upload_payment_proof",
            side_effect=PaymentProofStorageUnavailable(),
        ):
            failed = self.submit_proof(registration)
        self.assertEqual(failed.status_code, 503, failed.data)
        stored_registration = Registration.objects.get(
            pk=registration["registration_id"]
        )
        self.assertIsNone(stored_registration.ticket_id)
        self.assertEqual(Payment.objects.filter(provider=Payment.Provider.UPI_MANUAL).count(), 0)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_database_failure_cleans_uploaded_asset_and_does_not_assign_ticket_id(self):
        registration = self.start_registration()
        self.client.raise_request_exception = False
        with patch(
            "apps.payments.proof.Payment.objects.create",
            side_effect=DatabaseError("simulated persistence failure"),
        ):
            failed = self.submit_proof(registration)
        self.assertEqual(failed.status_code, 500)
        self.cleanup_mock.assert_called_once_with(
            "college-ticketing/payment-proofs/test-proof-1"
        )
        self.assertIsNone(
            Registration.objects.get(pk=registration["registration_id"]).ticket_id
        )

    def test_payment_screenshot_validation_rejects_invalid_and_oversized_images(self):
        registration = self.start_registration()
        invalid = self.client.post(
            f"/api/v1/payments/proof/registrations/{registration['registration_id']}/submit/",
            {
                "utr_reference": "UTR12345678",
                "transaction_id": "TXN123456789",
                "screenshot": SimpleUploadedFile(
                    "fake.png",
                    b"not an image",
                    content_type="image/png",
                ),
            },
            format="multipart",
            HTTP_X_PROOF_ACCESS_TOKEN=registration["proof_access_token"],
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(invalid.status_code, 400)

        oversized = self.client.post(
            f"/api/v1/payments/proof/registrations/{registration['registration_id']}/submit/",
            {
                "utr_reference": "UTR12345678",
                "transaction_id": "TXN123456789",
                "screenshot": SimpleUploadedFile(
                    "large.png",
                    b"x" * (5 * 1024 * 1024 + 1),
                    content_type="image/png",
                ),
            },
            format="multipart",
            HTTP_X_PROOF_ACCESS_TOKEN=registration["proof_access_token"],
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(oversized.status_code, 400)
        self.assertEqual(self.upload_mock.call_count, 0)
        self.assertIsNone(
            Registration.objects.get(pk=registration["registration_id"]).ticket_id
        )

    def test_admin_proof_screenshot_endpoint_requires_admin_and_proxies_image(self):
        registration = self.start_registration()
        submitted = self.submit_proof(registration)
        payment = Payment.objects.get(pk=submitted.data["payment_id"])
        screenshot_url = f"/api/v1/payments/proof/{payment.pk}/screenshot/"

        unauthorized = self.client.get(screenshot_url)
        self.assertEqual(unauthorized.status_code, 401)

        scanner = get_user_model().objects.create_user(
            "proof-viewer-scanner@example.test",
            "Secure-test-pass-123!",
            role="SCANNER_STAFF",
        )
        self.client.force_authenticate(scanner)
        forbidden = self.client.get(screenshot_url)
        self.assertEqual(forbidden.status_code, 403)

        self.client.force_authenticate(self.admin)
        with patch(
            "apps.payments.proof.get_payment_proof_content",
            return_value=PNG_IMAGE,
        ) as get_content:
            authorized = self.client.get(screenshot_url)
        self.assertEqual(authorized.status_code, 200)
        self.assertEqual(authorized.content, PNG_IMAGE)
        self.assertEqual(authorized["Cache-Control"], "no-store, private")
        get_content.assert_called_once()


class CloudinaryPaymentProofStorageTests(TestCase):
    @override_settings(
        CLOUDINARY_CLOUD_NAME="test-cloud",
        CLOUDINARY_API_KEY="test-key",
        CLOUDINARY_API_SECRET="test-secret",
        CLOUDINARY_PAYMENT_PROOF_FOLDER="college-ticketing/payment-proofs",
    )
    def test_upload_requires_authenticated_asset_type_and_uses_random_public_id(self):
        result = {
            "public_id": "college-ticketing/payment-proofs/opaque-id",
            "asset_id": "opaque-asset-id",
            "type": "authenticated",
            "format": "png",
            "bytes": len(PNG_IMAGE),
            "version": 123,
        }
        with patch(
            "apps.payments.cloudinary_storage.cloudinary.uploader.upload",
            return_value=result,
        ) as cloudinary_upload:
            stored = upload_cloudinary_payment_proof(
                PNG_IMAGE,
                image_format="png",
                image_size=len(PNG_IMAGE),
            )
        self.assertEqual(stored["public_id"], result["public_id"])
        self.assertEqual(cloudinary_upload.call_args.kwargs["type"], "authenticated")
        self.assertEqual(
            cloudinary_upload.call_args.kwargs["asset_folder"],
            "college-ticketing/payment-proofs",
        )
        self.assertTrue(
            cloudinary_upload.call_args.kwargs["public_id"].startswith(
                "college-ticketing/payment-proofs/"
            )
        )
        self.assertFalse(cloudinary_upload.call_args.kwargs["use_filename"])

    @override_settings(
        CLOUDINARY_CLOUD_NAME="",
        CLOUDINARY_API_KEY="",
        CLOUDINARY_API_SECRET="",
    )
    def test_missing_cloudinary_credentials_fail_closed(self):
        with self.assertRaises(PaymentProofStorageUnavailable):
            upload_cloudinary_payment_proof(
                PNG_IMAGE,
                image_format="png",
                image_size=len(PNG_IMAGE),
            )

    @override_settings(
        CLOUDINARY_CLOUD_NAME="test-cloud",
        CLOUDINARY_API_KEY="test-key",
        CLOUDINARY_API_SECRET="test-secret",
    )
    def test_cloudinary_sdk_upload_failure_is_sanitized(self):
        with patch(
            "apps.payments.cloudinary_storage.cloudinary.uploader.upload",
            side_effect=cloudinary.exceptions.Error("provider unavailable"),
        ):
            with self.assertRaises(PaymentProofStorageUnavailable):
                upload_cloudinary_payment_proof(
                    PNG_IMAGE,
                    image_format="png",
                    image_size=len(PNG_IMAGE),
                )

    @override_settings(
        CLOUDINARY_CLOUD_NAME="test-cloud",
        CLOUDINARY_API_KEY="test-key",
        CLOUDINARY_API_SECRET="test-secret",
    )
    def test_cleanup_never_deletes_an_asset_referenced_by_a_payment(self):
        referenced = MagicMock()
        referenced.exists.return_value = True
        with (
            patch(
                "apps.payments.cloudinary_storage.Payment.objects.filter",
                return_value=referenced,
            ),
            patch(
                "apps.payments.cloudinary_storage.cloudinary.uploader.destroy"
            ) as destroy,
        ):
            delete_unreferenced_payment_proof(
                "college-ticketing/payment-proofs/referenced"
            )
        destroy.assert_not_called()

    @override_settings(
        CLOUDINARY_CLOUD_NAME="test-cloud",
        CLOUDINARY_API_KEY="test-key",
        CLOUDINARY_API_SECRET="test-secret",
    )
    def test_authenticated_asset_is_fetched_only_by_server_side_signed_url(self):
        payment = Payment(
            proof_cloudinary_public_id=(
                "college-ticketing/payment-proofs/private-proof"
            ),
            proof_cloudinary_version=123,
            proof_format="png",
            proof_content_type="image/png",
        )
        response = MagicMock()
        response.status_code = 200
        response.__enter__.return_value = response
        response.iter_content.return_value = [PNG_IMAGE]
        with patch(
            "apps.payments.cloudinary_storage.requests.get",
            return_value=response,
        ) as cloudinary_get:
            content = get_payment_proof_content(payment)
        signed_url = cloudinary_get.call_args.args[0]
        self.assertIn("/image/authenticated/", signed_url)
        self.assertIn("/s--", signed_url)
        self.assertEqual(cloudinary_get.call_args.kwargs["allow_redirects"], False)
        self.assertEqual(content, PNG_IMAGE)
