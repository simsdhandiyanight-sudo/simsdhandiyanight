from threading import Lock


class FakeRazorpayClient:
    def __init__(self, *args, **kwargs):
        self.lock = Lock()
        self.orders = {}
        self.last_order_payload = None
        self.order_overrides = {}
        self.payment_overrides = {}
        self.order = self.OrderResource(self)
        self.payment = self.PaymentResource(self)

    class OrderResource:
        def __init__(self, client):
            self.client = client

        def create(self, payload):
            suffix = payload["receipt"].removeprefix("pay-")
            order_id = f"order_{suffix}"
            with self.client.lock:
                self.client.last_order_payload = dict(payload)
            order = {
                "id": order_id,
                "amount": payload["amount"],
                "currency": payload["currency"],
                "status": "created",
            }
            with self.client.lock:
                self.client.orders[order_id] = order
            return order

        def fetch(self, order_id):
            with self.client.lock:
                order = dict(self.client.orders[order_id])
                order.update(self.client.order_overrides)
            return order

    class PaymentResource:
        def __init__(self, client):
            self.client = client

        def fetch(self, payment_id):
            suffix = payment_id.removeprefix("pay_")
            order_id = f"order_{suffix}"
            with self.client.lock:
                order = self.client.orders[order_id]
                payment = {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": order["amount"],
                    "currency": order["currency"],
                    "status": "captured",
                }
                payment.update(self.client.payment_overrides)
            return payment
