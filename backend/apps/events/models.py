import uuid

from django.core.validators import MinValueValidator
from django.db import models


class Event(models.Model):
    class Status(models.TextChoices):
        UPCOMING = "UPCOMING", "Upcoming"
        OPEN = "OPEN", "Open"
        SOLD_OUT = "SOLD_OUT", "Sold out"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=200)
    tagline = models.CharField(max_length=240, blank=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=40, default="music")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    venue = models.CharField(max_length=240)
    city = models.CharField(max_length=120)
    address = models.CharField(max_length=300)
    reporting_time = models.CharField(max_length=120, blank=True)
    location_url = models.URLField(max_length=500, blank=True)
    rules_and_regulations = models.JSONField(default=list, blank=True)
    instructions = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UPCOMING)
    registration_open = models.BooleanField(default=False)
    capacity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    highlights = models.JSONField(default=list, blank=True)
    schedule = models.JSONField(default=list, blank=True)
    faqs = models.JSONField(default=list, blank=True)
    accent_color = models.CharField(max_length=16, default="#b71959")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("start_at",)
        indexes = [models.Index(fields=("status", "registration_open"))]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_at__gt=models.F("start_at")),
                name="event_end_after_start",
            ),
            models.CheckConstraint(condition=models.Q(capacity__gt=0), name="event_capacity_positive"),
        ]

    def __str__(self):
        return self.name


class TicketTier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="tiers")
    slug = models.SlugField(max_length=80)
    name = models.CharField(max_length=160)
    price = models.DecimalField(max_digits=9, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default="INR")
    admission_count = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    description = models.CharField(max_length=300, blank=True)
    perks = models.JSONField(default=list, blank=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("price",)
        constraints = [
            models.UniqueConstraint(fields=("event", "slug"), name="unique_event_ticket_tier_slug"),
            models.CheckConstraint(condition=models.Q(admission_count__gt=0), name="tier_admissions_positive"),
            models.CheckConstraint(condition=models.Q(price__gte=0), name="tier_price_nonnegative"),
        ]

    def __str__(self):
        return f"{self.event.name}: {self.name}"
