import base64
import os
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.events.models import Event, TicketTier
from apps.payments.models import (
    Payment,
    TicketDelivery,
    TicketSheetSync,
)
from apps.registrations.models import Registration
from apps.registrations.serializers import RegistrationSerializer
from apps.scanning.models import Gate, StaffAssignment, TicketScan
from apps.registrations.services import RegistrationConflict, create_registration
from apps.tickets.models import Ticket


TEST_PAYMENT_SCREENSHOT = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAE0lEQVR4nGP8//8/AwMDEwMYAAAkBgMBXaJOiAAAAABJRU5ErkJggg=="
)


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


@override_settings(DJANGO_INTERNAL_API_KEY="n8n-test-token")
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
            payment_confirmation={
                "payment_received": True,
                "payment_method": "CASH",
            },
        )

        self.assertEqual(registration.ticket_tier.admission_count, 6)
        self.assertEqual([ticket.attendee_name for ticket in tickets], names)
        expected_ticket_codes = [
            f"{registration.registration_code}-T{index:02d}"
            for index in range(1, 7)
        ]
        self.assertEqual(
            [ticket.ticket_code for ticket in tickets],
            expected_ticket_codes,
        )
        self.assertEqual(len({ticket.ticket_code for ticket in tickets}), 6)

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
                payment_confirmation={
                    "payment_received": True,
                    "payment_method": "CASH",
                },
            )

        _, tickets = create_registration(
            event_id=self.event.id,
            tier_id=retired_combo.id,
            buyer=buyer,
            attendee_names=names,
            source=Registration.Source.ON_SPOT,
            exclude_payment_intent_id=uuid.uuid4(),
            payment_confirmation={
                "payment_received": True,
                "payment_method": "CASH",
            },
        )
        self.assertEqual(len(tickets), 4)

    def start_manual_registration(self, payload, key):
        return self.client.post(
            "/api/v1/payments/proof/registrations/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(key),
        )

    def create_manual_registration(self, tier=None, buyer=None, **overrides):
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
        payload.update(overrides)
        return self.start_manual_registration(payload, uuid.uuid4())

    def create_online_registration(self, tier=None, buyer=None):
        reservation = self.create_manual_registration(tier=tier, buyer=buyer)
        if reservation.status_code >= 400:
            return reservation

        registration_id = reservation.data["registration_id"]
        with patch(
            "apps.payments.proof.upload_payment_proof",
            return_value={
                "public_id": f"test/{uuid.uuid4()}",
                "asset_id": str(uuid.uuid4()),
                "version": 1,
                "format": "png",
                "size": len(TEST_PAYMENT_SCREENSHOT),
            },
        ):
            proof_response = self.client.post(
                f"/api/v1/payments/proof/registrations/{registration_id}/submit/",
                {
                    "utr_reference": f"UTR{uuid.uuid4().hex}",
                    "transaction_id": f"TXN{uuid.uuid4().hex}",
                    "screenshot": SimpleUploadedFile(
                        "payment.png",
                        TEST_PAYMENT_SCREENSHOT,
                        content_type="image/png",
                    ),
                },
                format="multipart",
                HTTP_X_PROOF_ACCESS_TOKEN=reservation.data["proof_access_token"],
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            )
        if proof_response.status_code >= 400:
            return proof_response

        admin_client = APIClient()
        admin_client.force_authenticate(self.admin)
        approval = admin_client.post(
            f"/api/v1/payments/proof/{proof_response.data['payment_id']}/approve/",
            {"confirmed_received": True},
            format="json",
        )
        if approval.status_code >= 400:
            return approval

        registration = Registration.objects.prefetch_related("tickets").get(
            pk=registration_id,
        )
        serialized = RegistrationSerializer(registration).data
        return SimpleNamespace(
            status_code=200,
            data={
                "registration": serialized,
                "tickets": serialized["tickets"],
                "delivery_status": "DISABLED",
            },
        )

    def test_manual_reservations_increment_registration_codes_and_keep_uuid_identity(self):
        first = self.create_manual_registration()
        second = self.create_manual_registration(
            buyer={
                "name": "Another Buyer",
                "email": "another@example.test",
            }
        )

        expected_prefix = f"SIMS-DN-{self.event.start_at.year}-"
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 201, second.data)
        self.assertTrue(first.data["registration_id"])
        self.assertEqual(
            first.data["registration_code"],
            f"{expected_prefix}00001",
        )
        self.assertEqual(
            second.data["registration_code"],
            f"{expected_prefix}00002",
        )
        self.assertEqual(Registration.objects.count(), 2)
        self.assertEqual(Ticket.objects.count(), 0)

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

    def test_manual_combo_reserves_four_tickets_without_issuing_before_approval(self):
        response = self.create_manual_registration(self.combo)
        self.assertEqual(response.status_code, 201, response.data)
        registration = Registration.objects.get(pk=response.data["registration_id"])
        intent = registration.payment_intent
        self.assertEqual(registration.source, Registration.Source.ONLINE)
        self.assertEqual(intent.quantity, 1)
        self.assertEqual(
            intent.attendee_names,
            ["Attendee One", "Attendee Two", "Attendee Three", "Attendee Four"],
        )
        self.assertEqual(Ticket.objects.filter(registration=registration).count(), 0)
        self.assertEqual(self.event.registrations.count(), 1)
        self.assertEqual(AuditLog.objects.filter(action="REGISTRATION_CREATED").count(), 1)
        self.assertEqual(TicketDelivery.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)

    def test_combo_requires_a_name_for_each_ticket(self):
        payload = self.registration_payload(self.combo)
        response = self.start_manual_registration(payload, uuid.uuid4())
        self.assertEqual(response.status_code, 400)
        self.assertIn("attendee_names", response.data["error"]["details"])
        self.assertEqual(Registration.objects.count(), 0)

        payload["attendee_names"] = ["One", "Two", "Three"]
        response = self.start_manual_registration(payload, uuid.uuid4())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Registration.objects.count(), 0)

    def test_client_cannot_choose_registration_source(self):
        response = self.create_manual_registration(source=Registration.Source.ON_SPOT)
        self.assertEqual(response.status_code, 201, response.data)
        registration = Registration.objects.get(pk=response.data["registration_id"])
        self.assertEqual(registration.source, Registration.Source.ONLINE)

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
















    def test_ticket_pdf_endpoint_returns_readable_pdf_with_ticket_data(self):
        self.event.start_at = timezone.localtime(self.event.start_at).replace(
            hour=18,
            minute=0,
            second=0,
            microsecond=0,
        )
        self.event.end_at = timezone.localtime(self.event.end_at).replace(
            hour=21,
            minute=0,
            second=0,
            microsecond=0,
        )
        self.event.save(update_fields=("start_at", "end_at"))
        created = self.create_online_registration()
        response = self.client.get(
            f"/api/v1/registrations/{created.data['registration']['id']}/tickets.pdf"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertIn(b"Test Event", response.content)
        self.assertIn(b"Test Buyer", response.content)
        self.assertIn(
            created.data["tickets"][0]["ticket_code"].encode(),
            response.content,
        )
        self.assertIn(b"6:00 PM", response.content)
        self.assertIn(b"9:00 PM", response.content)
        self.assertIn(b"Terms & Conditions", response.content)
        self.assertIn(
            b"Arrive 1 hour early for entry and security checking.",
            response.content,
        )
        self.assertIn(b"No re-entry after exit.", response.content)
        self.assertIn(
            b"Any misconduct or violation of rules may result in immediate eviction without refund.",
            response.content,
        )
        self.assertGreaterEqual(response.content.count(b"/Subtype /Image"), 2)







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
            "/api/v1/payments/proof/registrations/",
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
        self.assertEqual(denied.status_code, 404)
        csrf_token = client.get("/api/v1/auth/csrf/").data["csrfToken"]
        logout_response = client.post(
            "/api/v1/auth/logout/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(logout_response.status_code, 204)
        self.assertEqual(client.get("/api/v1/auth/me/").status_code, 401)

    @override_settings(
        CSRF_TRUSTED_ORIGINS=[
            *settings.CSRF_TRUSTED_ORIGINS,
            "http://localhost:3001",
        ]
    )
    def test_local_vite_origin_can_submit_csrf_protected_manual_payment_requests(self):
        origin = "http://localhost:3001"
        client = APIClient(enforce_csrf_checks=True)
        csrf_token = client.get("/api/v1/auth/csrf/").data["csrfToken"]

        response = client.post(
            "/api/v1/payments/proof/registrations/",
            {},
            format="json",
            HTTP_ORIGIN=origin,
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 400, response.data)

    @override_settings(CORS_ALLOWED_ORIGINS=["https://ticketing-test.vercel.app"])
    def test_api_allows_only_configured_credentialed_cors_origin(self):
        allowed = self.client.get(
            "/api/v1/auth/csrf/",
            HTTP_ORIGIN="https://ticketing-test.vercel.app",
        )
        preflight = self.client.options(
            "/api/v1/payments/proof/registrations/",
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
        registration_response = self.create_online_registration(self.combo)
        self.assertEqual(registration_response.status_code, 200)
        payment = Payment.objects.get(
            intent__registration_id=registration_response.data["registration"]["id"]
        )
        payment.provider = Payment.Provider.UPI_MANUAL
        payment.status = Payment.Status.VERIFIED
        payment.verification_status = Payment.VerificationStatus.VERIFIED
        payment.ticket_issuance_status = Payment.TicketIssuanceStatus.ISSUED
        payment.verified_by = self.admin
        payment.verified_at = timezone.now()
        payment.save(
            update_fields=(
                "provider",
                "status",
                "verification_status",
                "ticket_issuance_status",
                "verified_by",
                "verified_at",
                "updated_at",
            )
        )
        self.client.force_authenticate(self.admin)
        response = self.client.get(f"/api/v1/reports/dashboard/?event_id={self.event.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["registrations"], 1)
        self.assertEqual(response.data["online_registrations"], 1)
        self.assertEqual(response.data["paid_online_tickets"], 4)
        self.assertEqual(response.data["active_tickets"], 4)

        payment_review = self.client.get("/api/v1/payments/review/dashboard/")
        self.assertEqual(payment_review.status_code, 200, payment_review.data)
        self.assertEqual(
            payment_review.data["issue_counts"]["TICKET_WITHOUT_VALID_PAYMENT"],
            0,
        )
        self.assertEqual(
            payment_review.data["registrations_without_valid_payment"],
            [],
        )
