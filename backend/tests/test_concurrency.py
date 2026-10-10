from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import math
import time
from threading import Barrier, Lock
from unittest import skipUnless
from unittest.mock import Mock, patch
import uuid

from django.contrib.auth import get_user_model
from django.db import connections, connection
from django.db.models import Count
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.events.models import Event, TicketTier
from apps.payments.delivery import process_next_ticket_email
from apps.payments.models import EmailDailyUsage, Payment, PaymentIntent, TicketDelivery
from apps.registrations.models import Registration, RegistrationIdempotency
from apps.registrations.services import RegistrationConflict, create_registration
from apps.scanning.models import Gate, StaffAssignment
from apps.tickets.models import Ticket


class FakeBrevoResponse:
    status_code = 201

    def __init__(self, message_id):
        self.message_id = message_id

    def json(self):
        return {"messageId": self.message_id}


@skipUnless(connection.vendor == "postgresql", "Concurrency guarantees require PostgreSQL row locks.")
@override_settings(
    PAYU_MERCHANT_KEY="payu-test-key",
    PAYU_MERCHANT_SALT="payu-test-salt",
    PAYU_ENVIRONMENT="test",
    PAYU_FRONTEND_URL="https://tickets.example.test",
    BREVO_API_KEY="brevo-test-key",
    BREVO_SENDER_EMAIL="tickets@example.test",
)
class PostgreSQLConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.vendor != "postgresql":
            raise AssertionError("PostgreSQL concurrency tests require PostgreSQL.")
        database = connection.settings_dict
        print(
            "POSTGRESQL CONCURRENCY TEST DATABASE: ACTIVE "
            + json.dumps(
                {
                    "engine": database["ENGINE"],
                    "host": database["HOST"],
                    "port": database["PORT"],
                    "name": database["NAME"],
                },
                sort_keys=True,
            )
        )

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
            capacity=1000,
        )
        self.combo = TicketTier.objects.create(
            event=self.event,
            slug="combo",
            name="Combo",
            price="447.00",
            admission_count=4,
        )
        self.single = TicketTier.objects.create(
            event=self.event,
            slug="single",
            name="Single",
            price="149.00",
            admission_count=1,
        )
        self.scanners = []
        for index in range(6):
            scanner = get_user_model().objects.create_user(
                f"concurrent-scanner-{index}@example.test",
                "Secure-test-pass-123!",
                name=f"Concurrent Scanner {index}",
                role="SCANNER_STAFF",
            )
            gate = Gate.objects.create(event=self.event, name=f"Gate {index + 1}")
            StaffAssignment.objects.create(user=scanner, gate=gate)
            self.scanners.append(scanner)
        self.scanner = self.scanners[0]
        self.registration_staff = get_user_model().objects.create_user(
            "concurrent-registration@example.test",
            "Secure-test-pass-123!",
            name="Concurrent Registration Staff",
            role="REGISTRATION_STAFF",
        )
        self.admin = get_user_model().objects.create_user(
            "concurrent-admin@example.test",
            "Secure-test-pass-123!",
            name="Concurrent Admin",
            role="ADMIN",
        )

    def _payu_verification_response(self, *args, **kwargs):
        txnid = kwargs["data"]["var1"]
        payment = Payment.objects.select_related("intent").get(
            provider_order_id=txnid
        )
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "status": 1,
            "transaction_details": {
                txnid: {
                    "txnid": txnid,
                    "mihpayid": f"payu-{payment.id.hex}",
                    "amount": f"{payment.amount / 100:.2f}",
                    "productinfo": "Dhandiya Night Tickets",
                    "firstname": payment.intent.buyer_name.strip().split(maxsplit=1)[0][:60],
                    "email": payment.intent.buyer_email,
                    "udf1": str(payment.intent_id),
                    "udf2": str(payment.id),
                    "status": "success",
                    "unmappedstatus": "captured",
                }
            },
        }
        return response

    def _request_payload(self, name, email, tier=None):
        return {
            "event_id": str(self.event.id),
            "ticket_tier_id": str((tier or self.single).id),
            "buyer": {
                "name": name,
                "email": email,
                "phone": "+919876543210",
            },
            "attendee_names": [name],
        }

    @staticmethod
    def _tag(index):
        return chr(ord("A") + index)

    def _concurrent_requests(self, specs):
        barrier = Barrier(len(specs))

        def send(index, spec):
            connections.close_all()
            try:
                client = APIClient()
                if spec.get("user_id"):
                    client.force_authenticate(
                        get_user_model().objects.get(pk=spec["user_id"])
                    )
                barrier.wait(timeout=30)
                started = time.perf_counter()
                response = client.post(
                    spec["path"],
                    spec["payload"],
                    format="json",
                    HTTP_IDEMPOTENCY_KEY=spec.get("idempotency_key", ""),
                    REMOTE_ADDR=spec.get("remote_addr", f"198.51.100.{index + 1}"),
                )
                order_replayed = None
                verification_status = None
                if spec.get("payment_flow") and response.status_code in (200, 201):
                    order_replayed = response.data["replayed"]
                    order_id = response.data["order_id"]
                    verified = client.get(
                        "/api/v1/payments/status/",
                        {
                            "txnid": order_id,
                            "idempotency_key": response.data["payment_params"]["udf1"],
                        },
                    )
                    verification_status = verified.status_code
                    if verified.status_code >= 400:
                        response = verified
                        response_data = verified.data
                    else:
                        response_data = verified.data
                else:
                    response_data = response.data
                return {
                    "status": response.status_code,
                    "data": response_data,
                    "headers": dict(response.headers),
                    "order_replayed": order_replayed,
                    "verification_status": verification_status,
                    "latency_ms": (time.perf_counter() - started) * 1000,
                }
            except Exception as error:
                return {
                    "error": f"{type(error).__name__}: {error}",
                    "latency_ms": 0,
                }
            finally:
                connections.close_all()

        with patch(
            "apps.payments.services.requests.post",
            side_effect=self._payu_verification_response,
        ):
            with ThreadPoolExecutor(max_workers=len(specs)) as executor:
                futures = [
                    executor.submit(send, index, spec)
                    for index, spec in enumerate(specs)
                ]
                return [future.result() for future in futures]

    def _report_results(self, label, results):
        latencies = sorted(result["latency_ms"] for result in results)
        percentile = lambda value: latencies[max(0, math.ceil(value * len(latencies)) - 1)]
        status_counts = {}
        for result in results:
            key = str(result.get("status", result.get("error", "unknown")))
            status_counts[key] = status_counts.get(key, 0) + 1
        print(
            "POSTGRESQL_CONCURRENCY_METRICS "
            + json.dumps(
                {
                    "test": label,
                    "operations": len(results),
                    "successes": sum(
                        200 <= result.get("status", 0) < 300 for result in results
                    ),
                    "rejected_4xx": sum(
                        400 <= result.get("status", 0) < 500 for result in results
                    ),
                    "http_5xx": sum(
                        500 <= result.get("status", 0) < 600 for result in results
                    ),
                    "database_errors": sum(
                        "OperationalError" in result.get("error", "")
                        or "IntegrityError" in result.get("error", "")
                        for result in results
                    ),
                    "deadlocks": sum(
                        "deadlock" in result.get("error", "").lower()
                        for result in results
                    ),
                    "timeouts": sum(
                        "timeout" in result.get("error", "").lower()
                        for result in results
                    ),
                    "status_counts": status_counts,
                    "average_latency_ms": round(
                        sum(latencies) / len(latencies), 2
                    ),
                    "p95_latency_ms": round(percentile(0.95), 2),
                    "p99_latency_ms": round(percentile(0.99), 2),
                    "max_latency_ms": round(max(latencies), 2),
                },
                sort_keys=True,
            )
        )

    def _assert_database_and_dashboard_consistent(self):
        from apps.registrations.models import Registration
        from apps.scanning.models import TicketScan

        registrations = Registration.objects.filter(event=self.event)
        tickets = Ticket.objects.filter(registration__event=self.event)
        scans = TicketScan.objects.filter(event=self.event)
        active_tickets = tickets.exclude(status=Ticket.Status.CANCELLED)
        self.assertLessEqual(active_tickets.count(), self.event.capacity)
        self.assertEqual(tickets.values("id").distinct().count(), tickets.count())
        self.assertEqual(
            tickets.values("token").distinct().count(),
            tickets.count(),
        )
        self.assertEqual(
            scans.filter(result=TicketScan.Result.ENTRY_GRANTED)
            .values("ticket_id")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
            .count(),
            0,
        )
        self.assertEqual(
            tickets.filter(registration__isnull=True).count(),
            0,
        )
        for ticket in tickets.select_related("registration"):
            self.assertEqual(ticket.registration.event_id, self.event.id)
        verified_intents = PaymentIntent.objects.filter(
            event=self.event,
            status=PaymentIntent.Status.VERIFIED,
        )
        self.assertEqual(
            Payment.objects.filter(
                intent__in=verified_intents,
                verification_status=Payment.VerificationStatus.VERIFIED,
            ).count(),
            verified_intents.count(),
        )
        self.assertEqual(
            TicketDelivery.objects.filter(
                ticket__registration__event=self.event,
                status=TicketDelivery.Status.PENDING,
            ).count(),
            tickets.count(),
        )
        client = APIClient()
        client.force_authenticate(self.admin)
        dashboard = client.get(
            f"/api/v1/reports/dashboard/?event_id={self.event.id}"
        )
        self.assertEqual(dashboard.status_code, 200, dashboard.data)
        self.assertEqual(dashboard.data["registrations"], registrations.count())
        self.assertEqual(
            dashboard.data["online_registrations"],
            registrations.filter(source="ONLINE").count(),
        )
        self.assertEqual(dashboard.data["on_spot_registrations"], registrations.filter(source="ON_SPOT").count())
        self.assertEqual(dashboard.data["active_tickets"], active_tickets.count())
        self.assertEqual(
            dashboard.data["used_tickets"],
            tickets.filter(status=Ticket.Status.USED).count(),
        )
        self.assertEqual(dashboard.data["scan_attempts"], scans.count())

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
            attendee_names=[
                "Attendee One",
                "Attendee Two",
                "Attendee Three",
                "Attendee Four",
            ],
        )
        token = tickets[0].token
        barrier = Barrier(2)

        def scan_once():
            connections.close_all()
            try:
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
                return response.status_code, response.data["result"]
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: scan_once(), range(2)))

        self.assertEqual(
            [result for _, result in results].count("ENTRY_GRANTED"),
            1,
        )
        self.assertEqual([result for _, result in results].count("ALREADY_USED"), 1)
        self.assertEqual(Ticket.objects.get(pk=tickets[0].pk).status, Ticket.Status.USED)

    def test_simultaneous_combo_orders_never_exceed_capacity(self):
        self.event.capacity = 4
        self.event.save(update_fields=("capacity",))
        barrier = Barrier(2)

        def register_once(index):
            connections.close_all()
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
                    attendee_names=[
                        f"Attendee {index} One",
                        f"Attendee {index} Two",
                        f"Attendee {index} Three",
                        f"Attendee {index} Four",
                    ],
                )
                outcome = "created"
            except RegistrationConflict:
                outcome = "conflict"
            finally:
                connections.close_all()
            return outcome

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(register_once, range(2)))

        self.assertEqual(results.count("created"), 1)
        self.assertEqual(results.count("conflict"), 1)
        self.assertEqual(
            Ticket.objects.exclude(status=Ticket.Status.CANCELLED).count(),
            self.event.capacity,
        )

    def _same_key_concurrent_requests(self, request_count):
        key = str(uuid.uuid4())
        payload = {
            "event_id": str(self.event.id),
            "ticket_tier_id": str(self.combo.id),
            "buyer": {
                "name": "Same Buyer",
                "email": "same-buyer@example.test",
                "phone": "+919876543210",
            },
            "attendee_names": [
                "Attendee One",
                "Attendee Two",
                "Attendee Three",
                "Attendee Four",
            ],
        }
        specs = [
            {
                "path": "/api/v1/payments/create-order/",
                "payload": payload,
                "idempotency_key": key,
                "remote_addr": f"198.18.0.{index + 1}",
                "payment_flow": True,
            }
            for index in range(request_count)
        ]
        results = self._concurrent_requests(specs)
        self._report_results(f"same_key_{request_count}", results)
        self.assertEqual(sum(result.get("status") == 201 for result in results), 1)
        self.assertEqual(
            sum(result.get("status") == 200 for result in results),
            request_count - 1,
        )
        registration_ids = {
            result["data"]["registration"]["id"] for result in results
        }
        ticket_sets = {
            tuple(ticket["id"] for ticket in result["data"]["tickets"])
            for result in results
        }
        qr_token_sets = {
            tuple(ticket["qr_token"] for ticket in result["data"]["tickets"])
            for result in results
        }
        self.assertEqual(len(registration_ids), 1)
        self.assertEqual(len(ticket_sets), 1)
        self.assertEqual(len(qr_token_sets), 1)
        self.assertEqual(len(set(next(iter(qr_token_sets)))), 4)
        self.assertEqual(Registration.objects.count(), 1)
        self.assertEqual(Ticket.objects.count(), 4)
        self.assertEqual(PaymentIntent.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(
            Payment.objects.get().verification_status,
            Payment.VerificationStatus.VERIFIED,
        )
        self.assertEqual(TicketDelivery.objects.count(), 4)
        self.assertEqual(
            sum(result["verification_status"] == 200 for result in results),
            request_count,
        )
        self.assertEqual(
            sum(result["order_replayed"] is True for result in results),
            request_count - 1,
        )
        self.assertEqual(
            str(PaymentIntent.objects.get().registration_id),
            next(iter(registration_ids)),
        )

    def test_five_concurrent_identical_requests_create_one_registration(self):
        self._same_key_concurrent_requests(5)

    def test_ten_concurrent_identical_requests_create_one_registration(self):
        self._same_key_concurrent_requests(10)

    def test_six_simultaneous_scans_of_same_ticket_grant_once(self):
        _, tickets = create_registration(
            event_id=self.event.id,
            tier_id=self.single.id,
            buyer={
                "name": "Race Attendee",
                "email": "race-attendee@example.test",
                "phone": "+919876543210",
            },
            source="ONLINE",
            attendee_names=["Race Attendee"],
        )
        ticket = tickets[0]
        specs = [
            {
                "path": "/api/v1/scans/",
                "payload": {"token": ticket.token},
                "user_id": scanner.id,
                "remote_addr": f"203.0.113.{index + 1}",
            }
            for index, scanner in enumerate(self.scanners)
        ]
        results = self._concurrent_requests(specs)
        self._report_results("same_qr_6", results)
        self.assertEqual(sum(result.get("data", {}).get("result") == "ENTRY_GRANTED" for result in results), 1)
        self.assertEqual(sum(result.get("data", {}).get("result") == "ALREADY_USED" for result in results), 5)
        self.assertEqual(sum(result.get("status") == 200 for result in results), 1)
        self.assertEqual(sum(result.get("status") == 409 for result in results), 5)
        from apps.scanning.models import TicketScan

        self.assertEqual(TicketScan.objects.filter(ticket=ticket).count(), 6)
        self.assertEqual(
            TicketScan.objects.filter(
                ticket=ticket,
                result=TicketScan.Result.ENTRY_GRANTED,
            ).count(),
            1,
        )
        self.assertEqual(
            Ticket.objects.get(pk=ticket.pk).status,
            Ticket.Status.USED,
        )
        self._assert_database_and_dashboard_consistent()

    def _five_registration_specs(self, source):
        specs = []
        for index in range(5):
            name = f"{source.title()} Attendee {self._tag(index)}"
            payload = self._request_payload(
                name,
                f"{source.lower()}-{index}@example.test",
                tier=self.combo,
            )
            payload["attendee_names"] = [
                f"{name} One",
                f"{name} Two",
                f"{name} Three",
                f"{name} Four",
            ]
            specs.append(
                {
                    "path": (
                        "/api/v1/registrations/on-spot/"
                        if source == "onspot"
                        else "/api/v1/payments/create-order/"
                    ),
                    "payload": payload,
                    "user_id": (
                        self.registration_staff.id if source == "onspot" else None
                    ),
                    "idempotency_key": str(uuid.uuid4()),
                    "remote_addr": f"192.0.2.{index + 1}",
                    "payment_flow": source == "online",
                }
            )
        return specs

    def _assert_registration_results(self, source, specs, results):
        from apps.registrations.models import Registration, RegistrationIdempotency

        self._report_results(f"{source}_registrations_5", results)
        self.assertEqual([result.get("status") for result in results], [201] * 5)
        registration_source = (
            Registration.Source.ON_SPOT if source == "onspot" else Registration.Source.ONLINE
        )
        registrations = list(
            Registration.objects.filter(event=self.event, source=registration_source)
        )
        self.assertEqual(len(registrations), 5)
        self.assertEqual(len({registration.id for registration in registrations}), 5)
        self.assertEqual(
            Ticket.objects.filter(registration__in=registrations).count(),
            20,
        )
        if source == "onspot":
            self.assertEqual(RegistrationIdempotency.objects.count(), 5)
        else:
            self.assertEqual(PaymentIntent.objects.count(), 5)
            self.assertEqual(Payment.objects.count(), 5)
            self.assertTrue(
                all(result["verification_status"] == 200 for result in results)
            )
        for spec, result in zip(specs, results):
            response_registration = result["data"]["registration"]
            registration = Registration.objects.get(pk=response_registration["id"])
            self.assertEqual(registration.source, registration_source)
            self.assertEqual(registration.event_id, self.event.id)
            self.assertEqual(registration.ticket_tier_id, self.combo.id)
            self.assertEqual(
                sorted(
                    registration.tickets.order_by("created_at").values_list(
                        "attendee_name",
                        flat=True,
                    )
                ),
                sorted(spec["payload"]["attendee_names"]),
            )
            for response_ticket in result["data"]["tickets"]:
                stored_ticket = Ticket.objects.get(pk=response_ticket["id"])
                self.assertEqual(stored_ticket.registration_id, registration.id)
                self.assertEqual(stored_ticket.token, response_ticket["qr_token"])

    def test_five_on_spot_registrations_concurrently(self):
        specs = self._five_registration_specs("onspot")
        results = self._concurrent_requests(specs)
        self._assert_registration_results("onspot", specs, results)
        self._assert_database_and_dashboard_consistent()

    def test_five_online_registrations_concurrently(self):
        specs = self._five_registration_specs("online")
        results = self._concurrent_requests(specs)
        self._assert_registration_results("online", specs, results)
        self._assert_database_and_dashboard_consistent()

    def test_mixed_sixteen_operations_repeated_ten_times(self):
        for repetition in range(10):
            specs = []
            for index, scanner in enumerate(self.scanners):
                _, tickets = create_registration(
                    event_id=self.event.id,
                    tier_id=self.single.id,
                    buyer={
                        "name": f"Mixed Scanner {repetition}-{index}",
                        "email": f"mixed-scan-{repetition}-{index}@example.test",
                        "phone": "+919876543210",
                    },
                    source="ONLINE",
                    attendee_names=[f"Mixed Scanner {repetition}-{index}"],
                )
                specs.append(
                    {
                        "path": "/api/v1/scans/",
                        "payload": {"token": tickets[0].token},
                        "user_id": scanner.id,
                        "remote_addr": f"10.{repetition}.{index}.1",
                    }
                )
            for source in ("onspot", "online"):
                batch = self._five_registration_specs(source)
                for index, spec in enumerate(batch):
                    spec["payload"]["buyer"]["name"] += f" {self._tag(repetition)}"
                    spec["payload"]["buyer"]["email"] = (
                        f"{source}-{repetition}-{index}@example.test"
                    )
                    spec["payload"]["attendee_names"] = [
                        f"{name} {self._tag(repetition)}"
                        for name in spec["payload"]["attendee_names"]
                    ]
                    spec["remote_addr"] = (
                        f"10.{repetition}.{index}.{2 if source == 'onspot' else 3}"
                    )
                specs.extend(batch)
            results = self._concurrent_requests(specs)
            self._report_results(f"mixed_16_run_{repetition + 1}", results)
            self.assertEqual(len(results), 16)
            self.assertEqual(
                sum(result.get("status") in (200, 201) for result in results),
                16,
            )
            self.assertEqual(
                sum(500 <= result.get("status", 0) < 600 for result in results),
                0,
            )
            self.assertFalse([result for result in results if "error" in result])
            self.assertEqual(
                Registration.objects.filter(event=self.event).count(),
                16 * (repetition + 1),
            )
            self.assertEqual(
                Ticket.objects.filter(registration__event=self.event).count(),
                46 * (repetition + 1),
            )
            self.assertEqual(
                RegistrationIdempotency.objects.count(),
                5 * (repetition + 1),
            )
            self.assertEqual(
                PaymentIntent.objects.count(),
                5 * (repetition + 1),
            )
            self.assertEqual(
                Payment.objects.count(),
                5 * (repetition + 1),
            )
            from apps.scanning.models import TicketScan

            self.assertEqual(
                TicketScan.objects.filter(event=self.event).count(),
                6 * (repetition + 1),
            )
            self._assert_database_and_dashboard_consistent()

    def test_capacity_race_five_registrations_for_two_tickets(self):
        self.event.capacity = 2
        self.event.save(update_fields=("capacity",))
        specs = []
        for index in range(5):
            name = f"Capacity Attendee {self._tag(index)}"
            specs.append(
                {
                    "path": "/api/v1/payments/create-order/",
                    "payload": self._request_payload(
                        name,
                        f"capacity-{index}@example.test",
                    ),
                    "idempotency_key": str(uuid.uuid4()),
                    "remote_addr": f"198.51.100.{index + 1}",
                    "payment_flow": True,
                }
            )
        results = self._concurrent_requests(specs)
        self._report_results("capacity_race_5_for_2", results)
        self.assertEqual(sum(result.get("status") == 201 for result in results), 2)
        self.assertEqual(sum(result.get("status") == 409 for result in results), 3)
        self.assertEqual(
            Ticket.objects.exclude(status=Ticket.Status.CANCELLED).count(),
            2,
        )
        self.assertEqual(Registration.objects.count(), 2)
        self.assertEqual(RegistrationIdempotency.objects.count(), 0)
        self.assertEqual(PaymentIntent.objects.count(), 2)
        self.assertEqual(Payment.objects.count(), 2)
        self._assert_database_and_dashboard_consistent()

    def _create_and_verify_online(self, payload, key, remote_addr):
        client = APIClient()
        with patch(
            "apps.payments.services.requests.post",
            side_effect=self._payu_verification_response,
        ):
            order = client.post(
                "/api/v1/payments/create-order/",
                payload,
                format="json",
                HTTP_IDEMPOTENCY_KEY=key,
                REMOTE_ADDR=remote_addr,
            )
            self.assertEqual(order.status_code, 201, order.data)
            order_id = order.data["order_id"]
            verification = client.get(
                "/api/v1/payments/status/",
                {
                    "txnid": order_id,
                    "idempotency_key": order.data["payment_params"]["udf1"],
                },
            )
        self.assertEqual(verification.status_code, 200, verification.data)
        return order, verification

    def _mixed_load_specs(self, operation_count):
        scan_count = operation_count // 3
        onspot_count = operation_count // 3
        online_count = operation_count // 6
        duplicate_count = operation_count - scan_count - onspot_count - online_count
        specs = []
        for index in range(scan_count):
            _, tickets = create_registration(
                event_id=self.event.id,
                tier_id=self.single.id,
                buyer={
                    "name": f"Load Scanner {operation_count}-{index}",
                    "email": f"load-scan-{operation_count}-{index}@example.test",
                    "phone": "+919876543210",
                },
                source="ONLINE",
                attendee_names=[f"Load Scanner {operation_count}-{index}"],
            )
            specs.append(
                {
                    "path": "/api/v1/scans/",
                    "payload": {"token": tickets[0].token},
                    "user_id": self.scanners[index % len(self.scanners)].id,
                    "remote_addr": f"172.16.{operation_count}.{index + 1}",
                }
            )
        for index in range(onspot_count):
            name = f"Load Onspot {self._tag(index)}"
            specs.append(
                {
                    "path": "/api/v1/registrations/on-spot/",
                    "payload": self._request_payload(name, f"load-ons-{operation_count}-{index}@example.test"),
                    "user_id": self.registration_staff.id,
                    "idempotency_key": str(uuid.uuid4()),
                    "remote_addr": f"172.17.{operation_count}.{index + 1}",
                }
            )
        for index in range(online_count):
            name = f"Load Online {self._tag(index)}"
            specs.append(
                {
                    "path": "/api/v1/payments/create-order/",
                    "payload": self._request_payload(name, f"load-onl-{operation_count}-{index}@example.test"),
                    "idempotency_key": str(uuid.uuid4()),
                    "remote_addr": f"172.18.{operation_count}.{index + 1}",
                    "payment_flow": True,
                }
            )
        for index in range(duplicate_count):
            name = f"Load Duplicate {self._tag(index)}"
            payload = self._request_payload(
                name,
                f"load-dup-{operation_count}-{index}@example.test",
            )
            key = str(uuid.uuid4())
            self._create_and_verify_online(
                payload,
                key,
                f"172.19.{operation_count}.{index + 1}",
            )
            specs.append(
                {
                    "path": "/api/v1/payments/create-order/",
                    "payload": payload,
                    "idempotency_key": key,
                    "remote_addr": f"172.20.{operation_count}.{index + 1}",
                    "payment_flow": True,
                }
            )
        return specs, scan_count

    def _run_mixed_load_test(self, operation_count):
        specs, scan_count = self._mixed_load_specs(operation_count)
        results = self._concurrent_requests(specs)
        self._report_results(f"mixed_load_{operation_count}", results)
        self.assertEqual(len(results), operation_count)
        self.assertFalse([result for result in results if "error" in result])
        self.assertEqual(
            sum(result.get("status") == 500 for result in results),
            0,
        )
        self.assertEqual(
            sum(result.get("status") in (200, 201) for result in results),
            operation_count,
        )
        self.assertTrue(
            all(
                result.get("data", {}).get("result") == "ENTRY_GRANTED"
                for result in results[:scan_count]
            )
        )
        self.assertEqual(
            sum(result.get("order_replayed") is True for result in results),
            operation_count - scan_count - operation_count // 3 - operation_count // 6,
        )
        self.assertEqual(
            Registration.objects.filter(event=self.event).count(),
            operation_count,
        )
        self.assertEqual(
            Ticket.objects.filter(registration__event=self.event).count(),
            operation_count,
        )
        self.assertEqual(
            RegistrationIdempotency.objects.count(),
            operation_count // 3,
        )
        self.assertEqual(
            PaymentIntent.objects.count(),
            operation_count // 6
            + operation_count
            - scan_count
            - operation_count // 3
            - operation_count // 6,
        )
        self.assertEqual(
            Payment.objects.count(),
            PaymentIntent.objects.count(),
        )
        from apps.scanning.models import TicketScan

        self.assertEqual(TicketScan.objects.filter(event=self.event).count(), scan_count)
        self._assert_database_and_dashboard_consistent()

    def test_twenty_five_concurrent_mixed_operations(self):
        self._run_mixed_load_test(25)

    def test_fifty_concurrent_mixed_operations(self):
        self._run_mixed_load_test(50)

    def test_concurrent_email_workers_claim_each_delivery_once(self):
        deliveries_expected = 6
        for index in range(deliveries_expected):
            create_registration(
                event_id=self.event.id,
                tier_id=self.single.id,
                buyer={
                    "name": f"Email Buyer {index}",
                    "email": f"email-buyer-{index}@example.test",
                    "phone": "+919876543210",
                },
                source=Registration.Source.ON_SPOT,
                created_by=self.registration_staff,
                attendee_names=[f"Email Attendee {index}"],
            )

        barrier = Barrier(deliveries_expected)
        message_id_lock = Lock()
        message_counter = iter(range(deliveries_expected))

        def send_email(*args, **kwargs):
            with message_id_lock:
                message_id = f"concurrent-email-{next(message_counter)}"
            return FakeBrevoResponse(message_id)

        def process():
            connections.close_all()
            try:
                barrier.wait(timeout=30)
                return process_next_ticket_email()
            finally:
                connections.close_all()

        with (
            patch("apps.payments.delivery.generate_tickets_pdf", return_value=b"%PDF-test"),
            patch("apps.payments.delivery.requests.post", side_effect=send_email),
            ThreadPoolExecutor(max_workers=deliveries_expected) as executor,
        ):
            results = list(executor.map(lambda _: process(), range(deliveries_expected)))

        self.assertEqual(results, [TicketDelivery.Status.SENT] * deliveries_expected)
        self.assertEqual(
            TicketDelivery.objects.filter(status=TicketDelivery.Status.SENT).count(),
            deliveries_expected,
        )
        self.assertEqual(
            TicketDelivery.objects.values("ticket_id").distinct().count(),
            deliveries_expected,
        )
        self.assertEqual(
            TicketDelivery.objects.values("provider_message_id").distinct().count(),
            deliveries_expected,
        )

    def test_concurrent_priority_workers_cannot_exceed_daily_quota(self):
        deliveries_expected = 7
        for index in range(deliveries_expected):
            create_registration(
                event_id=self.event.id,
                tier_id=self.single.id,
                buyer={
                    "name": f"Priority Buyer {index}",
                    "email": f"priority-buyer-{index}@example.test",
                    "phone": "+919876543210",
                },
                source=Registration.Source.ON_SPOT,
                created_by=self.registration_staff,
                attendee_names=[f"Priority Attendee {index}"],
            )
        TicketDelivery.objects.filter(
            ticket__registration__event=self.event,
        ).update(priority=TicketDelivery.Priority.STAFF)

        barrier = Barrier(deliveries_expected)
        message_id_lock = Lock()
        message_counter = iter(range(deliveries_expected))

        def send_email(*args, **kwargs):
            with message_id_lock:
                message_id = f"priority-email-{next(message_counter)}"
            return FakeBrevoResponse(message_id)

        def process():
            connections.close_all()
            try:
                barrier.wait(timeout=30)
                return process_next_ticket_email()
            finally:
                connections.close_all()

        with (
            patch("apps.payments.delivery.generate_tickets_pdf", return_value=b"%PDF-test"),
            patch("apps.payments.delivery.requests.post", side_effect=send_email),
            ThreadPoolExecutor(max_workers=deliveries_expected) as executor,
        ):
            results = list(executor.map(lambda _: process(), range(deliveries_expected)))

        usage = EmailDailyUsage.objects.get()
        self.assertEqual(results.count(TicketDelivery.Status.SENT), 5)
        self.assertEqual(results.count(None), 2)
        self.assertEqual(usage.priority_slots_used, 5)
        self.assertEqual(usage.priority_sent, 5)
        self.assertEqual(
            TicketDelivery.objects.filter(status=TicketDelivery.Status.SENT).count(),
            5,
        )
        self.assertEqual(
            TicketDelivery.objects.filter(status=TicketDelivery.Status.PENDING).count(),
            2,
        )
