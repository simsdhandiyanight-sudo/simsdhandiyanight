import uuid

from django.db import models


class Registration(models.Model):
    class Source(models.TextChoices):
        ONLINE = "ONLINE", "Online"
        ON_SPOT = "ON_SPOT", "On-spot"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.PROTECT, related_name="registrations")
    ticket_tier = models.ForeignKey("events.TicketTier", on_delete=models.PROTECT, related_name="registrations")
    buyer_name = models.CharField(max_length=200)
    buyer_email = models.EmailField()
    buyer_phone = models.CharField(max_length=16)
    buyer_organization = models.CharField(max_length=200, blank=True)
    buyer_job_title = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=8, choices=Source.choices)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_registrations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("event", "created_at")),
            models.Index(fields=("source", "created_at")),
        ]

    def __str__(self):
        return f"Registration {self.id}"


class RegistrationIdempotency(models.Model):
    key = models.UUIDField(primary_key=True, editable=False)
    request_hash = models.CharField(max_length=64)
    registration = models.OneToOneField(
        Registration,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="idempotency_record",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.key)
