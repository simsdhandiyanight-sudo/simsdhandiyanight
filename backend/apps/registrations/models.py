import uuid

from django.db import models, transaction


class Registration(models.Model):
    class Source(models.TextChoices):
        ONLINE = "ONLINE", "Online"
        ON_SPOT = "ON_SPOT", "On-spot"

    class Status(models.TextChoices):
        REGISTERED = "REGISTERED", "Registered"
        PENDING_VERIFICATION = "PENDING_VERIFICATION", "Payment pending verification"
        REJECTED = "REJECTED", "Payment proof rejected"
        PAYMENT_VERIFIED = "PAYMENT_VERIFIED", "Payment verified"
        TICKET_ISSUED = "TICKET_ISSUED", "Ticket issued"
        EXPIRED = "EXPIRED", "Reservation expired"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    registration_code = models.CharField(max_length=32, unique=True)
    ticket_id = models.CharField(max_length=48, unique=True, null=True, blank=True)
    event = models.ForeignKey("events.Event", on_delete=models.PROTECT, related_name="registrations")
    ticket_tier = models.ForeignKey("events.TicketTier", on_delete=models.PROTECT, related_name="registrations")
    buyer_name = models.CharField(max_length=200)
    buyer_email = models.EmailField()
    buyer_phone = models.CharField(max_length=16)
    buyer_organization = models.CharField(max_length=200, blank=True)
    buyer_job_title = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=8, choices=Source.choices)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.TICKET_ISSUED,
    )
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
            models.Index(fields=("-created_at",), name="reg_created_at_desc_idx"),
            models.Index(fields=("buyer_email",), name="reg_buyer_email_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self.registration_code:
            registration_year = self.event.start_at.year
            with transaction.atomic():
                RegistrationSequence.objects.get_or_create(year=registration_year)
                sequence = RegistrationSequence.objects.select_for_update().get(
                    year=registration_year
                )
                self.registration_code = (
                    f"SIMS-DN-{registration_year}-{sequence.next_number:05d}"
                )
                sequence.next_number += 1
                sequence.save(update_fields=("next_number",))
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Registration {self.registration_code}"


class RegistrationSequence(models.Model):
    year = models.PositiveSmallIntegerField(primary_key=True)
    next_number = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"Registration sequence {self.year}: {self.next_number}"


class TicketIdSequence(models.Model):
    year = models.PositiveSmallIntegerField(primary_key=True)
    next_number = models.PositiveIntegerField(default=1)

    @classmethod
    def next_ticket_id(cls, year):
        cls.objects.get_or_create(year=year)
        sequence = cls.objects.select_for_update().get(year=year)
        ticket_id = f"SIMS-DN-{year}{sequence.next_number:04d}"
        sequence.next_number += 1
        sequence.save(update_fields=("next_number",))
        return ticket_id

    def __str__(self):
        return f"Ticket ID sequence {self.year}: {self.next_number}"


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


class InventoryReservation(models.Model):
    class Status(models.TextChoices):
        RESERVED = "RESERVED", "Reserved"
        CONSUMED = "CONSUMED", "Consumed"
        RELEASED = "RELEASED", "Released"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    registration = models.OneToOneField(
        Registration,
        on_delete=models.PROTECT,
        related_name="inventory_reservation",
    )
    event = models.ForeignKey(
        "events.Event",
        on_delete=models.PROTECT,
        related_name="inventory_reservations",
    )
    units_reserved = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.RESERVED,
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=("event", "status", "expires_at")),
        ]
