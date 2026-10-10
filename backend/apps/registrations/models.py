import uuid

from django.db import models, transaction


class Registration(models.Model):
    class Source(models.TextChoices):
        ONLINE = "ONLINE", "Online"
        ON_SPOT = "ON_SPOT", "On-spot"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    registration_code = models.CharField(max_length=32, unique=True)
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
