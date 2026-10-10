import uuid
from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.events.models import Event, TicketTier
from apps.payments.models import (
    Payment,
    PaymentIntent,
    PaymentVerificationAttempt,
)
from apps.payments.services import payu_response_hash, payu_request_hash_for_params
from apps.registrations.models import Registration
from apps.tickets.models import Ticket


@override_settings(
    PAYU_MERCHANT_KEY="payu-test-key",
    PAYU_MERCHANT_SALT="payu-test-salt",
    PAYU_ENVIRONMENT="test",
    PAYU_FRONTEND_URL="https://tickets.example.test",
)
class PayUPaymentTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        start = timezone.now() + timedelta(days=2)
        self.event = Event.objects.create(
            slug="payu-test-event",
            name="PayU Test Event",
            start_at=start,
            end_at=start + timedelta(hours=3),
            venue="Test Venue",
            city="Bengaluru",
            address="Test address",
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
        self.payload = {
            "event_id": str(self.event.id),
            "ticket_tier_id": str(self.tier.id),
            "buyer": {
                "name": "Test Buyer",
                "email": "buyer@example.test",
                "phone": "+919876543210",
                "organization": "",
                "job_title": "",
            },
            "attendee_names": ["Test Buyer"],
        }

    def create_order(self, *, payload=None):
        response = self.client.post(
            "/api/v1/payments/create-order/",
            payload or self.payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response

    def callback_payload(self, order):
        payload = dict(order.data["payment_params"])
        payload.update(
            {
                "status": "success",
                "mihpayid": "payu-payment-123",
                "unmappedstatus": "captured",
            }
        )
        payload["hash"] = payu_response_hash(payload)
        return payload

    def verification_response(self, order, *, status="success", unmapped="captured"):
        params = order.data["payment_params"]
        return {
            "status": "1",
            "transaction_details": {
                order.data["order_id"]: {
                    "txnid": order.data["order_id"],
                    "mihpayid": "payu-payment-123",
                    "amt": params["amount"],
                    "productinfo": params["productinfo"],
                    "firstname": params["firstname"],
                    "udf1": params["udf1"],
                    "udf2": params["udf2"],
                    "status": status,
                    "unmappedstatus": unmapped,
                    "mode": "UPI",
                }
            },
        }

    def payu_response(self, response_data, *, status_code=200):
        response = Mock()
        response.status_code = status_code
        response.ok = 200 <= status_code < 400
        response.headers = {}
        response.json.return_value = response_data
        return response

    def check_status(self, order):
        payment = Payment.objects.get(provider_order_id=order.data["order_id"])
        return self.client.get(
            "/api/v1/payments/status/",
            {
                "txnid": order.data["order_id"],
                "idempotency_key": str(payment.intent_id),
            },
        )

    def test_create_order_builds_payu_hosted_request_and_server_hash(self):
        order = self.create_order()
        params = order.data["payment_params"]
        self.assertEqual(order.data["checkout_url"], "https://test.payu.in/_payment")
        self.assertEqual(params["amount"], "153.00")
        self.assertEqual(params["key"], "payu-test-key")
        self.assertEqual(params["surl"], "http://testserver/api/v1/payments/payu/success/")
        self.assertEqual(params["furl"], "http://testserver/api/v1/payments/payu/failure/")
        self.assertEqual(params["hash"], payu_request_hash_for_params(params))
        self.assertNotIn("payu-test-salt", params.values())
        self.assertEqual(Registration.objects.count(), 0)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_duplicate_submission_reuses_transaction_and_reservation(self):
        key = str(uuid.uuid4())
        first = self.client.post(
            "/api/v1/payments/create-order/",
            self.payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        replay = self.client.post(
            "/api/v1/payments/create-order/",
            self.payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(first.data["order_id"], replay.data["order_id"])
        self.assertEqual(Payment.objects.count(), 1)

    def test_pending_orders_reserve_capacity(self):
        self.event.capacity = 1
        self.event.save(update_fields=("capacity",))
        first = self.create_order()
        second = self.client.post(
            "/api/v1/payments/create-order/",
            self.payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(Payment.objects.count(), 1)

    def test_valid_callback_verifies_with_payu_and_issues_tickets_once(self):
        order = self.create_order()
        callback = self.callback_payload(order)
        response_data = self.verification_response(order)
        with patch(
            "apps.payments.services.requests.post",
            return_value=self.payu_response(response_data),
        ) as verify:
            response = self.client.post(
                "/api/v1/payments/payu/webhook/",
                callback,
                format="multipart",
            )
            repeated = self.client.post(
                "/api/v1/payments/payu/webhook/",
                callback,
                format="multipart",
            )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(repeated.status_code, 200, repeated.data)
        self.assertEqual(verify.call_count, 1)
        self.assertEqual(verify.call_args.kwargs["data"]["command"], "verify_payment")
        self.assertEqual(
            verify.call_args.kwargs["data"]["var1"],
            order.data["order_id"],
        )
        self.assertEqual(
            verify.call_args.kwargs["headers"]["Content-Type"],
            "application/x-www-form-urlencoded",
        )
        self.assertEqual(Registration.objects.count(), 1)
        self.assertEqual(Ticket.objects.count(), 1)
        payment = Payment.objects.get(provider_order_id=order.data["order_id"])
        self.assertEqual(payment.provider, Payment.Provider.PAYU)
        self.assertEqual(payment.status, Payment.Status.CAPTURED)
        self.assertEqual(payment.verification_status, Payment.VerificationStatus.VERIFIED)
        self.assertEqual(payment.ticket_issuance_status, Payment.TicketIssuanceStatus.ISSUED)

    def test_invalid_callback_hash_is_rejected_without_provider_verification(self):
        order = self.create_order()
        callback = self.callback_payload(order)
        callback["amount"] = "1.00"
        with patch("apps.payments.services.requests.post") as verify:
            response = self.client.post(
                "/api/v1/payments/payu/webhook/",
                callback,
                format="multipart",
            )
        self.assertEqual(response.status_code, 400)
        verify.assert_not_called()
        self.assertEqual(Ticket.objects.count(), 0)

    def test_payment_status_uses_server_verification_and_rejects_amount_mismatch(self):
        order = self.create_order()
        provider_result = self.verification_response(order)
        provider_result["transaction_details"][order.data["order_id"]]["amount"] = "1.00"
        with patch(
            "apps.payments.services.requests.post",
            return_value=self.payu_response(provider_result),
        ):
            response = self.check_status(order)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["payment_verified"])
        self.assertEqual(response.data["payment_status"], Payment.Status.CAPTURED)
        self.assertEqual(
            response.data["ticket_issuance_status"],
            Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED,
        )
        self.assertEqual(Ticket.objects.count(), 0)

    def test_payment_status_requires_the_booking_idempotency_key(self):
        order = self.create_order()
        response = self.client.get(
            "/api/v1/payments/status/",
            {
                "txnid": order.data["order_id"],
                "idempotency_key": str(uuid.uuid4()),
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_pending_and_failed_provider_results_never_issue_tickets(self):
        for provider_status, unmapped, expected in (
            ("pending", "initiated", Payment.Status.PENDING),
            ("failure", "failed", Payment.Status.FAILED),
        ):
            with self.subTest(provider_status=provider_status):
                order = self.create_order()
                provider_result = self.verification_response(
                    order,
                    status=provider_status,
                    unmapped=unmapped,
                )
                with patch(
                    "apps.payments.services.requests.post",
                    return_value=self.payu_response(provider_result),
                ):
                    response = self.check_status(order)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data["payment_status"], expected)
                self.assertFalse(response.data["payment_verified"])
                self.assertEqual(Ticket.objects.count(), 0)

    def test_unknown_transaction_is_not_found(self):
        response = self.client.get(
            "/api/v1/payments/status/",
            {
                "txnid": "unknown-transaction",
                "idempotency_key": str(uuid.uuid4()),
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_verification_api_outage_does_not_issue_tickets(self):
        order = self.create_order()
        with patch(
            "apps.payments.services.requests.post",
            side_effect=__import__("requests").Timeout("test timeout"),
        ):
            response = self.check_status(order)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["payment_status"], Payment.Status.PENDING)
        self.assertFalse(response.data["payment_verified"])
        payment = Payment.objects.get(provider_order_id=order.data["order_id"])
        self.assertEqual(payment.verification_attempt_count, 1)
        self.assertEqual(
            payment.verification_attempts.get().outcome,
            PaymentVerificationAttempt.Outcome.NETWORK_ERROR,
        )
        self.assertEqual(Ticket.objects.count(), 0)

    def test_captured_response_without_email_matches_documented_payu_shape(self):
        order = self.create_order()
        provider_result = self.verification_response(order)
        transaction_data = provider_result["transaction_details"][order.data["order_id"]]
        self.assertNotIn("email", transaction_data)
        self.assertIn("amt", transaction_data)
        with patch(
            "apps.payments.services.requests.post",
            return_value=self.payu_response(provider_result),
        ):
            response = self.check_status(order)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["payment_verified"])
        self.assertEqual(Registration.objects.count(), 1)
        self.assertEqual(Ticket.objects.count(), 1)

    def test_delayed_capture_is_reconciled_on_a_later_verification(self):
        order = self.create_order()
        pending = self.verification_response(
            order,
            status="pending",
            unmapped="initiated",
        )
        captured = self.verification_response(order)
        with patch(
            "apps.payments.services.requests.post",
            side_effect=[
                self.payu_response(pending),
                self.payu_response(captured),
            ],
        ):
            first = self.check_status(order)
            payment = Payment.objects.get(provider_order_id=order.data["order_id"])
            payment.next_verification_at = timezone.now() - timedelta(seconds=1)
            payment.save(update_fields=("next_verification_at",))
            second = self.check_status(order)
        self.assertEqual(first.data["payment_status"], Payment.Status.PENDING)
        self.assertFalse(first.data["payment_verified"])
        self.assertTrue(second.data["payment_verified"])
        self.assertEqual(Registration.objects.count(), 1)
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(
            list(
                PaymentVerificationAttempt.objects.filter(
                    payment__provider_order_id=order.data["order_id"]
                ).values_list("outcome", flat=True)
            ),
            [
                PaymentVerificationAttempt.Outcome.CAPTURED,
                PaymentVerificationAttempt.Outcome.PENDING,
            ],
        )

    def test_pending_verification_does_not_erase_prior_capture_review(self):
        order = self.create_order()
        captured_but_mismatched = self.verification_response(order)
        captured_but_mismatched["transaction_details"][order.data["order_id"]]["amt"] = "1.00"
        pending = self.verification_response(
            order,
            status="pending",
            unmapped="initiated",
        )
        with patch(
            "apps.payments.services.requests.post",
            side_effect=[
                self.payu_response(captured_but_mismatched),
                self.payu_response(pending),
            ],
        ):
            first = self.check_status(order)
            payment = Payment.objects.get(provider_order_id=order.data["order_id"])
            payment.next_verification_at = timezone.now() - timedelta(seconds=1)
            payment.save(update_fields=("next_verification_at",))
            second = self.check_status(order)
        payment.refresh_from_db()
        payment.intent.refresh_from_db()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.data["payment_status"], Payment.Status.PENDING)
        self.assertEqual(
            payment.ticket_issuance_status,
            Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED,
        )
        self.assertEqual(payment.intent.status, PaymentIntent.Status.REVIEW_REQUIRED)
        self.assertEqual(Registration.objects.count(), 0)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_api_authentication_failure_is_audited_and_remains_unresolved(self):
        order = self.create_order()
        with patch(
            "apps.payments.services.requests.post",
            return_value=self.payu_response(
                {"status": 0, "msg": "Invalid hash"},
                status_code=401,
            ),
        ):
            response = self.check_status(order)
        self.assertEqual(response.status_code, 200, response.data)
        payment = Payment.objects.get(provider_order_id=order.data["order_id"])
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(
            payment.verification_attempts.get().outcome,
            PaymentVerificationAttempt.Outcome.AUTH_ERROR,
        )
        self.assertEqual(Ticket.objects.count(), 0)

    def test_malformed_api_response_is_audited_and_remains_unresolved(self):
        order = self.create_order()
        malformed = self.payu_response([])
        with patch(
            "apps.payments.services.requests.post",
            return_value=malformed,
        ):
            response = self.check_status(order)
        self.assertEqual(response.status_code, 200, response.data)
        payment = Payment.objects.get(provider_order_id=order.data["order_id"])
        self.assertEqual(
            payment.verification_attempts.get().outcome,
            PaymentVerificationAttempt.Outcome.MALFORMED,
        )
        self.assertEqual(Ticket.objects.count(), 0)

    def test_admin_can_reconcile_verified_capture_after_ticket_issue_failure(self):
        order = self.create_order()
        provider_result = self.verification_response(order)
        with (
            patch(
                "apps.payments.services.requests.post",
                return_value=self.payu_response(provider_result),
            ),
            patch(
                "apps.payments.services.create_registration",
                side_effect=RuntimeError("simulated ticket failure"),
            ),
        ):
            first = self.check_status(order)
        self.assertEqual(first.status_code, 409, first.data)
        payment = Payment.objects.get(provider_order_id=order.data["order_id"])
        self.assertEqual(payment.verification_status, Payment.VerificationStatus.VERIFIED)
        self.assertEqual(
            payment.ticket_issuance_status,
            Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED,
        )

        admin = get_user_model().objects.create_user(
            email="admin@example.test",
            password="test-password",
            name="Payment Admin",
            role=get_user_model().Role.ADMIN,
            is_staff=True,
        )
        self.client.force_authenticate(user=admin)
        with patch("apps.payments.services.requests.post") as verify:
            response = self.client.post(
                f"/api/v1/payments/review/{payment.id}/reconcile/",
                {},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.data)
        verify.assert_not_called()
        payment.refresh_from_db()
        self.assertEqual(payment.ticket_issuance_status, Payment.TicketIssuanceStatus.ISSUED)
        self.assertEqual(Registration.objects.count(), 1)
        self.assertEqual(Ticket.objects.count(), 1)

    def test_ticket_creation_failure_is_retained_for_admin_review(self):
        order = self.create_order()
        callback = self.callback_payload(order)
        provider_result = self.verification_response(order)
        with (
            patch(
                "apps.payments.services.requests.post",
                return_value=self.payu_response(provider_result),
            ),
            patch(
                "apps.payments.services.create_registration",
                side_effect=RuntimeError("simulated ticket failure"),
            ) as create_registration,
        ):
            response = self.client.post(
                "/api/v1/payments/payu/webhook/",
                callback,
                format="multipart",
            )
            repeated = self.client.post(
                "/api/v1/payments/payu/webhook/",
                callback,
                format="multipart",
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(repeated.status_code, 200)
        create_registration.assert_called_once()
        payment = Payment.objects.get(provider_order_id=order.data["order_id"])
        self.assertEqual(payment.status, Payment.Status.CAPTURED)
        self.assertEqual(
            payment.verification_status,
            Payment.VerificationStatus.VERIFIED,
        )
        self.assertEqual(
            payment.ticket_issuance_status,
            Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED,
        )
        self.assertEqual(Registration.objects.count(), 0)
        self.assertEqual(Ticket.objects.count(), 0)
