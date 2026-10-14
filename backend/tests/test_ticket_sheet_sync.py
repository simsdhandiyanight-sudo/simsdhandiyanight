import uuid
from datetime import timedelta
from io import StringIO
from unittest.mock import Mock, patch

import requests
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.events.models import Event, TicketTier
from apps.payments.models import Payment, PaymentIntent, TicketDelivery, TicketSheetSync
from apps.payments.sheets import (
    SHEET_HEADERS,
    backfill_ticket_sheet_syncs,
    ensure_ticket_sheet_syncs,
    sheet_sync_data,
)
from apps.registrations.models import Registration
from apps.registrations.services import create_registration
from apps.scanning.models import Gate, StaffAssignment, TicketScan
from apps.scanning.services import scan_ticket
from apps.tickets.services import cancel_ticket
from apps.tickets.college_services import create_college_student_ticket
from apps.tickets.models import CollegeStudentTicket, Ticket


@override_settings(
    DJANGO_INTERNAL_API_KEY="sheet-sync-test-token",
    N8N_SHEET_SYNC_JOB_LEASE_MINUTES=10,
)
class TicketSheetSyncTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        start = timezone.now() + timedelta(days=2)
        self.event = Event.objects.create(
            slug="sheet-sync-event",
            name="Sheet Sync Event",
            start_at=start,
            end_at=start + timedelta(hours=3),
            venue="Test Venue",
            city="Bengaluru",
            address="Test Address",
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
            "sheet-admin@example.test",
            "Secure-test-pass-123!",
            name="Sheet Admin",
            role="ADMIN",
        )
        self.gate = Gate.objects.create(event=self.event, name="Sheet Sync Gate")
        StaffAssignment.objects.create(user=self.admin, gate=self.gate)

    def make_registration(self, *, source, email, number, quantity=1):
        attendee_names = [
            f"Sheet Attendee {number} {index + 1}"
            for index in range(quantity)
        ]
        registration, tickets = create_registration(
            event_id=self.event.id,
            tier_id=self.tier.id,
            buyer={
                "name": f"Sheet Buyer {number}",
                "email": email,
                "phone": "+919876543210",
            },
            source=source,
            created_by=self.admin if source == Registration.Source.ON_SPOT else None,
            quantity=quantity,
            attendee_names=attendee_names,
            payment_confirmation=(
                {"payment_received": True, "payment_method": "CASH"}
                if source == Registration.Source.ON_SPOT
                else None
            ),
        )
        return registration, tickets

    def make_paid_online_ticket(
        self,
        *,
        number=1,
        quantity=1,
        provider=Payment.Provider.UPI_MANUAL,
        provider_order_id=None,
        provider_payment_id=None,
    ):
        registration, tickets = self.make_registration(
            source=Registration.Source.ONLINE,
            email=f"online-sheet-{number}@example.test",
            number=number,
            quantity=quantity,
        )
        intent = PaymentIntent.objects.create(
            idempotency_key=uuid.uuid4(),
            request_hash="sheet-sync-online",
            event=self.event,
            ticket_tier=self.tier,
            buyer_name=registration.buyer_name,
            buyer_email=registration.buyer_email,
            buyer_phone=registration.buyer_phone,
            attendee_names=[ticket.attendee_name for ticket in tickets],
            quantity=quantity,
            status=PaymentIntent.Status.VERIFIED,
            registration=registration,
        )
        Payment.objects.create(
            intent=intent,
            provider=provider,
            provider_order_id=provider_order_id,
            provider_payment_id=provider_payment_id,
            amount=int(registration.ticket_tier.price * quantity * 100),
            currency="INR",
            status=(
                Payment.Status.CAPTURED
                if provider == Payment.Provider.PAYU
                else Payment.Status.VERIFIED
            ),
            verification_status=Payment.VerificationStatus.VERIFIED,
            ticket_issuance_status=Payment.TicketIssuanceStatus.ISSUED,
            verified_at=timezone.now(),
            verified_by=self.admin,
        )
        registration.status = Registration.Status.TICKET_ISSUED
        registration.save(update_fields=("status", "updated_at"))
        ensure_ticket_sheet_syncs(registration, tickets)
        return tickets[0]

    def auth_headers(self):
        return {"HTTP_AUTHORIZATION": "Token sheet-sync-test-token"}

    @override_settings(
        GOOGLE_APPS_SCRIPT_WEBHOOK_URL="https://script.google.com/macros/s/test/exec",
        GOOGLE_APPS_SCRIPT_WEBHOOK_SECRET="apps-script-test-secret",
    )
    def test_apps_script_delivery_upserts_each_eligible_ticket(self):
        first_ticket = self.make_paid_online_ticket(number=81, quantity=2)
        ticket_list = list(
            first_ticket.registration.tickets.order_by("ticket_code")
        )
        sync_ids = list(
            TicketSheetSync.objects.filter(
                ticket__registration=ticket_list[0].registration
            ).values_list("id", flat=True)
        )

        def response_for_request(_url, *, json, timeout):
            self.assertEqual(timeout, (3.05, 6))
            self.assertEqual(json["secret"], "apps-script-test-secret")
            records = json["tickets"]
            self.assertEqual(len(records), 2)
            self.assertEqual(
                {record["sheet_name"] for record in records},
                {"Online_Tickets"},
            )
            self.assertTrue(
                all(record["row"]["payment_status"] == "VERIFIED" for record in records)
            )
            response = Mock()
            response.json.return_value = {
                "success": True,
                "processed_ticket_ids": [
                    record["row"]["ticket_id"] for record in records
                ],
            }
            return response

        with patch(
            "apps.payments.apps_script_sync.requests.post",
            side_effect=response_for_request,
        ) as post, patch("apps.payments.apps_script_sync.time.sleep"):
            from apps.payments.apps_script_sync import dispatch_ticket_sheet_syncs

            dispatch_ticket_sheet_syncs(sync_ids)

        self.assertEqual(post.call_count, 1)
        self.assertEqual(
            set(
                TicketSheetSync.objects.filter(pk__in=sync_ids).values_list(
                    "status", flat=True
                )
            ),
            {TicketSheetSync.Status.SYNCED},
        )
        self.assertEqual(
            set(
                TicketSheetSync.objects.filter(pk__in=sync_ids).values_list(
                    "attempt_count", flat=True
                )
            ),
            {0},
        )

    @override_settings(
        GOOGLE_APPS_SCRIPT_WEBHOOK_URL="https://script.google.com/macros/s/test/exec",
        GOOGLE_APPS_SCRIPT_WEBHOOK_SECRET="apps-script-test-secret",
    )
    def test_apps_script_timeout_marks_job_failed_without_changing_ticket_payment(self):
        ticket = self.make_paid_online_ticket(number=82)
        sync = TicketSheetSync.objects.get(ticket=ticket)
        payment = Payment.objects.get(intent__registration=ticket.registration)

        with patch(
            "apps.payments.apps_script_sync.requests.post",
            side_effect=requests.Timeout("simulated timeout"),
        ) as post, patch("apps.payments.apps_script_sync.time.sleep"):
            from apps.payments.apps_script_sync import dispatch_ticket_sheet_syncs

            dispatch_ticket_sheet_syncs([sync.id])

        sync.refresh_from_db()
        payment.refresh_from_db()
        ticket.refresh_from_db()
        self.assertEqual(post.call_count, 3)
        self.assertEqual(sync.status, TicketSheetSync.Status.FAILED)
        self.assertEqual(sync.attempt_count, 3)
        self.assertIn("TIMEOUT", sync.failure_reason)
        self.assertEqual(payment.status, Payment.Status.VERIFIED)
        self.assertEqual(ticket.status, Ticket.Status.ISSUED)

    @override_settings(
        GOOGLE_APPS_SCRIPT_WEBHOOK_URL="",
        GOOGLE_APPS_SCRIPT_WEBHOOK_SECRET="",
    )
    def test_unconfigured_apps_script_keeps_outbox_job_visible_and_pending(self):
        ticket = self.make_paid_online_ticket(number=83)
        sync = TicketSheetSync.objects.get(ticket=ticket)

        from apps.payments.apps_script_sync import dispatch_ticket_sheet_syncs

        dispatch_ticket_sheet_syncs([sync.id])
        sync.refresh_from_db()
        self.assertEqual(sync.status, TicketSheetSync.Status.PENDING)
        self.assertEqual(sync.attempt_count, 0)
        self.assertEqual(sync.failure_reason, "APPS_SCRIPT_NOT_CONFIGURED")

    @override_settings(
        GOOGLE_APPS_SCRIPT_WEBHOOK_URL="https://script.google.com/macros/s/test/exec",
        GOOGLE_APPS_SCRIPT_WEBHOOK_SECRET="apps-script-test-secret",
    )
    def test_apps_script_application_error_is_failure_even_with_http_success(self):
        ticket = self.make_paid_online_ticket(number=84)
        sync = TicketSheetSync.objects.get(ticket=ticket)
        response = Mock()
        response.json.return_value = {
            "success": False,
            "processed_ticket_ids": [],
            "error_code": "AUTH_FAILED",
            "retryable": False,
        }

        with patch(
            "apps.payments.apps_script_sync.requests.post",
            return_value=response,
        ) as post:
            from apps.payments.apps_script_sync import dispatch_ticket_sheet_syncs

            dispatch_ticket_sheet_syncs([sync.id])

        sync.refresh_from_db()
        self.assertEqual(post.call_count, 1)
        self.assertEqual(sync.status, TicketSheetSync.Status.FAILED)
        self.assertIn("AUTH_FAILED", sync.failure_reason)

    @override_settings(
        GOOGLE_APPS_SCRIPT_WEBHOOK_URL="https://script.google.com/macros/s/test/exec",
        GOOGLE_APPS_SCRIPT_WEBHOOK_SECRET="apps-script-test-secret",
    )
    def test_admin_retry_action_dispatches_a_failed_job(self):
        ticket = self.make_paid_online_ticket(number=85)
        sync = TicketSheetSync.objects.get(ticket=ticket)
        sync.status = TicketSheetSync.Status.FAILED
        sync.failure_reason = "APPS_SCRIPT_SYNC_FAILED (TIMEOUT)"
        sync.failed_at = timezone.now()
        sync.save(
            update_fields=("status", "failure_reason", "failed_at")
        )

        request = RequestFactory().post("/admin/")
        SessionMiddleware(lambda _request: None).process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        request.user = self.admin
        model_admin = admin.site._registry[TicketSheetSync]

        def success_response(_url, *, json, timeout):
            response = Mock()
            response.json.return_value = {
                "success": True,
                "processed_ticket_ids": [
                    record["row"]["ticket_id"] for record in json["tickets"]
                ],
            }
            return response

        with patch(
            "apps.payments.apps_script_sync.requests.post",
            side_effect=success_response,
        ):
            with self.captureOnCommitCallbacks(execute=True):
                model_admin.retry_failed_syncs(
                    request,
                    TicketSheetSync.objects.filter(pk=sync.pk),
                )

        sync.refresh_from_db()
        self.assertEqual(sync.status, TicketSheetSync.Status.SYNCED)

    def test_online_and_on_spot_ticket_sources_route_without_qr_tokens(self):
        online_ticket = self.make_paid_online_ticket()
        _, on_spot_tickets = self.make_registration(
            source=Registration.Source.ON_SPOT,
            email="onsite-sheet@example.test",
            number=2,
        )
        student_ticket = create_college_student_ticket(
            event=self.event,
            student_name="Student Name",
            student_email="student-sheet@example.test",
            created_by=self.admin,
        )

        self.assertEqual(TicketSheetSync.objects.count(), 2)
        self.assertFalse(
            TicketSheetSync.objects.filter(college_ticket=student_ticket).exists()
        )
        pending = self.client.get(
            "/api/internal/sheet-jobs/pending",
            **self.auth_headers(),
        )
        self.assertEqual(pending.status_code, 200, pending.data)
        self.assertEqual(pending.data["count"], 2)

        sheets = {}
        rows = {}
        for job in pending.data["jobs"]:
            data = self.client.get(
                f"/api/internal/sheet-jobs/{job['job_id']}/data",
                {"attempt": job["attempt"]},
                **self.auth_headers(),
            )
            self.assertEqual(data.status_code, 200, data.data)
            self.assertNotIn("token", data.data)
            self.assertNotIn("qr", str(data.data).lower())
            self.assertEqual(data.data["headers"], list(SHEET_HEADERS))
            self.assertEqual(list(data.data["row"]), list(SHEET_HEADERS))
            self.assertEqual(data.data["row"]["payment_status"], "VERIFIED")
            self.assertEqual(data.data["row"]["booking_quantity"], 1)
            self.assertEqual(data.data["row"]["ticket_quantity"], 1)
            self.assertEqual(data.data["row"]["unit_price"], "149.00")
            self.assertEqual(data.data["row"]["amount_due"], "149.00")
            self.assertTrue(data.data["row"]["verified_by"])
            self.assertTrue(data.data["row"]["verified_at"])
            self.assertTrue(data.data["row"]["last_synced_at"])
            sheets[data.data["row"]["ticket_number"]] = data.data["sheet_name"]
            rows[data.data["row"]["ticket_number"]] = data.data["row"]
            self.assertEqual(data.data["attempt"], job["attempt"])

            synced = self.client.post(
                f"/api/internal/sheet-jobs/{job['job_id']}/synced",
                {"attempt": job["attempt"]},
                format="json",
                **self.auth_headers(),
            )
            self.assertEqual(synced.status_code, 200, synced.data)
            self.assertEqual(synced.data["status"], "SYNCED")

        self.assertEqual(
            sheets,
            {
                online_ticket.ticket_code: "Online_Tickets",
                on_spot_tickets[0].ticket_code: "OnSpot_Tickets",
            },
        )
        self.assertEqual(
            TicketSheetSync.objects.filter(status=TicketSheetSync.Status.SYNCED).count(),
            2,
        )

    def test_multi_ticket_booking_data_has_correct_quantity_price_and_total(self):
        ticket = self.make_paid_online_ticket(number=20, quantity=3)
        registration = ticket.registration
        self.assertEqual(registration.quantity, 3)

        sync_data = sheet_sync_data(TicketSheetSync.objects.get(ticket=ticket))

        self.assertEqual(sync_data["row"]["booking_quantity"], 3)
        self.assertEqual(sync_data["row"]["ticket_quantity"], 3)
        self.assertEqual(sync_data["row"]["unit_price"], "149.00")
        self.assertEqual(sync_data["row"]["amount_due"], "447.00")

    def test_legacy_provider_order_and_payment_references_are_synchronized(self):
        ticket = self.make_paid_online_ticket(
            number=21,
            provider=Payment.Provider.PAYU,
            provider_order_id="payu-order-21",
            provider_payment_id="payu-payment-21",
        )

        sync_data = sheet_sync_data(TicketSheetSync.objects.get(ticket=ticket))

        self.assertEqual(sync_data["row"]["provider_order_id"], "payu-order-21")
        self.assertEqual(sync_data["row"]["provider_payment_id"], "payu-payment-21")

    def test_unverified_online_tickets_do_not_queue_sheet_jobs(self):
        registration, tickets = self.make_registration(
            source=Registration.Source.ONLINE,
            email="unverified-sheet@example.test",
            number=3,
        )
        registration.status = Registration.Status.TICKET_ISSUED
        registration.save(update_fields=("status", "updated_at"))
        ensure_ticket_sheet_syncs(registration, tickets)

        self.assertFalse(TicketSheetSync.objects.exists())
        self.assertFalse(TicketDelivery.objects.exists())

    def test_legacy_gateway_ticket_queues_without_human_verifier(self):
        registration, tickets = self.make_registration(
            source=Registration.Source.ONLINE,
            email="payu-sheet@example.test",
            number=5,
        )
        intent = PaymentIntent.objects.create(
            idempotency_key=uuid.uuid4(),
            request_hash="sheet-sync-payu",
            event=self.event,
            ticket_tier=self.tier,
            buyer_name=registration.buyer_name,
            buyer_email=registration.buyer_email,
            buyer_phone=registration.buyer_phone,
            attendee_names=[tickets[0].attendee_name],
            status=PaymentIntent.Status.VERIFIED,
            registration=registration,
        )
        Payment.objects.create(
            intent=intent,
            provider=Payment.Provider.PAYU,
            amount=14900,
            currency="INR",
            status=Payment.Status.CAPTURED,
            verification_status=Payment.VerificationStatus.VERIFIED,
            ticket_issuance_status=Payment.TicketIssuanceStatus.ISSUED,
            verified_at=timezone.now(),
        )

        ensure_ticket_sheet_syncs(registration, tickets)

        sync = TicketSheetSync.objects.get(ticket=tickets[0])
        row = sheet_sync_data(sync)["row"]
        self.assertEqual(row["payment_method"], Payment.Provider.PAYU)
        self.assertEqual(row["verified_by"], "Payment gateway")

    def test_reconciliation_requeues_existing_eligible_rows(self):
        ticket = self.make_paid_online_ticket()
        sync = TicketSheetSync.objects.get(ticket=ticket)
        sync.status = TicketSheetSync.Status.SYNCED
        sync.attempt_count = 4
        sync.save(update_fields=("status", "attempt_count", "updated_at"))

        count = backfill_ticket_sheet_syncs()

        sync.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(sync.status, TicketSheetSync.Status.PENDING)
        self.assertEqual(sync.attempt_count, 0)

    def test_unauthenticated_user_cannot_claim_or_update_sheet_jobs(self):
        create_college_student_ticket(
            event=self.event,
            student_name="Student",
            student_email="student-auth@example.test",
        )

        response = self.client.get("/api/internal/sheet-jobs/pending")
        claim_response = self.client.post(
            "/api/internal/email-jobs/claim-from-sheet",
            {"ticket_id": str(uuid.uuid4())},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(claim_response.status_code, 401)

    def test_sheet_email_claim_is_disabled_and_does_not_modify_ticket_or_sync(self):
        ticket = self.make_paid_online_ticket()
        delivery_count = TicketDelivery.objects.count()
        sync = TicketSheetSync.objects.get(ticket=ticket)
        sync.status = TicketSheetSync.Status.SYNCED
        sync.synced_at = timezone.now()
        sync.save(update_fields=("status", "synced_at"))
        headers = self.auth_headers()
        claim = self.client.post(
            "/api/internal/email-jobs/claim-from-sheet",
            {"ticket_id": str(ticket.id)},
            format="json",
            **headers,
        )

        self.assertEqual(claim.status_code, 200, claim.data)
        self.assertFalse(claim.data["claimed"])
        self.assertEqual(claim.data["reason"], "Email delivery is disabled.")
        self.assertEqual(TicketDelivery.objects.count(), delivery_count)

        duplicate = self.client.post(
            "/api/internal/email-jobs/claim-from-sheet",
            {"ticket_id": str(ticket.id)},
            format="json",
            **headers,
        )

        self.assertEqual(duplicate.status_code, 200, duplicate.data)
        self.assertFalse(duplicate.data["claimed"])
        sync.refresh_from_db()
        self.assertEqual(sync.status, TicketSheetSync.Status.SYNCED)
        self.assertEqual(TicketDelivery.objects.count(), delivery_count)

    def test_sheet_email_claim_rejects_unpaid_or_unknown_ticket(self):
        _, tickets = self.make_registration(
            source=Registration.Source.ONLINE,
            email="unpaid-claim@example.test",
            number=6,
        )
        unpaid_claim = self.client.post(
            "/api/internal/email-jobs/claim-from-sheet",
            {"ticket_id": str(tickets[0].id)},
            format="json",
            **self.auth_headers(),
        )
        unknown_claim = self.client.post(
            "/api/internal/email-jobs/claim-from-sheet",
            {"ticket_id": str(uuid.uuid4())},
            format="json",
            **self.auth_headers(),
        )

        self.assertEqual(unpaid_claim.status_code, 200, unpaid_claim.data)
        self.assertFalse(unpaid_claim.data["claimed"])
        self.assertEqual(unknown_claim.status_code, 200, unknown_claim.data)
        self.assertFalse(unknown_claim.data["claimed"])

    def test_failed_sheet_sync_uses_bounded_backoff_and_safe_retry(self):
        _, tickets = self.make_registration(
            source=Registration.Source.ON_SPOT,
            email="retry-sheet@example.test",
            number=4,
        )
        sync = TicketSheetSync.objects.get(ticket=tickets[0])
        claimed = self.client.get(
            "/api/internal/sheet-jobs/pending",
            **self.auth_headers(),
        )
        job = claimed.data["jobs"][0]
        failed = self.client.post(
            f"/api/internal/sheet-jobs/{job['job_id']}/failed",
            {"attempt": job["attempt"], "error_code": "SHEETS_UPSERT_FAILED"},
            format="json",
            **self.auth_headers(),
        )

        self.assertEqual(failed.status_code, 200, failed.data)
        sync.refresh_from_db()
        self.assertEqual(sync.status, TicketSheetSync.Status.PENDING)
        self.assertGreater(sync.retry_after, timezone.now())
        self.assertEqual(
            self.client.get(
                "/api/internal/sheet-jobs/pending",
                **self.auth_headers(),
            ).data["count"],
            0,
        )

        sync.retry_after = timezone.now() - timedelta(seconds=1)
        sync.save(update_fields=("retry_after",))
        retried = self.client.get(
            "/api/internal/sheet-jobs/pending",
            **self.auth_headers(),
        )
        self.assertEqual(retried.data["jobs"][0]["attempt"], 2)

    def test_worker_retries_temporary_google_sheets_timeout(self):
        ticket = self.make_paid_online_ticket(number=25)
        sync = TicketSheetSync.objects.get(ticket=ticket)
        sheets_client = Mock()
        sheets_client.upsert_ticket_row.side_effect = requests.Timeout(
            "simulated response timeout"
        )

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

        sync.refresh_from_db()
        self.assertEqual(sync.status, TicketSheetSync.Status.PENDING)
        self.assertEqual(sync.attempt_count, 1)
        self.assertGreater(sync.retry_after, timezone.now())

        sync.retry_after = timezone.now() - timedelta(seconds=1)
        sync.save(update_fields=("retry_after",))
        sheets_client.upsert_ticket_row.side_effect = None

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

        sync.refresh_from_db()
        self.assertEqual(sync.status, TicketSheetSync.Status.SYNCED)
        self.assertEqual(sync.attempt_count, 0)
        self.assertEqual(sheets_client.upsert_ticket_row.call_count, 2)

    def test_worker_recovers_queued_job_after_previous_worker_lease_expires(self):
        ticket = self.make_paid_online_ticket(number=26)
        sync = TicketSheetSync.objects.get(ticket=ticket)
        sync.status = TicketSheetSync.Status.PROCESSING
        sync.attempt_count = 1
        sync.lease_expires_at = timezone.now() - timedelta(seconds=1)
        sync.save(
            update_fields=("status", "attempt_count", "lease_expires_at")
        )
        sheets_client = Mock()

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

        sync.refresh_from_db()
        self.assertEqual(sync.status, TicketSheetSync.Status.SYNCED)
        self.assertEqual(sync.attempt_count, 0)
        sheets_client.upsert_ticket_row.assert_called_once()

    def test_check_in_updates_the_existing_ticket_row(self):
        _, tickets = self.make_registration(
            source=Registration.Source.ON_SPOT,
            email="checked-in-sheet@example.test",
            number=7,
        )
        ticket = tickets[0]
        sync = TicketSheetSync.objects.get(ticket=ticket)
        sync.status = TicketSheetSync.Status.SYNCED
        sync.synced_at = timezone.now()
        sync.save(update_fields=("status", "synced_at"))

        scan_ticket(token=ticket.token, scanner=self.admin)

        sync.refresh_from_db()
        self.assertEqual(sync.status, TicketSheetSync.Status.PENDING)
        pending = self.client.get(
            "/api/internal/sheet-jobs/pending",
            **self.auth_headers(),
        )
        job = pending.data["jobs"][0]
        data = self.client.get(
            f"/api/internal/sheet-jobs/{job['job_id']}/data",
            {"attempt": job["attempt"]},
            **self.auth_headers(),
        )

        self.assertEqual(data.data["row"]["ticket_status"], "USED")
        self.assertEqual(data.data["row"]["scan_status"], "CHECKED_IN")
        self.assertTrue(data.data["row"]["checked_in_at"])
        self.assertEqual(data.data["row"]["checked_in_by"], "Sheet Admin")
        self.assertEqual(
            TicketScan.objects.filter(ticket=ticket, result="ENTRY_GRANTED").count(),
            1,
        )

    def test_cancellation_updates_the_existing_ticket_row(self):
        _, tickets = self.make_registration(
            source=Registration.Source.ON_SPOT,
            email="cancelled-sheet@example.test",
            number=8,
        )
        ticket = tickets[0]
        sync = TicketSheetSync.objects.get(ticket=ticket)
        sync.status = TicketSheetSync.Status.SYNCED
        sync.synced_at = timezone.now()
        sync.save(update_fields=("status", "synced_at"))

        cancel_ticket(ticket.id, self.admin)

        sync.refresh_from_db()
        self.assertEqual(sync.status, TicketSheetSync.Status.PENDING)
        pending = self.client.get(
            "/api/internal/sheet-jobs/pending",
            **self.auth_headers(),
        )
        job = pending.data["jobs"][0]
        data = self.client.get(
            f"/api/internal/sheet-jobs/{job['job_id']}/data",
            {"attempt": job["attempt"]},
            **self.auth_headers(),
        )
        self.assertEqual(data.data["row"]["ticket_status"], "CANCELLED")
        self.assertEqual(data.data["row"]["scan_status"], "NOT_CHECKED_IN")

    def test_backfill_requeues_used_and_cancelled_tickets_without_sync_rows(self):
        used_ticket = self.make_paid_online_ticket(number=30)
        cancelled_ticket = self.make_paid_online_ticket(number=31)
        scan_ticket(token=used_ticket.token, scanner=self.admin)
        cancel_ticket(cancelled_ticket.id, self.admin)
        TicketSheetSync.objects.filter(
            ticket__in=(used_ticket, cancelled_ticket)
        ).delete()

        queued_count = backfill_ticket_sheet_syncs()

        self.assertEqual(queued_count, 2)
        self.assertEqual(
            set(
                TicketSheetSync.objects.filter(
                    ticket__in=(used_ticket, cancelled_ticket),
                    status=TicketSheetSync.Status.PENDING,
                ).values_list("ticket_id", flat=True)
            ),
            {used_ticket.id, cancelled_ticket.id},
        )

    def test_disabled_email_compatibility_routes_do_not_change_sheet_sync(self):
        ticket = self.make_paid_online_ticket()
        sync = TicketSheetSync.objects.get(ticket=ticket)
        sync.status = TicketSheetSync.Status.SYNCED
        sync.synced_at = timezone.now()
        sync.save(update_fields=("status", "synced_at"))
        claim = self.client.get(
            "/api/internal/email-jobs/pending",
            **self.auth_headers(),
        )
        self.assertEqual(claim.status_code, 200, claim.data)
        self.assertEqual(claim.data, {"count": 0, "jobs": []})
        sync.refresh_from_db()
        self.assertEqual(sync.status, TicketSheetSync.Status.SYNCED)
        self.assertFalse(TicketDelivery.objects.exists())

        claim = self.client.post(
            "/api/internal/email-jobs/claim-from-sheet",
            {"ticket_id": str(ticket.pk)},
            format="json",
            **self.auth_headers(),
        )
        self.assertEqual(claim.status_code, 200, claim.data)
        self.assertFalse(claim.data["claimed"])
        sync.refresh_from_db()
        self.assertEqual(sync.status, TicketSheetSync.Status.SYNCED)

    def test_sheet_failure_becomes_terminal_after_fifth_attempt(self):
        _, tickets = self.make_registration(
            source=Registration.Source.ON_SPOT,
            email="terminal-sheet@example.test",
            number=5,
        )
        sync = TicketSheetSync.objects.get(ticket=tickets[0])
        sync.status = TicketSheetSync.Status.PROCESSING
        sync.attempt_count = 5
        sync.lease_expires_at = timezone.now() + timedelta(minutes=5)
        sync.save(
            update_fields=("status", "attempt_count", "lease_expires_at")
        )

        response = self.client.post(
            f"/api/internal/sheet-jobs/{sync.id}/failed",
            {"attempt": 5, "error_code": "SHEETS_REJECTED"},
            format="json",
            **self.auth_headers(),
        )

        self.assertEqual(response.status_code, 200, response.data)
        sync.refresh_from_db()
        self.assertEqual(sync.status, TicketSheetSync.Status.FAILED)
        self.assertIsNotNone(sync.failed_at)
