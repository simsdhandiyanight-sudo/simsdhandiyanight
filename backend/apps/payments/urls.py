from django.urls import path

from .views import (
    PaymentProofApproveView,
    PaymentProofConfirmationView,
    PaymentProofDashboardView,
    PaymentProofRegistrationView,
    PaymentProofRejectView,
    PaymentProofScreenshotView,
    PaymentProofStatusView,
    PaymentProofTicketsPdfView,
    PaymentProofSubmissionView,
    PayUCallbackView,
    PayUPaymentStatusView,
    PayUWebhookView,
    PayUCreatePaymentView,
    PaymentReviewDashboardView,
    PaymentReconcileView,
)

urlpatterns = [
    path(
        "payments/proof/registrations/",
        PaymentProofRegistrationView.as_view(),
        name="payment-proof-registration",
    ),
    path(
        "payments/proof/registrations/<uuid:registration_id>/",
        PaymentProofStatusView.as_view(),
        name="payment-proof-status",
    ),
    path(
        "payments/proof/registrations/<uuid:registration_id>/submit/",
        PaymentProofSubmissionView.as_view(),
        name="payment-proof-submit",
    ),
    path(
        "payments/proof/registrations/<uuid:registration_id>/ticket-id.pdf",
        PaymentProofConfirmationView.as_view(),
        name="payment-proof-ticket-id",
    ),
    path(
        "payments/proof/registrations/<uuid:registration_id>/tickets.pdf",
        PaymentProofTicketsPdfView.as_view(),
        name="payment-proof-issued-tickets",
    ),
    path(
        "payments/proof/dashboard/",
        PaymentProofDashboardView.as_view(),
        name="payment-proof-dashboard",
    ),
    path(
        "payments/proof/<uuid:payment_id>/screenshot/",
        PaymentProofScreenshotView.as_view(),
        name="payment-proof-screenshot",
    ),
    path(
        "payments/proof/<uuid:payment_id>/approve/",
        PaymentProofApproveView.as_view(),
        name="payment-proof-approve",
    ),
    path(
        "payments/proof/<uuid:payment_id>/reject/",
        PaymentProofRejectView.as_view(),
        name="payment-proof-reject",
    ),
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
]
