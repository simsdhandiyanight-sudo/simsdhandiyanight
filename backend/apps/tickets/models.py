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
    ticket_code = models.CharField(max_length=40, unique=True)
    registration = models.ForeignKey("registrations.Registration", on_delete=models.PROTECT, related_name="tickets")
    attendee_name = models.CharField(max_length=200, blank=True, default="")
    token = models.CharField(max_length=64, unique=True, default=create_ticket_token, editable=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ISSUED)
    issued_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=("registration", "status")),
            models.Index(fields=("created_at",), name="ticket_created_at_idx"),
            models.Index(fields=("status", "created_at"), name="ticket_status_created_idx"),
        ]
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
        return f"Ticket {self.ticket_code}"


class CollegeStudentTicketSequence(models.Model):
    year = models.PositiveSmallIntegerField(primary_key=True)
    next_number = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"College ticket sequence {self.year}: {self.next_number}"


class CollegeStudentTicket(models.Model):
    class Status(models.TextChoices):
        ISSUED = "ISSUED", "Issued"
        USED = "USED", "Used"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(
        "events.Event",
        on_delete=models.PROTECT,
        related_name="college_student_tickets",
    )
    student_name = models.CharField(max_length=200)
    student_email = models.EmailField()
    ticket_code = models.CharField(max_length=48, unique=True, editable=False)
    token = models.CharField(max_length=64, unique=True, default=create_ticket_token, editable=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ISSUED)
    email_delivery_enabled = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_college_student_tickets",
    )
    issued_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=("event", "status")),
            models.Index(fields=("student_email", "created_at")),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("event", "student_email"),
                name="unique_college_student_email_per_event",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="ISSUED", used_at__isnull=True, cancelled_at__isnull=True)
                    | models.Q(status="USED", used_at__isnull=False, cancelled_at__isnull=True)
                    | models.Q(status="CANCELLED", used_at__isnull=True, cancelled_at__isnull=False)
                ),
                name="college_ticket_status_timestamp_consistent",
            ),
        ]

    def __str__(self):
        return f"College student ticket {self.ticket_code}"
