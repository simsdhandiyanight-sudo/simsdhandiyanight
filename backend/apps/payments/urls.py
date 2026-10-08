from django.urls import path

from .views import (
    BrevoWebhookView,
    RazorpayCreateOrderView,
    RazorpayPaymentFailureView,
    RazorpayVerifyPaymentView,
    PaymentReviewDashboardView,
    TicketDeliveryDashboardView,
    TicketDeliveryPriorityView,
    TicketDeliveryRetryView,
)

urlpatterns = [
    path("payments/create-order/", RazorpayCreateOrderView.as_view(), name="razorpay-create-order"),
    path("payments/verify/", RazorpayVerifyPaymentView.as_view(), name="razorpay-verify-payment"),
    path("payments/failure/", RazorpayPaymentFailureView.as_view(), name="razorpay-payment-failure"),
    path(
        "payments/review/dashboard/",
        PaymentReviewDashboardView.as_view(),
        name="payment-review-dashboard",
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
