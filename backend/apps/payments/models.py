import uuid

from django.db import models
from django.db.models import F, Q


class PaymentIntent(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        VERIFIED = "VERIFIED", "Verified"
        FAILED = "FAILED", "Failed"
        REVIEW_REQUIRED = "REVIEW_REQUIRED", "Payment review required"

    idempotency_key = models.UUIDField(primary_key=True, editable=False)
    request_hash = models.CharField(max_length=64)
    event = models.ForeignKey("events.Event", on_delete=models.PROTECT, related_name="payment_intents")
    ticket_tier = models.ForeignKey(
        "events.TicketTier",
        on_delete=models.PROTECT,
        related_name="payment_intents",
    )
    buyer_name = models.CharField(max_length=200)
    buyer_email = models.EmailField()
    buyer_phone = models.CharField(max_length=16)
    buyer_organization = models.CharField(max_length=200, blank=True)
    buyer_job_title = models.CharField(max_length=120, blank=True)
    attendee_names = models.JSONField(default=list)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    registration = models.OneToOneField(
        "registrations.Registration",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payment_intent",
    )
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=("event", "status", "expires_at")),
            models.Index(fields=("buyer_email", "created_at")),
        ]


class Payment(models.Model):
    class Provider(models.TextChoices):
        RAZORPAY = "RAZORPAY", "Razorpay (legacy)"
        PAYU = "PAYU", "PayU"

    class Status(models.TextChoices):
        CREATING = "CREATING", "Creating order"
        CREATED = "CREATED", "Order created"
        PENDING = "PENDING", "Pending"
        AUTHORIZED = "AUTHORIZED", "Authorized"
        CAPTURED = "CAPTURED", "Captured"
        FAILED = "FAILED", "Failed"

    class VerificationStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        VERIFIED = "VERIFIED", "Verified"
        FAILED = "FAILED", "Failed"

    class TicketIssuanceStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ISSUED = "ISSUED", "Tickets issued"
        ADMIN_REVIEW_REQUIRED = "ADMIN_REVIEW_REQUIRED", "Admin review required"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intent = models.ForeignKey(PaymentIntent, on_delete=models.PROTECT, related_name="payments")
    provider = models.CharField(
        max_length=12,
        choices=Provider.choices,
        default=Provider.RAZORPAY,
    )
    provider_order_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    provider_payment_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    provider_status = models.CharField(max_length=40, blank=True)
    payment_method = models.CharField(max_length=40, blank=True)
    amount = models.PositiveIntegerField()
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CREATING)
    verification_status = models.CharField(
        max_length=12,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
    )
    ticket_issuance_status = models.CharField(
        max_length=24,
        choices=TicketIssuanceStatus.choices,
        default=TicketIssuanceStatus.PENDING,
    )
    ticket_issuance_failure = models.CharField(max_length=1000, blank=True)
    failure_message = models.CharField(max_length=500, blank=True)
    expires_at = models.DateTimeField()
    captured_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_attempt_count = models.PositiveSmallIntegerField(default=0)
    last_verification_attempt_at = models.DateTimeField(null=True, blank=True)
    next_verification_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=("intent", "status", "created_at")),
            models.Index(fields=("verification_status", "created_at")),
            models.Index(fields=("status", "created_at"), name="payment_status_created_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("intent",),
                condition=models.Q(
                    status="CAPTURED",
                    verification_status="VERIFIED",
                ),
                name="one_verified_capture_per_payment_intent",
            )
        ]


class PaymentVerificationAttempt(models.Model):
    class Trigger(models.TextChoices):
        CALLBACK = "CALLBACK", "PayU callback"
        CLIENT = "CLIENT", "Browser status check"
        ADMIN = "ADMIN", "Administrator retry"
        SCHEDULED = "SCHEDULED", "Scheduled reconciliation"

    class Outcome(models.TextChoices):
        STARTED = "STARTED", "Started"
        CAPTURED = "CAPTURED", "Captured"
        PENDING = "PENDING", "Pending"
        FAILED = "FAILED", "Failed"
        MISMATCH = "MISMATCH", "Transaction mismatch"
        AUTH_ERROR = "AUTH_ERROR", "Authentication error"
        INVALID_REQUEST = "INVALID_REQUEST", "Invalid API request"
        TRANSACTION_NOT_FOUND = "TRANSACTION_NOT_FOUND", "Transaction not found"
        API_ERROR = "API_ERROR", "API error"
        MALFORMED = "MALFORMED", "Malformed response"
        NETWORK_ERROR = "NETWORK_ERROR", "Network error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name="verification_attempts",
    )
    requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_verification_attempts",
    )
    trigger = models.CharField(max_length=12, choices=Trigger.choices)
    attempt_number = models.PositiveSmallIntegerField()
    environment = models.CharField(max_length=12)
    outcome = models.CharField(
        max_length=24,
        choices=Outcome.choices,
        default=Outcome.STARTED,
    )
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    api_status = models.CharField(max_length=24, blank=True)
    api_message = models.CharField(max_length=300, blank=True)
    response_schema_valid = models.BooleanField(null=True, blank=True)
    transaction_found = models.BooleanField(null=True, blank=True)
    returned_txnid = models.CharField(max_length=64, blank=True)
    returned_status = models.CharField(max_length=40, blank=True)
    returned_unmappedstatus = models.CharField(max_length=40, blank=True)
    returned_amount = models.CharField(max_length=40, blank=True)
    expected_amount = models.PositiveIntegerField()
    transaction_id_matches = models.BooleanField(null=True, blank=True)
    amount_matches = models.BooleanField(null=True, blank=True)
    booking_fields_match = models.BooleanField(null=True, blank=True)
    currency_matches = models.BooleanField(null=True, blank=True)
    retry_after = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("payment", "created_at"))]


class TicketDelivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENDING = "SENDING", "Sending"
        SENT = "SENT", "Sent"
        DELIVERED = "DELIVERED", "Delivered"
        FAILED = "FAILED", "Failed"
        RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED", "Reconciliation required"

    class Priority(models.TextChoices):
        STAFF = "STAFF", "Staff"
        COMPLIMENTARY = "COMPLIMENTARY", "Complimentary"
        REGULAR = "REGULAR", "Regular"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.OneToOneField(
        "tickets.Ticket",
        on_delete=models.PROTECT,
        related_name="email_delivery",
    )
    recipient = models.EmailField()
    priority = models.CharField(
        max_length=16,
        choices=Priority.choices,
        default=Priority.REGULAR,
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveIntegerField(default=0)
    failure_reason = models.CharField(max_length=500, blank=True)
    provider_message_id = models.CharField(max_length=120, unique=True, null=True, blank=True)
    pdf_content = models.BinaryField(null=True, blank=True)
    quota_date = models.DateField(null=True, blank=True)
    quota_reserved = models.BooleanField(default=False)
    claim_token = models.UUIDField(null=True, blank=True)
    retry_after = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=("status", "priority", "created_at")),
            models.Index(fields=("retry_after", "status")),
        ]


class EmailDailyUsage(models.Model):
    date = models.DateField(primary_key=True)
    regular_sent = models.PositiveSmallIntegerField(default=0)
    priority_sent = models.PositiveSmallIntegerField(default=0)
    regular_slots_used = models.PositiveSmallIntegerField(default=0)
    priority_slots_used = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(regular_slots_used__lte=295),
                name="email_daily_regular_quota_limit",
            ),
            models.CheckConstraint(
                condition=Q(priority_slots_used__lte=5),
                name="email_daily_priority_quota_limit",
            ),
            models.CheckConstraint(
                condition=Q(regular_sent__lte=F("regular_slots_used"))
                & Q(priority_sent__lte=F("priority_slots_used")),
                name="email_daily_sent_within_reserved",
            ),
        ]
