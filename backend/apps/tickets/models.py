import secrets
import uuid

from django.db import models


def create_ticket_token():
    return secrets.token_urlsafe(32)


class Ticket(models.Model):
    class Status(models.TextChoices):
        ISSUED = "ISSUED", "Issued"
        USED = "USED", "Used"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    registration = models.ForeignKey("registrations.Registration", on_delete=models.PROTECT, related_name="tickets")
    token = models.CharField(max_length=64, unique=True, default=create_ticket_token, editable=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ISSUED)
    issued_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [models.Index(fields=("registration", "status"))]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(status="ISSUED", used_at__isnull=True, cancelled_at__isnull=True)
                    | models.Q(status="USED", used_at__isnull=False, cancelled_at__isnull=True)
                    | models.Q(status="CANCELLED", used_at__isnull=True, cancelled_at__isnull=False)
                ),
                name="ticket_status_timestamp_consistent",
            ),
        ]

    def __str__(self):
        return f"Ticket {self.id}"
