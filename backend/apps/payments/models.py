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
    class Status(models.TextChoices):
        CREATING = "CREATING", "Creating order"
        CREATED = "CREATED", "Order created"
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
    razorpay_order_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
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
