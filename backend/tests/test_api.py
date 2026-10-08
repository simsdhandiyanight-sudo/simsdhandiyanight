import base64
import hashlib
import hmac
import os
import uuid
from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
import requests
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.events.models import Event, TicketTier
from apps.payments.delivery import process_next_ticket_email
from apps.payments.models import EmailDailyUsage, Payment, PaymentIntent, TicketDelivery
from apps.registrations.models import Registration
from apps.scanning.models import Gate, StaffAssignment, TicketScan
from apps.registrations.services import RegistrationConflict, create_registration
from apps.tickets.models import Ticket
from razorpay.errors import BadRequestError
from tests.payment_fakes import FakeRazorpayClient


class FakeBrevoResponse:
    def __init__(self, message_id, status_code=201):
        self.status_code = status_code
        self.json = Mock(return_value={"messageId": message_id})


class CanonicalEventSeedTests(TestCase):
    def test_seed_command_is_safe_to_run_repeatedly(self):
        call_command("seed_dhandiya_event")
        call_command("seed_dhandiya_event")

        event = Event.objects.get(slug="dhandiya-night-2026")
        self.assertEqual(Event.objects.filter(slug="dhandiya-night-2026").count(), 1)
        self.assertEqual(
            set(event.tiers.filter(is_available=True).values_list("slug", flat=True)),
            {"single-ticket", "combo-buy-5-get-1"},
        )
        combo = event.tiers.get(slug="combo-buy-5-get-1")
        self.assertEqual(combo.name, "Combo Offer — Buy 5, Get 1 Free")
        self.assertEqual(str(combo.price), "745.00")
        self.assertEqual(combo.admission_count, 6)
        self.assertIn(
            "1 welcome drink and 1 set of Dhandiya sticks per ticket",
            combo.perks,
        )
        single = event.tiers.get(slug="single-ticket")
        self.assertIn(
            "1 welcome drink and 1 set of Dhandiya sticks per ticket",
            single.perks,
        )
        response = APIClient().get("/api/v1/events/dhandiya-night-2026/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {tier["name"] for tier in response.data["tiers"]},
            {"Single Ticket", "Combo Offer — Buy 5, Get 1 Free"},
        )

    def test_seed_retires_legacy_combo_and_creates_new_tier(self):
        event = Event.objects.create(
            id="8b3f7a20-6e8d-4b91-a462-9c5d2f1e7043",
            slug="dhandiya-night-2026",
            name="Dhandiya Night 2026",
            start_at=timezone.now() + timedelta(days=1),
            end_at=timezone.now() + timedelta(days=1, hours=3),
            venue="Soundarya College Campus",
            city="Bengaluru",
            address="Test address",
            status=Event.Status.OPEN,
            registration_open=True,
            capacity=2500,
        )
        old_combo = TicketTier.objects.create(
            event=event,
            slug="combo-buy-3-get-1",
            name="Combo Offer — Buy 3, Get 1 Free",
            price="447.00",
            admission_count=4,
        )

        call_command("seed_dhandiya_event")

        old_combo.refresh_from_db()
        new_combo = event.tiers.get(slug="combo-buy-5-get-1")
        self.assertEqual(old_combo.slug, "combo-buy-3-get-1")
        self.assertEqual(old_combo.name, "Combo Offer — Buy 3, Get 1 Free")
        self.assertEqual(str(old_combo.price), "447.00")
        self.assertEqual(old_combo.admission_count, 4)
        self.assertFalse(old_combo.is_available)
        self.assertEqual(new_combo.name, "Combo Offer — Buy 5, Get 1 Free")
        self.assertEqual(str(new_combo.price), "745.00")
        self.assertEqual(new_combo.admission_count, 6)
        self.assertEqual(event.tiers.count(), 3)


class AdminBootstrapTests(TestCase):
    def test_bootstrap_creates_admin_and_does_not_reset_existing_password(self):
        user_model = get_user_model()
        with patch.dict(
            os.environ,
            {
                "BOOTSTRAP_ADMIN_EMAIL": "admin@sims.in",
                "BOOTSTRAP_ADMIN_PASSWORD": "Bootstrap-test-password-1!",
            },
        ):
            call_command("bootstrap_admin")
            admin = user_model.objects.get(email="admin@sims.in")
            self.assertTrue(admin.is_superuser)
            self.assertTrue(admin.is_staff)
            self.assertEqual(admin.role, user_model.Role.ADMIN)
            self.assertTrue(admin.check_password("Bootstrap-test-password-1!"))

            admin.set_password("Rotated-test-password-2!")
            admin.save(update_fields=["password"])
            call_command("bootstrap_admin")

        admin.refresh_from_db()
        self.assertTrue(admin.check_password("Rotated-test-password-2!"))

    def test_bootstrap_resets_existing_admin_password_only_when_explicitly_enabled(self):
        user_model = get_user_model()
        admin = user_model.objects.create_superuser(
            email="admin@sims.in",
            password="Old-test-password-1!",
            name="SIMS Admin",
        )
        with patch.dict(
            os.environ,
            {
                "BOOTSTRAP_ADMIN_EMAIL": "admin@sims.in",
                "BOOTSTRAP_ADMIN_PASSWORD": "New-test-password-2!",
                "BOOTSTRAP_ADMIN_RESET_PASSWORD": "true",
            },
        ):
            call_command("bootstrap_admin")

        admin.refresh_from_db()
        self.assertTrue(admin.check_password("New-test-password-2!"))
        self.assertFalse(admin.check_password("Old-test-password-1!"))

    def test_bootstrap_skips_when_no_credentials_are_configured(self):
        with patch.dict(
            os.environ, {"BOOTSTRAP_ADMIN_EMAIL": "admin@sims.in"}, clear=True
        ):
            call_command("bootstrap_admin")

        self.assertFalse(get_user_model().objects.exists())


@override_settings(
    RAZORPAY_KEY_ID="rzp_test_id",
    RAZORPAY_KEY_SECRET="test_secret",
    BREVO_API_KEY="brevo-test-key",
    BREVO_SENDER_EMAIL="tickets@example.test",
)
class TicketingApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        start = timezone.now() + timedelta(days=2)
        self.event = Event.objects.create(
            slug="test-event",
            name="Test Event",
            start_at=start,
            end_at=start + timedelta(hours=3),
            venue="Test Venue",
            city="Bengaluru",
            address="Test address",
            status=Event.Status.OPEN,
            registration_open=True,
            capacity=8,
        )
        self.single = TicketTier.objects.create(
            event=self.event,
            slug="single",
            name="Single Ticket",
            price="149.00",
            admission_count=1,
        )
        self.combo = TicketTier.objects.create(
            event=self.event,
            slug="combo",
            name="Combo",
            price="447.00",
            admission_count=4,
        )
        self.admin = get_user_model().objects.create_user(
            "admin@example.test", "Secure-test-pass-123!", name="Admin", role="ADMIN"
        )
        self.registration_staff = get_user_model().objects.create_user(
            "registration@example.test",
            "Secure-test-pass-123!",
            name="Registration Staff",
            role="REGISTRATION_STAFF",
        )
        self.scanner = get_user_model().objects.create_user(
            "scanner@example.test",
            "Secure-test-pass-123!",
            name="Scanner Staff",
            role="SCANNER_STAFF",
        )
        self.gate = Gate.objects.create(event=self.event, name="Gate 1")
        StaffAssignment.objects.create(user=self.scanner, gate=self.gate)

    def registration_payload(self, tier=None, **overrides):
        payload = {
            "event_id": str(self.event.id),
            "ticket_tier_id": str((tier or self.single).id),
            "buyer": {
                "name": "Test Buyer",
                "email": "buyer@example.test",
                "phone": "+919876543210",
                "organization": "",
                "job_title": "",
            },
            "source": "ON_SPOT",
        }
        payload.update(overrides)
        return payload

    def test_six_admission_combo_registration_creates_six_tickets(self):
        combo = TicketTier.objects.create(
            event=self.event,
            slug="combo-six",
            name="Combo Offer — Buy 5, Get 1 Free",
            price="745.00",
            admission_count=6,
        )
        names = [f"Attendee {index}" for index in range(1, 7)]

        registration, tickets = create_registration(
            event_id=self.event.id,
            tier_id=combo.id,
            buyer={
                "name": names[0],
                "email": "combo@example.test",
                "phone": "+919876543210",
            },
            attendee_names=names,
            source=Registration.Source.ON_SPOT,
            created_by=self.registration_staff,
        )

        self.assertEqual(registration.ticket_tier.admission_count, 6)
        self.assertEqual([ticket.attendee_name for ticket in tickets], names)

    def test_retired_tier_is_unavailable_for_new_orders_but_existing_payment_can_finish(self):
        retired_combo = TicketTier.objects.create(
            event=self.event,
            slug="combo-retired",
            name="Retired combo",
            price="447.00",
            admission_count=4,
            is_available=False,
        )
        buyer = {
            "name": "Attendee One",
            "email": "combo@example.test",
            "phone": "+919876543210",
        }
        names = ["Attendee One", "Attendee Two", "Attendee Three", "Attendee Four"]

        with self.assertRaises(RegistrationConflict):
            create_registration(
                event_id=self.event.id,
                tier_id=retired_combo.id,
                buyer=buyer,
                attendee_names=names,
                source=Registration.Source.ON_SPOT,
            )

        _, tickets = create_registration(
            event_id=self.event.id,
            tier_id=retired_combo.id,
            buyer=buyer,
            attendee_names=names,
            source=Registration.Source.ON_SPOT,
            exclude_payment_intent_id=uuid.uuid4(),
        )
        self.assertEqual(len(tickets), 4)

    def payment_order(self, payload, key, provider):
        return self.client.post(
            "/api/v1/payments/create-order/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(key),
        )

    def verify_order(self, order_id, provider):
        payment_id = f"pay_{order_id.removeprefix('order_')}"
        signature = hmac.new(
            b"test_secret",
            f"{order_id}|{payment_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return self.client.post(
            "/api/v1/payments/verify/",
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            },
            format="json",
        )

    def create_online_registration(self, tier=None, buyer=None):
        payload = self.registration_payload(tier)
        if tier == self.combo:
            payload["attendee_names"] = [
                "Attendee One",
                "Attendee Two",
                "Attendee Three",
                "Attendee Four",
            ]
        if buyer:
            payload["buyer"].update(buyer)
        provider = FakeRazorpayClient()
        with patch("apps.payments.services.razorpay.Client", return_value=provider):
            order = self.payment_order(payload, uuid.uuid4(), provider)
            if order.status_code >= 400 or order.data.get("payment_verified"):
                return order
            return self.verify_order(order.data["order_id"], provider)

    def test_public_event_uses_canonical_backend_identity_and_live_capacity(self):
        canonical = Event.objects.create(
            id="8b3f7a20-6e8d-4b91-a462-9c5d2f1e7043",
            slug="dhandiya-night-2026",
            name="Dhandiya Night 2026",
            start_at=self.event.start_at,
            end_at=self.event.end_at,
            venue="Soundarya College Campus",
            city="Bengaluru",
            address="Sidedahalli",
            status=Event.Status.OPEN,
            registration_open=True,
            capacity=2500,
        )
        TicketTier.objects.create(
            event=canonical,
            slug="combo",
            name="Combo",
            price="447.00",
            admission_count=4,
        )
        response = self.client.get("/api/v1/events/dhandiya-night-2026/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], "8b3f7a20-6e8d-4b91-a462-9c5d2f1e7043")
        self.assertEqual(response.data["registeredCount"], 0)
        self.assertEqual(response.data["tiers"][0]["admissionCount"], 4)

    def test_admin_event_context_avoids_public_ticket_aggregates(self):
        self.client.force_authenticate(user=self.admin)

        with self.assertNumQueries(2):
            response = self.client.get(
                f"/api/v1/events/admin-context/{self.event.slug}/"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], str(self.event.id))
        self.assertEqual(response.data["capacity"], self.event.capacity)
        self.assertEqual(
            {tier["id"] for tier in response.data["tiers"]},
            {str(self.single.id), str(self.combo.id)},
        )

    def test_admin_event_context_requires_admin_access(self):
        response = self.client.get(
            f"/api/v1/events/admin-context/{self.event.slug}/"
        )

        self.assertEqual(response.status_code, 401)

    def test_online_combo_creates_four_independently_scannable_tickets(self):
        response = self.create_online_registration(self.combo)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["tickets"]), 4)
        self.assertEqual(response.data["registration"]["source"], Registration.Source.ONLINE)
        self.assertEqual(
            len({ticket["qr_token"] for ticket in response.data["tickets"]}),
            4,
        )
        self.assertEqual(
            [ticket["attendee_name"] for ticket in response.data["tickets"]],
            ["Attendee One", "Attendee Two", "Attendee Three", "Attendee Four"],
        )
        self.assertEqual(Ticket.objects.filter(registration_id=response.data["registration"]["id"]).count(), 4)
        self.assertEqual(self.event.registrations.count(), 1)
        self.assertEqual(AuditLog.objects.filter(action="REGISTRATION_CREATED").count(), 1)
        self.assertEqual(TicketDelivery.objects.count(), 4)
        self.assertEqual(
            set(TicketDelivery.objects.values_list("status", flat=True)),
            {TicketDelivery.Status.PENDING},
        )
        with patch(
            "apps.payments.delivery.requests.post",
            side_effect=[
                FakeBrevoResponse("message-1"),
                FakeBrevoResponse("message-2"),
                FakeBrevoResponse("message-3"),
                FakeBrevoResponse("message-4"),
            ],
        ) as send_email:
            for _ in range(4):
                self.assertEqual(
                    process_next_ticket_email(),
                    TicketDelivery.Status.SENT,
                )
        self.assertEqual(send_email.call_count, 4)
        self.assertEqual(TicketDelivery.objects.filter(status=TicketDelivery.Status.SENT).count(), 4)
        self.assertEqual(
            set(TicketDelivery.objects.values_list("provider_message_id", flat=True)),
            {"message-1", "message-2", "message-3", "message-4"},
        )
        sent_payloads = [
            call.kwargs["json"] for call in send_email.call_args_list
        ]
        self.assertEqual(
            {payload["to"][0]["name"] for payload in sent_payloads},
            {"Attendee One", "Attendee Two", "Attendee Three", "Attendee Four"},
        )
        for payload in sent_payloads:
            pdf_bytes = base64.b64decode(payload["attachment"][0]["content"])
            self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
            self.assertIn(payload["to"][0]["name"], payload["htmlContent"])

    def test_combo_requires_a_name_for_each_ticket(self):
        payload = self.registration_payload(self.combo)
        provider = FakeRazorpayClient()
        with patch("apps.payments.services.razorpay.Client", return_value=provider):
            response = self.payment_order(payload, uuid.uuid4(), provider)
        self.assertEqual(response.status_code, 400)
        self.assertIn("attendee_names", response.data["error"]["details"])
        self.assertEqual(Registration.objects.count(), 0)

        payload["attendee_names"] = ["One", "Two", "Three"]
        with patch("apps.payments.services.razorpay.Client", return_value=provider):
            response = self.payment_order(payload, uuid.uuid4(), provider)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Registration.objects.count(), 0)

    def test_client_cannot_choose_registration_source(self):
        response = self.create_online_registration()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["registration"]["source"], Registration.Source.ONLINE)

    def test_public_registration_endpoint_cannot_issue_unpaid_tickets(self):
        response = self.client.post(
            "/api/v1/registrations/",
            self.registration_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, 402)
        self.assertEqual(response.data["error"]["code"], "PAYMENT_REQUIRED")
        self.assertEqual(Registration.objects.count(), 0)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_payment_order_retry_and_verification_issue_once(self):
        key = str(uuid.uuid4())
        payload = self.registration_payload(
            self.combo,
            attendee_names=[
                "Attendee One",
                "Attendee Two",
                "Attendee Three",
                "Attendee Four",
            ],
        )
        provider = FakeRazorpayClient()
        with patch("apps.payments.services.razorpay.Client", return_value=provider):
            first_order = self.payment_order(payload, key, provider)
            repeated_order = self.payment_order(payload, key, provider)
            self.assertEqual(first_order.status_code, 201, first_order.data)
            self.assertEqual(repeated_order.status_code, 200, repeated_order.data)
            self.assertEqual(first_order.data["order_id"], repeated_order.data["order_id"])
            self.assertNotIn("expire_by", provider.last_order_payload)
            self.assertEqual(Registration.objects.count(), 0)
            self.assertEqual(Ticket.objects.count(), 0)
            first = self.verify_order(first_order.data["order_id"], provider)
            replay = self.verify_order(first_order.data["order_id"], provider)

        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(first.data["registration"]["id"], replay.data["registration"]["id"])
        self.assertEqual(
            [ticket["id"] for ticket in first.data["tickets"]],
            [ticket["id"] for ticket in replay.data["tickets"]],
        )
        self.assertEqual(
            [ticket["qr_token"] for ticket in first.data["tickets"]],
            [ticket["qr_token"] for ticket in replay.data["tickets"]],
        )
        self.assertEqual(Registration.objects.count(), 1)
        self.assertEqual(Ticket.objects.count(), 4)
        self.assertEqual(
            len({ticket["qr_token"] for ticket in replay.data["tickets"]}),
            4,
        )
        self.assertEqual(PaymentIntent.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(AuditLog.objects.filter(action="REGISTRATION_CREATED").count(), 1)
        self.assertEqual(TicketDelivery.objects.count(), 4)
        self.assertEqual(
            TicketDelivery.objects.filter(status=TicketDelivery.Status.PENDING).count(),
            4,
        )

    def test_idempotency_key_cannot_be_reused_for_different_request(self):
        key = str(uuid.uuid4())
        provider = FakeRazorpayClient()
        changed_payload = self.registration_payload(
            buyer={
                "name": "Different Buyer",
                "email": "different@example.test",
                "phone": "+919876543210",
            }
        )
        with patch("apps.payments.services.razorpay.Client", return_value=provider):
            first = self.payment_order(self.registration_payload(), key, provider)
            conflict = self.payment_order(changed_payload, key, provider)
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data["error"]["code"], "IDEMPOTENCY_CONFLICT")
        self.assertEqual(Registration.objects.count(), 0)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_different_idempotency_keys_create_distinct_registrations(self):
        first = self.create_online_registration()
        second = self.create_online_registration(
            buyer={
                "name": "Another Buyer",
                "email": "another@example.test",
                "phone": "+919876543210",
            }
        )
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertNotEqual(
            first.data["registration"]["id"],
            second.data["registration"]["id"],
        )
        self.assertEqual(Registration.objects.count(), 2)
        self.assertEqual(Ticket.objects.count(), 2)

    def test_ticket_insert_failure_preserves_capture_and_requires_admin_review(self):
        key = str(uuid.uuid4())
        payload = self.registration_payload()
        provider = FakeRazorpayClient()
        with patch("apps.payments.services.razorpay.Client", return_value=provider):
            order = self.payment_order(payload, key, provider)
            self.assertEqual(order.status_code, 201, order.data)
            with patch(
                "apps.registrations.services.Ticket.objects.bulk_create",
                side_effect=RuntimeError("simulated ticket insert failure"),
            ) as ticket_insert:
                failed = self.verify_order(order.data["order_id"], provider)
                self.assertEqual(failed.status_code, 409, failed.data)
                self.assertEqual(
                    failed.data["error"]["code"],
                    "PAYMENT_REVIEW_REQUIRED",
                )
                retry = self.verify_order(order.data["order_id"], provider)
                self.assertEqual(retry.status_code, 409, retry.data)
                self.assertEqual(
                    retry.data["error"]["code"],
                    "PAYMENT_REVIEW_REQUIRED",
                )
                self.assertEqual(ticket_insert.call_count, 1)
            self.assertEqual(Registration.objects.count(), 0)
            self.assertEqual(Ticket.objects.count(), 0)
        payment = Payment.objects.get()
        payment_intent = PaymentIntent.objects.get()
        self.assertEqual(payment.status, Payment.Status.CAPTURED)
        self.assertIsNotNone(payment.captured_at)
        self.assertEqual(
            payment.verification_status,
            Payment.VerificationStatus.VERIFIED,
        )
        self.assertEqual(
            payment.ticket_issuance_status,
            Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED,
        )
        self.assertIn("simulated ticket insert failure", payment.ticket_issuance_failure)
        self.assertEqual(payment_intent.status, PaymentIntent.Status.REVIEW_REQUIRED)
        review_log = AuditLog.objects.get(action="PAYMENT_REVIEW_REQUIRED")
        self.assertEqual(review_log.resource_id, str(payment.id))
        self.assertEqual(
            review_log.metadata["razorpay_payment_id"],
            payment.razorpay_payment_id,
        )
        self.client.force_authenticate(self.admin)
        dashboard = self.client.get("/api/v1/payments/review/dashboard/")
        self.assertEqual(dashboard.status_code, 200, dashboard.data)
        self.assertEqual(
            dashboard.data["issue_counts"]["PAYMENT_CAPTURED_WITHOUT_TICKET"],
            1,
        )
        self.assertEqual(
            dashboard.data["issue_counts"]["TICKET_ISSUANCE_FAILED"],
            1,
        )
        self.assertEqual(len(dashboard.data["payments"]), 1)

    def test_payment_review_dashboard_reports_online_tickets_without_payment(self):
        registration, tickets = create_registration(
            event_id=self.event.id,
            tier_id=self.single.id,
            buyer=self.registration_payload()["buyer"],
            source=Registration.Source.ONLINE,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/v1/payments/review/dashboard/")
        self.assertEqual(response.status_code, 200, response.data)
        cases = response.data["registrations_without_valid_payment"]
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["registration_id"], str(registration.id))
        self.assertEqual(response.data["issue_counts"]["TICKET_WITHOUT_VALID_PAYMENT"], 1)
        self.assertEqual(len(tickets), 1)

    def test_payment_review_dashboard_reports_duplicate_captured_payments(self):
        response = self.create_online_registration()
        self.assertEqual(response.status_code, 200, response.data)
        original = Payment.objects.get()
        Payment.objects.create(
            intent=original.intent,
            amount=original.amount,
            currency=original.currency,
            status=Payment.Status.CAPTURED,
            verification_status=Payment.VerificationStatus.FAILED,
            ticket_issuance_status=Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED,
            ticket_issuance_failure="Duplicate captured payment detected.",
            expires_at=original.expires_at,
            captured_at=timezone.now(),
        )
        self.client.force_authenticate(self.admin)
        dashboard = self.client.get("/api/v1/payments/review/dashboard/")
        self.assertEqual(dashboard.status_code, 200, dashboard.data)
        self.assertEqual(dashboard.data["issue_counts"]["DUPLICATE_PAYMENT"], 2)
        self.assertEqual(len(dashboard.data["payments"]), 2)

    def test_payment_review_dashboard_is_admin_only(self):
        self.client.force_authenticate(self.scanner)
        response = self.client.get("/api/v1/payments/review/dashboard/")
        self.assertEqual(response.status_code, 403, response.data)

    def test_successful_payment_records_ticket_issuance_as_complete(self):
        response = self.create_online_registration()
        self.assertEqual(response.status_code, 200, response.data)
        payment = Payment.objects.get()
        self.assertEqual(
            payment.ticket_issuance_status,
            Payment.TicketIssuanceStatus.ISSUED,
        )
        self.assertEqual(PaymentIntent.objects.count(), 1)

    def test_retry_recovers_matching_incomplete_payment_intent(self):
        key = uuid.uuid4()
        payload = self.registration_payload()
        request_hash = __import__(
            "apps.payments.services",
            fromlist=["payment_request_hash"],
        ).payment_request_hash(
            event_id=self.event.id,
            tier_id=self.single.id,
            buyer=payload["buyer"],
            attendee_names=[payload["buyer"]["name"]],
        )
        intent = PaymentIntent.objects.create(
            idempotency_key=key,
            request_hash=request_hash,
            event=self.event,
            ticket_tier=self.single,
            buyer_name=payload["buyer"]["name"],
            buyer_email=payload["buyer"]["email"],
            buyer_phone=payload["buyer"]["phone"],
            attendee_names=[payload["buyer"]["name"]],
            expires_at=timezone.now(),
        )
        provider = FakeRazorpayClient()
        with patch("apps.payments.services.razorpay.Client", return_value=provider):
            order = self.payment_order(payload, key, provider)
            self.assertEqual(order.status_code, 201, order.data)
            verified = self.verify_order(order.data["order_id"], provider)
        self.assertEqual(verified.status_code, 200, verified.data)
        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntent.Status.VERIFIED)
        self.assertEqual(Registration.objects.count(), 1)
        self.assertEqual(Ticket.objects.count(), 1)

    def test_repeated_payment_verification_and_registration_create_one_ticket_set(self):
        payload = self.registration_payload()
        key = uuid.uuid4()
        provider = FakeRazorpayClient()
        with patch("apps.payments.services.razorpay.Client", return_value=provider):
            order = self.payment_order(payload, key, provider)
            first_verification = self.verify_order(order.data["order_id"], provider)
            repeated_verification = self.verify_order(order.data["order_id"], provider)
        self.assertEqual(first_verification.status_code, 200, first_verification.data)
        self.assertEqual(repeated_verification.status_code, 200, repeated_verification.data)
        self.assertTrue(first_verification.data["payment_verified"])
        self.assertTrue(repeated_verification.data["payment_verified"])
        self.assertEqual(Registration.objects.count(), 1)
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(TicketDelivery.objects.count(), 1)
        self.assertEqual(
            TicketDelivery.objects.get().status,
            TicketDelivery.Status.PENDING,
        )

    def test_invalid_payment_signature_does_not_issue_tickets(self):
        provider = FakeRazorpayClient()
        with patch("apps.payments.services.razorpay.Client", return_value=provider):
            order = self.payment_order(self.registration_payload(), uuid.uuid4(), provider)
            response = self.client.post(
                "/api/v1/payments/verify/",
                {
                    "razorpay_order_id": order.data["order_id"],
                    "razorpay_payment_id": "pay_invalid",
                    "razorpay_signature": "0" * 64,
                },
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Payment.objects.get().verification_status, Payment.VerificationStatus.FAILED)
        self.assertEqual(Registration.objects.count(), 0)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_unknown_order_and_wrong_payment_id_are_rejected(self):
        response = self.client.post(
            "/api/v1/payments/verify/",
            {
                "razorpay_order_id": "order_not_found",
                "razorpay_payment_id": "pay_not_found",
                "razorpay_signature": "0" * 64,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 404)

        provider = FakeRazorpayClient()
        with patch("apps.payments.services.razorpay.Client", return_value=provider):
            order = self.payment_order(self.registration_payload(), uuid.uuid4(), provider)
            signature = hmac.new(
                b"test_secret",
                f"{order.data['order_id']}|pay_wrong".encode(),
                hashlib.sha256,
            ).hexdigest()
            with patch.object(
                provider.payment,
                "fetch",
                side_effect=BadRequestError("payment not found"),
            ):
                invalid = self.client.post(
                    "/api/v1/payments/verify/",
                    {
                        "razorpay_order_id": order.data["order_id"],
                        "razorpay_payment_id": "pay_wrong",
                        "razorpay_signature": signature,
                    },
                    format="json",
                )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(Registration.objects.count(), 0)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_captured_payment_mismatch_is_preserved_for_admin_review(self):
        for index, override in enumerate(({"amount": 1}, {"currency": "USD"})):
            provider = FakeRazorpayClient()
            provider.payment_overrides = override
            with patch("apps.payments.services.razorpay.Client", return_value=provider):
                payload = self.registration_payload(
                    buyer={
                        "name": f"Wrong Details {chr(65 + index)}",
                        "email": f"wrong-{index}@example.test",
                        "phone": "+919876543210",
                    }
                )
                order = self.payment_order(payload, uuid.uuid4(), provider)
                response = self.verify_order(order.data["order_id"], provider)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(
                response.data["error"]["code"],
                "PAYMENT_REVIEW_REQUIRED",
            )
            self.assertEqual(Registration.objects.count(), 0)
            self.assertEqual(Ticket.objects.count(), 0)
            payment = Payment.objects.get(razorpay_order_id=order.data["order_id"])
            self.assertEqual(payment.status, Payment.Status.CAPTURED)
            self.assertIsNotNone(payment.captured_at)
            self.assertEqual(
                payment.ticket_issuance_status,
                Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED,
            )

    def test_unverified_payment_failure_report_does_not_change_order_state(self):
        payload = self.registration_payload()
        key = uuid.uuid4()
        provider = FakeRazorpayClient()
        with patch("apps.payments.services.razorpay.Client", return_value=provider):
            first_order = self.payment_order(payload, key, provider)
            failed = self.client.post(
                "/api/v1/payments/failure/",
                {
                    "razorpay_order_id": first_order.data["order_id"],
                    "razorpay_payment_id": "pay_unverified_client_claim",
                },
                format="json",
            )
            self.assertIsNone(
                Payment.objects.get(
                    razorpay_order_id=first_order.data["order_id"]
                ).razorpay_payment_id
            )
            retry_order = self.payment_order(payload, key, provider)
        self.assertEqual(failed.status_code, 200)
        self.assertEqual(retry_order.status_code, 200, retry_order.data)
        self.assertEqual(retry_order.data["order_id"], first_order.data["order_id"])
        self.assertEqual(Payment.objects.filter(intent_id=key).count(), 1)
        self.assertEqual(
            Payment.objects.get(intent_id=key).status,
            Payment.Status.CREATED,
        )
        self.assertIn(
            "provider status is unverified",
            Payment.objects.get(intent_id=key).failure_message,
        )
        self.assertEqual(Registration.objects.count(), 0)

    def test_ticket_pdf_endpoint_returns_readable_pdf_with_ticket_data(self):
        created = self.create_online_registration()
        response = self.client.get(
            f"/api/v1/registrations/{created.data['registration']['id']}/tickets.pdf"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertIn(b"Test Event", response.content)
        self.assertIn(b"Test Buyer", response.content)
        self.assertIn(created.data["tickets"][0]["id"].encode(), response.content)

    def test_brevo_webhook_is_authenticated_and_idempotently_marks_delivery(self):
        response = self.create_online_registration()
        delivery = TicketDelivery.objects.get(ticket_id=response.data["ticket"]["id"])
        with patch(
            "apps.payments.delivery.requests.post",
            return_value=FakeBrevoResponse("brevo-message-1"),
        ):
            self.assertEqual(process_next_ticket_email(), TicketDelivery.Status.SENT)
        delivery.refresh_from_db()
        self.assertEqual(delivery.provider_message_id, "brevo-message-1")

        with override_settings(BREVO_WEBHOOK_TOKEN="webhook-test-token"):
            denied = self.client.post(
                "/api/v1/payments/brevo/webhook/",
                {"event": "delivered", "message-id": "brevo-message-1"},
                format="json",
            )
            self.assertEqual(denied.status_code, 403)
            headers = {"HTTP_X_BREVO_WEBHOOK_TOKEN": "webhook-test-token"}
            first = self.client.post(
                "/api/v1/payments/brevo/webhook/",
                {"event": "delivered", "message-id": "brevo-message-1"},
                format="json",
                **headers,
            )
            delivery.refresh_from_db()
            delivered_at = delivery.delivered_at
            replay = self.client.post(
                "/api/v1/payments/brevo/webhook/",
                {"event": "delivered", "message-id": "brevo-message-1"},
                format="json",
                **headers,
            )

        self.assertEqual(first.status_code, 200, first.data)
        self.assertTrue(first.data["processed"])
        self.assertEqual(replay.status_code, 200, replay.data)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, TicketDelivery.Status.DELIVERED)
        self.assertEqual(delivery.delivered_at, delivered_at)

    def test_daily_quota_keeps_staff_slots_reserved_and_regular_limit_strict(self):
        self.event.capacity = 400
        self.event.save(update_fields=("capacity",))
        registration, initial_tickets = create_registration(
            event_id=self.event.id,
            tier_id=self.single.id,
            buyer={
                "name": "Quota Test Buyer",
                "email": "quota@example.test",
                "phone": "+919876543210",
            },
            source=Registration.Source.ON_SPOT,
            created_by=self.registration_staff,
            attendee_names=["Quota Attendee 0"],
        )
        extra_tickets = Ticket.objects.bulk_create(
            [
                Ticket(
                    registration=registration,
                    attendee_name=f"Quota Attendee {index}",
                )
                for index in range(1, 310)
            ]
        )
        from apps.payments.delivery import ensure_ticket_deliveries

        ensure_ticket_deliveries(registration, extra_tickets)
        TicketDelivery.objects.filter(
            ticket__registration=registration,
            ticket__attendee_name__in=[
                f"Quota Attendee {index}" for index in range(5)
            ],
        ).update(priority=TicketDelivery.Priority.STAFF)
        TicketDelivery.objects.filter(
            ticket__registration=registration,
            ticket__attendee_name__in=[
                f"Quota Attendee {index}" for index in range(5, 10)
            ],
        ).update(priority=TicketDelivery.Priority.COMPLIMENTARY)

        def accepted(*args, **kwargs):
            return FakeBrevoResponse(str(uuid.uuid4()))

        with (
            patch("apps.payments.delivery.generate_tickets_pdf", return_value=b"%PDF-test"),
            patch("apps.payments.delivery.requests.post", side_effect=accepted) as send_email,
        ):
            for _ in range(300):
                self.assertEqual(
                    process_next_ticket_email(),
                    TicketDelivery.Status.SENT,
                )
            self.assertIsNone(process_next_ticket_email())

        usage = EmailDailyUsage.objects.get()
        self.assertEqual(send_email.call_count, 300)
        self.assertEqual(usage.regular_sent, 295)
        self.assertEqual(usage.priority_sent, 5)
        self.assertEqual(usage.regular_slots_used, 295)
        self.assertEqual(usage.priority_slots_used, 5)
        self.assertEqual(
            TicketDelivery.objects.filter(status=TicketDelivery.Status.SENT).count(),
            300,
        )
        self.assertEqual(
            TicketDelivery.objects.filter(
                status=TicketDelivery.Status.PENDING,
                priority=TicketDelivery.Priority.REGULAR,
            ).count(),
            5,
        )
        self.assertEqual(
            TicketDelivery.objects.filter(
                status=TicketDelivery.Status.PENDING,
                priority__in=(
                    TicketDelivery.Priority.STAFF,
                    TicketDelivery.Priority.COMPLIMENTARY,
                ),
            ).count(),
            5,
        )
        self.assertEqual(len(initial_tickets), 1)
        next_day = usage.date + timedelta(days=1)
        with (
            patch("apps.payments.delivery.timezone.localdate", return_value=next_day),
            patch(
                "apps.payments.delivery.generate_tickets_pdf",
                return_value=b"%PDF-test",
            ),
            patch(
                "apps.payments.delivery.requests.post",
                return_value=FakeBrevoResponse(str(uuid.uuid4())),
            ),
        ):
            self.assertEqual(
                process_next_ticket_email(),
                TicketDelivery.Status.SENT,
            )
        next_day_usage = EmailDailyUsage.objects.get(date=next_day)
        self.assertEqual(next_day_usage.regular_sent, 0)
        self.assertEqual(next_day_usage.priority_sent, 1)

    def test_email_failure_keeps_ticket_valid_and_can_be_retried(self):
        provider = FakeRazorpayClient()
        with patch("apps.payments.services.razorpay.Client", return_value=provider):
            order = self.payment_order(self.registration_payload(), uuid.uuid4(), provider)
            verified = self.verify_order(order.data["order_id"], provider)
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.data["delivery_status"], TicketDelivery.Status.PENDING)
        self.assertEqual(Ticket.objects.count(), 1)
        delivery = TicketDelivery.objects.get()
        self.assertEqual(delivery.attempt_count, 0)
        with (
            patch(
                "apps.payments.delivery.generate_tickets_pdf",
                return_value=b"%PDF-ticket",
            ) as render_pdf,
            patch(
                "apps.payments.delivery.requests.post",
                return_value=FakeBrevoResponse("message-failed", status_code=400),
            ),
        ):
            self.assertEqual(process_next_ticket_email(), TicketDelivery.Status.FAILED)
        delivery.refresh_from_db()
        self.assertIn("HTTP 400", delivery.failure_reason)
        with patch(
            "apps.payments.delivery.requests.post",
            return_value=FakeBrevoResponse("message-retry"),
        ):
            self.client.force_authenticate(self.admin)
            retried = self.client.post(
                f"/api/v1/payments/delivery/{delivery.id}/retry/",
                {},
                format="json",
            )
            sent = process_next_ticket_email()
        self.assertEqual(retried.status_code, 202)
        self.assertEqual(sent, TicketDelivery.Status.SENT)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, TicketDelivery.Status.SENT)
        self.assertEqual(delivery.attempt_count, 2)
        self.assertEqual(delivery.pdf_content, b"%PDF-ticket")
        self.assertEqual(render_pdf.call_count, 1)
        self.assertEqual(Ticket.objects.count(), 1)

    def test_ambiguous_brevo_timeout_requires_reconciliation(self):
        response = self.create_online_registration()
        self.assertEqual(response.status_code, 200, response.data)
        delivery = TicketDelivery.objects.get()
        with (
            patch(
                "apps.payments.delivery.generate_tickets_pdf",
                return_value=b"%PDF-ticket",
            ),
            patch(
                "apps.payments.delivery.requests.post",
                side_effect=requests.Timeout("provider timed out"),
            ) as send_email,
        ):
            self.assertEqual(
                process_next_ticket_email(),
                TicketDelivery.Status.RECONCILIATION_REQUIRED,
            )
            self.assertIsNone(process_next_ticket_email())
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, TicketDelivery.Status.RECONCILIATION_REQUIRED)
        self.assertTrue(delivery.quota_reserved)
        self.assertEqual(delivery.pdf_content, b"%PDF-ticket")
        self.assertEqual(send_email.call_count, 1)
        self.assertEqual(Ticket.objects.get().status, Ticket.Status.ISSUED)
        self.client.force_authenticate(self.admin)
        retry = self.client.post(
            f"/api/v1/payments/delivery/{delivery.id}/retry/",
            {},
            format="json",
        )
        self.assertEqual(retry.status_code, 400)

    def test_ambiguous_brevo_5xx_requires_reconciliation(self):
        response = self.create_online_registration()
        self.assertEqual(response.status_code, 200, response.data)
        delivery = TicketDelivery.objects.get()
        with (
            patch(
                "apps.payments.delivery.generate_tickets_pdf",
                return_value=b"%PDF-ticket",
            ),
            patch(
                "apps.payments.delivery.requests.post",
                return_value=FakeBrevoResponse("unknown", status_code=503),
            ) as send_email,
        ):
            self.assertEqual(
                process_next_ticket_email(),
                TicketDelivery.Status.RECONCILIATION_REQUIRED,
            )
            self.assertIsNone(process_next_ticket_email())
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, TicketDelivery.Status.RECONCILIATION_REQUIRED)
        self.assertTrue(delivery.quota_reserved)
        self.assertEqual(send_email.call_count, 1)

    def test_abandoned_worker_claim_is_reconciled_after_restart(self):
        response = self.create_online_registration()
        self.assertEqual(response.status_code, 200, response.data)
        delivery = TicketDelivery.objects.get()
        usage = EmailDailyUsage.objects.create(
            date=timezone.localdate(),
            regular_slots_used=1,
        )
        delivery.status = TicketDelivery.Status.SENDING
        delivery.quota_date = usage.date
        delivery.quota_reserved = True
        delivery.claim_token = uuid.uuid4()
        delivery.attempt_count = 1
        delivery.last_attempt_at = timezone.now() - timedelta(minutes=6)
        delivery.save()
        with patch("apps.payments.delivery.requests.post") as send_email:
            self.assertIsNone(process_next_ticket_email())
        delivery.refresh_from_db()
        usage.refresh_from_db()
        self.assertEqual(delivery.status, TicketDelivery.Status.RECONCILIATION_REQUIRED)
        self.assertTrue(delivery.quota_reserved)
        self.assertEqual(usage.regular_slots_used, 1)
        send_email.assert_not_called()
        self.assertEqual(Ticket.objects.get().status, Ticket.Status.ISSUED)

    def test_pdf_failure_does_not_reverse_payment_and_delivery_is_retryable(self):
        provider = FakeRazorpayClient()
        with patch("apps.payments.services.razorpay.Client", return_value=provider):
            order = self.payment_order(self.registration_payload(), uuid.uuid4(), provider)
            with patch(
                "apps.payments.delivery.generate_tickets_pdf",
                side_effect=ValueError("PDF renderer unavailable"),
            ):
                verified = self.verify_order(order.data["order_id"], provider)
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(
            Payment.objects.get().verification_status,
            Payment.VerificationStatus.VERIFIED,
        )
        delivery = TicketDelivery.objects.get()
        self.assertEqual(delivery.status, TicketDelivery.Status.PENDING)
        self.client.force_authenticate(self.admin)
        with patch(
            "apps.payments.delivery.generate_tickets_pdf",
            side_effect=ValueError("PDF renderer unavailable"),
        ):
            self.assertEqual(
                process_next_ticket_email(),
                TicketDelivery.Status.FAILED,
            )
        retried = self.client.post(
            f"/api/v1/payments/delivery/{delivery.id}/retry/",
            {},
            format="json",
        )
        self.assertEqual(retried.status_code, 202)
        with patch(
            "apps.payments.delivery.requests.post",
            return_value=FakeBrevoResponse("message-retry"),
        ):
            self.assertEqual(process_next_ticket_email(), TicketDelivery.Status.SENT)
        self.assertEqual(Ticket.objects.count(), 1)

    def test_repeated_email_and_phone_are_allowed(self):
        first = self.create_online_registration()
        second = self.create_online_registration()
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(Registration.objects.count(), 2)

    def test_invalid_buyer_fields_are_rejected(self):
        payload = self.registration_payload()
        payload["buyer"]["name"] = "Buyer 12"
        payload["buyer"]["phone"] = "123"
        response = self.client.post(
            "/api/v1/payments/create-order/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Registration.objects.count(), 0)

    def test_capacity_is_consumed_per_admission_and_conflicts_when_insufficient(self):
        self.event.capacity = 5
        self.event.save(update_fields=("capacity",))
        response = self.create_online_registration(self.combo)
        self.assertEqual(response.status_code, 200, response.data)
        response = self.create_online_registration(self.combo)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Ticket.objects.exclude(status=Ticket.Status.CANCELLED).count(), 4)

    def test_on_spot_registration_requires_staff_and_uses_same_ticket_model(self):
        payload = self.registration_payload(self.combo)
        payload["attendee_names"] = ["A One", "B Two", "C Three", "D Four"]
        denied = self.client.post("/api/v1/registrations/on-spot/", payload, format="json")
        self.assertEqual(denied.status_code, 401)

        self.client.force_authenticate(self.registration_staff)
        key = str(uuid.uuid4())
        response = self.client.post(
            "/api/v1/registrations/on-spot/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["registration"]["source"], Registration.Source.ON_SPOT)
        self.assertEqual(len(response.data["tickets"]), 4)
        replay = self.client.post(
            "/api/v1/registrations/on-spot/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(replay.data["registration"]["id"], response.data["registration"]["id"])
        self.assertEqual(Registration.objects.count(), 1)
        self.assertEqual(Ticket.objects.count(), 4)

    def test_closed_event_and_wrong_tier_are_rejected(self):
        other_event = Event.objects.create(
            slug="other-event",
            name="Other",
            start_at=self.event.start_at,
            end_at=self.event.end_at,
            venue="Other",
            city="Bengaluru",
            address="Other",
            status=Event.Status.OPEN,
            registration_open=True,
            capacity=10,
        )
        other_tier = TicketTier.objects.create(
            event=other_event,
            slug="other-tier",
            name="Other",
            price="1.00",
        )
        response = self.create_online_registration(other_tier)
        self.assertEqual(response.status_code, 409)
        self.event.registration_open = False
        self.event.save(update_fields=("registration_open",))
        response = self.create_online_registration()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Registration.objects.count(), 0)

    def test_ticket_is_retrievable_and_cancellable_only_while_issued(self):
        created = self.create_online_registration()
        ticket = created.data["tickets"][0]
        detail = self.client.get(f"/api/v1/tickets/{ticket['id']}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["qr_token"], ticket["qr_token"])

        self.client.force_authenticate(self.admin)
        cancelled = self.client.post(f"/api/v1/tickets/{ticket['id']}/cancel/", {}, format="json")
        self.assertEqual(cancelled.status_code, 200)
        repeated = self.client.post(f"/api/v1/tickets/{ticket['id']}/cancel/", {}, format="json")
        self.assertEqual(repeated.status_code, 409)
        self.assertEqual(AuditLog.objects.filter(action="TICKET_CANCELLED").count(), 1)

    def test_scan_grants_once_and_persists_failed_attempts(self):
        created = self.create_online_registration()
        token = created.data["tickets"][0]["qr_token"]
        self.client.force_authenticate(self.scanner)

        granted = self.client.post("/api/v1/scans/", {"token": token}, format="json")
        self.assertEqual(granted.status_code, 200, granted.data)
        self.assertEqual(granted.data["result"], TicketScan.Result.ENTRY_GRANTED)
        rejected = self.client.post("/api/v1/scans/", {"token": token}, format="json")
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(rejected.data["result"], TicketScan.Result.ALREADY_USED)
        invalid = self.client.post("/api/v1/scans/", {"token": "unknown-token"}, format="json")
        self.assertEqual(invalid.status_code, 404)
        self.assertEqual(invalid.data["result"], TicketScan.Result.INVALID_TICKET)
        self.assertEqual(TicketScan.objects.count(), 3)
        self.assertEqual(
            Ticket.objects.get(token=token).status,
            Ticket.Status.USED,
        )

    def test_cancelled_and_wrong_event_scans_are_rejected(self):
        created = self.create_online_registration()
        token = created.data["tickets"][0]["qr_token"]
        self.client.force_authenticate(self.admin)
        self.client.post(f"/api/v1/tickets/{created.data['tickets'][0]['id']}/cancel/", {}, format="json")
        self.client.force_authenticate(self.scanner)
        cancelled = self.client.post("/api/v1/scans/", {"token": token}, format="json")
        self.assertEqual(cancelled.data["result"], TicketScan.Result.CANCELLED)

        other_event = Event.objects.create(
            slug="other-scan-event",
            name="Other",
            start_at=self.event.start_at,
            end_at=self.event.end_at,
            venue="Other",
            city="Bengaluru",
            address="Other",
            status=Event.Status.OPEN,
            registration_open=True,
            capacity=2,
        )
        other_gate = Gate.objects.create(event=other_event, name="Other Gate")
        StaffAssignment.objects.filter(user=self.scanner).delete()
        StaffAssignment.objects.create(user=self.scanner, gate=other_gate)
        other_ticket_response = self.create_online_registration()
        other_token = other_ticket_response.data["tickets"][0]["qr_token"]
        wrong_event = self.client.post("/api/v1/scans/", {"token": other_token}, format="json")
        self.assertEqual(wrong_event.data["result"], TicketScan.Result.WRONG_EVENT)

    def test_authentication_login_logout_and_roles(self):
        client = APIClient(enforce_csrf_checks=True)
        csrf_bootstrap = client.get("/api/v1/auth/csrf/")
        csrf_token = csrf_bootstrap.data["csrfToken"]
        login_response = client.post(
            "/api/v1/auth/login/",
            {"email": self.admin.email, "password": "Secure-test-pass-123!"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(login_response.status_code, 200, login_response.data)
        self.assertEqual(login_response.data["user"]["role"], "ADMIN")
        me = client.get("/api/v1/auth/me/")
        self.assertEqual(me.status_code, 200)
        denied = client.post("/api/v1/registrations/on-spot/", self.registration_payload(), format="json")
        self.assertEqual(denied.status_code, 403)
        csrf_token = client.get("/api/v1/auth/csrf/").data["csrfToken"]
        logout_response = client.post(
            "/api/v1/auth/logout/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(logout_response.status_code, 204)
        self.assertEqual(client.get("/api/v1/auth/me/").status_code, 401)

    @override_settings(CORS_ALLOWED_ORIGINS=["https://ticketing-test.vercel.app"])
    def test_api_allows_only_configured_credentialed_cors_origin(self):
        allowed = self.client.get(
            "/api/v1/auth/csrf/",
            HTTP_ORIGIN="https://ticketing-test.vercel.app",
        )
        preflight = self.client.options(
            "/api/v1/payments/create-order/",
            HTTP_ORIGIN="https://ticketing-test.vercel.app",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,idempotency-key,x-csrftoken",
        )
        denied = self.client.get(
            "/api/v1/auth/csrf/",
            HTTP_ORIGIN="https://untrusted.example",
        )
        self.assertEqual(
            allowed.headers["Access-Control-Allow-Origin"],
            "https://ticketing-test.vercel.app",
        )
        self.assertEqual(
            allowed.headers["Access-Control-Allow-Credentials"],
            "true",
        )
        self.assertIn(
            "idempotency-key",
            preflight.headers["Access-Control-Allow-Headers"],
        )
        self.assertNotIn("Access-Control-Allow-Origin", denied.headers)

    def test_dashboard_aggregates_are_database_backed(self):
        self.create_online_registration(self.combo)
        self.client.force_authenticate(self.admin)
        response = self.client.get(f"/api/v1/reports/dashboard/?event_id={self.event.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["registrations"], 1)
        self.assertEqual(response.data["active_tickets"], 4)
