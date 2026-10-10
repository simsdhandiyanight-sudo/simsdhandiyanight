import uuid

from django.db import models


class Gate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.PROTECT, related_name="gates")
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("event", "name"), name="unique_event_gate_name")]

    def __str__(self):
        return self.name


class StaffAssignment(models.Model):
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="gate_assignments")
    gate = models.ForeignKey(Gate, on_delete=models.CASCADE, related_name="assignments")
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("user", "gate"), name="unique_user_gate_assignment")]


class TicketScan(models.Model):
    class Result(models.TextChoices):
        ENTRY_GRANTED = "ENTRY_GRANTED", "Entry granted"
        ALREADY_USED = "ALREADY_USED", "Already used"
        INVALID_TICKET = "INVALID_TICKET", "Invalid ticket"
        CANCELLED = "CANCELLED", "Cancelled ticket"
        PAYMENT_NOT_VERIFIED = "PAYMENT_NOT_VERIFIED", "Payment not verified"
        WRONG_EVENT = "WRONG_EVENT", "Wrong event"
        EVENT_CLOSED = "EVENT_CLOSED", "Event closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        "tickets.Ticket",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="scan_history",
    )
    event = models.ForeignKey("events.Event", on_delete=models.PROTECT, related_name="scans")
    gate = models.ForeignKey(Gate, on_delete=models.PROTECT, related_name="scans")
    scanned_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="ticket_scans")
    result = models.CharField(max_length=20, choices=Result.choices)
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-scanned_at",)
        indexes = [
            models.Index(fields=("event", "scanned_at")),
            models.Index(fields=("ticket", "scanned_at")),
            models.Index(fields=("result", "scanned_at")),
            models.Index(fields=("-scanned_at",), name="scan_scanned_at_desc_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("ticket",),
                condition=models.Q(result="ENTRY_GRANTED"),
                name="ticket_has_at_most_one_granted_scan",
            )
        ]
