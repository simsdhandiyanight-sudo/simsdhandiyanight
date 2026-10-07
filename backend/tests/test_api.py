from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.events.models import Event, TicketTier
from apps.registrations.models import Registration
from apps.scanning.models import Gate, StaffAssignment, TicketScan
from apps.tickets.models import Ticket


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

    def create_online_registration(self, tier=None, buyer=None):
        payload = self.registration_payload(tier)
        if buyer:
            payload["buyer"].update(buyer)
        response = self.client.post("/api/v1/registrations/", payload, format="json")
        return response

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

    def test_online_combo_creates_four_independently_scannable_tickets(self):
        response = self.create_online_registration(self.combo)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data["tickets"]), 4)
        self.assertEqual(response.data["registration"]["source"], Registration.Source.ONLINE)
        self.assertEqual(
            len({ticket["qr_token"] for ticket in response.data["tickets"]}),
            4,
        )
        self.assertEqual(Ticket.objects.filter(registration_id=response.data["registration"]["id"]).count(), 4)
        self.assertEqual(self.event.registrations.count(), 1)
        self.assertEqual(AuditLog.objects.filter(action="REGISTRATION_CREATED").count(), 1)

    def test_client_cannot_choose_registration_source(self):
        response = self.create_online_registration()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["registration"]["source"], Registration.Source.ONLINE)

    def test_repeated_email_and_phone_are_allowed(self):
        first = self.create_online_registration()
        second = self.create_online_registration()
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(Registration.objects.count(), 2)

    def test_invalid_buyer_fields_are_rejected(self):
        payload = self.registration_payload()
        payload["buyer"]["name"] = "Buyer 12"
        payload["buyer"]["phone"] = "123"
        response = self.client.post("/api/v1/registrations/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Registration.objects.count(), 0)

    def test_capacity_is_consumed_per_admission_and_conflicts_when_insufficient(self):
        self.event.capacity = 5
        self.event.save(update_fields=("capacity",))
        response = self.create_online_registration(self.combo)
        self.assertEqual(response.status_code, 201, response.data)
        response = self.create_online_registration(self.combo)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Ticket.objects.exclude(status=Ticket.Status.CANCELLED).count(), 4)

    def test_on_spot_registration_requires_staff_and_uses_same_ticket_model(self):
        payload = self.registration_payload(self.combo)
        denied = self.client.post("/api/v1/registrations/on-spot/", payload, format="json")
        self.assertEqual(denied.status_code, 401)

        self.client.force_authenticate(self.registration_staff)
        response = self.client.post("/api/v1/registrations/on-spot/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["registration"]["source"], Registration.Source.ON_SPOT)
        self.assertEqual(len(response.data["tickets"]), 4)

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
        client.get("/api/v1/auth/csrf/")
        csrf_token = client.cookies["csrftoken"].value
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
        csrf_token = client.cookies["csrftoken"].value
        logout_response = client.post(
            "/api/v1/auth/logout/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(logout_response.status_code, 204)
        self.assertEqual(client.get("/api/v1/auth/me/").status_code, 401)

    def test_dashboard_aggregates_are_database_backed(self):
        self.create_online_registration(self.combo)
        self.client.force_authenticate(self.admin)
        response = self.client.get(f"/api/v1/reports/dashboard/?event_id={self.event.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["registrations"], 1)
        self.assertEqual(response.data["active_tickets"], 4)
