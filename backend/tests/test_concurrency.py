from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.events.models import Event, TicketTier
from apps.registrations.services import RegistrationConflict, create_registration
from apps.scanning.models import Gate, StaffAssignment
from apps.tickets.models import Ticket


@skipUnless(connection.vendor == "postgresql", "Concurrency guarantees require PostgreSQL row locks.")
class PostgreSQLConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        start = timezone.now() + timedelta(days=2)
        self.event = Event.objects.create(
            slug="concurrent-event",
            name="Concurrent Event",
            start_at=start,
            end_at=start + timedelta(hours=3),
            venue="Test",
            city="Bengaluru",
            address="Test",
            status=Event.Status.OPEN,
            registration_open=True,
            capacity=4,
        )
        self.combo = TicketTier.objects.create(
            event=self.event,
            slug="combo",
            name="Combo",
            price="447.00",
            admission_count=4,
        )
        self.scanner = get_user_model().objects.create_user(
            "concurrent-scanner@example.test",
            "Secure-test-pass-123!",
            name="Concurrent Scanner",
            role="SCANNER_STAFF",
        )
        self.gate = Gate.objects.create(event=self.event, name="Gate 1")
        StaffAssignment.objects.create(user=self.scanner, gate=self.gate)

    def test_simultaneous_scans_grant_entry_exactly_once(self):
        registration, tickets = create_registration(
            event_id=self.event.id,
            tier_id=self.combo.id,
            buyer={
                "name": "Test Buyer",
                "email": "buyer@example.test",
                "phone": "+919876543210",
            },
            source="ONLINE",
        )
        token = tickets[0].token
        barrier = Barrier(2)

        def scan_once():
            close_old_connections()
            client = APIClient()
            client.force_authenticate(
                get_user_model().objects.get(pk=self.scanner.pk)
            )
            barrier.wait(timeout=10)
            response = client.post(
                "/api/v1/scans/",
                {"token": token},
                format="json",
            )
            close_old_connections()
            return response.status_code, response.data["result"]

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: scan_once(), range(2)))

        self.assertEqual(
            [result for _, result in results].count("ENTRY_GRANTED"),
            1,
        )
        self.assertEqual([result for _, result in results].count("ALREADY_USED"), 1)
        self.assertEqual(Ticket.objects.get(pk=tickets[0].pk).status, Ticket.Status.USED)

    def test_simultaneous_combo_orders_never_exceed_capacity(self):
        barrier = Barrier(2)

        def register_once(index):
            close_old_connections()
            barrier.wait(timeout=10)
            try:
                create_registration(
                    event_id=self.event.id,
                    tier_id=self.combo.id,
                    buyer={
                        "name": f"Buyer {index}",
                        "email": "repeated@example.test",
                        "phone": "+919876543210",
                    },
                    source="ONLINE",
                )
                outcome = "created"
            except RegistrationConflict:
                outcome = "conflict"
            finally:
                close_old_connections()
            return outcome

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(register_once, range(2)))

        self.assertEqual(results.count("created"), 1)
        self.assertEqual(results.count("conflict"), 1)
        self.assertEqual(
            Ticket.objects.exclude(status=Ticket.Status.CANCELLED).count(),
            self.event.capacity,
        )
