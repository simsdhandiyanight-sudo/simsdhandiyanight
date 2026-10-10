from django.urls import path

from .views import (
    BrevoWebhookView,
    PayUCallbackView,
    PayUPaymentStatusView,
    PayUWebhookView,
    PayUCreatePaymentView,
    PaymentReviewDashboardView,
    PaymentReconcileView,
    TicketDeliveryDashboardView,
    TicketDeliveryPriorityView,
    TicketDeliveryRetryView,
)

urlpatterns = [
    path("payments/create-order/", PayUCreatePaymentView.as_view(), name="payu-create-payment"),
    path("payments/payu/success/", PayUCallbackView.as_view(), name="payu-success-callback"),
    path("payments/payu/failure/", PayUCallbackView.as_view(), name="payu-failure-callback"),
    path("payments/payu/webhook/", PayUWebhookView.as_view(), name="payu-webhook"),
    path("payments/status/", PayUPaymentStatusView.as_view(), name="payu-payment-status"),
    path(
        "payments/review/dashboard/",
        PaymentReviewDashboardView.as_view(),
        name="payment-review-dashboard",
    ),
    path(
        "payments/review/<uuid:payment_id>/reconcile/",
        PaymentReconcileView.as_view(),
        name="payment-reconcile",
    ),
    path(
        "payments/delivery/dashboard/",
        TicketDeliveryDashboardView.as_view(),
        name="ticket-delivery-dashboard",
    ),
    path(
        "payments/delivery/<uuid:delivery_id>/retry/",
        TicketDeliveryRetryView.as_view(),
        name="ticket-delivery-retry",
    ),
    path(
        "payments/delivery/<uuid:delivery_id>/priority/",
        TicketDeliveryPriorityView.as_view(),
        name="ticket-delivery-priority",
    ),
    path("payments/brevo/webhook/", BrevoWebhookView.as_view(), name="brevo-webhook"),
]
