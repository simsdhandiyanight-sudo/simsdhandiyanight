from django.utils import timezone
from rest_framework import serializers

from .models import Event


def ordinal_day(day):
    suffix = "th" if 11 <= day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


class TicketTierPublicSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    price = serializers.DecimalField(max_digits=9, decimal_places=2, coerce_to_string=False)
    admissionCount = serializers.IntegerField(source="admission_count")
    description = serializers.CharField()
    perks = serializers.ListField(child=serializers.CharField())
    available = serializers.SerializerMethodField()

    def get_available(self, tier):
        event = tier.event
        remaining = max(
            0,
            event.capacity - self.context.get("active_ticket_count", 0),
        )
        return remaining // tier.admission_count if tier.is_available else 0


class PublicEventSerializer(serializers.ModelSerializer):
    date = serializers.SerializerMethodField()
    formattedDate = serializers.SerializerMethodField()
    time = serializers.SerializerMethodField()
    registeredCount = serializers.SerializerMethodField()
    checkedInCount = serializers.SerializerMethodField()
    tiers = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    accentColor = serializers.CharField(source="accent_color")

    class Meta:
        model = Event
        fields = (
            "id",
            "slug",
            "name",
            "tagline",
            "description",
            "category",
            "date",
            "formattedDate",
            "time",
            "venue",
            "city",
            "address",
            "reporting_time",
            "location_url",
            "rules_and_regulations",
            "instructions",
            "status",
            "capacity",
            "registeredCount",
            "checkedInCount",
            "tiers",
            "highlights",
            "schedule",
            "faqs",
            "accentColor",
        )

    def get_tiers(self, event):
        self.context["active_ticket_count"] = getattr(event, "active_ticket_count", 0)
        return TicketTierPublicSerializer(
            event.tiers.filter(is_available=True),
            many=True,
            context=self.context,
        ).data

    def get_date(self, event):
        return timezone.localtime(event.start_at).date().isoformat()

    def get_formattedDate(self, event):
        event_date = timezone.localtime(event.start_at).date()
        return f"{ordinal_day(event_date.day)} {event_date.strftime('%B %Y')}"

    def get_time(self, event):
        start = timezone.localtime(event.start_at).strftime("%I:%M %p").lstrip("0")
        end = timezone.localtime(event.end_at).strftime("%I:%M %p").lstrip("0")
        return f"{start} – {end}"

    def get_registeredCount(self, event):
        return getattr(event, "active_ticket_count", 0)

    def get_checkedInCount(self, event):
        return getattr(event, "used_ticket_count", 0)

    def get_status(self, event):
        if event.status == Event.Status.OPEN and not event.registration_open:
            return "upcoming"
        return event.status.lower()


class AdminEventSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(max_length=120)
    rules_and_regulations = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )
    instructions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )

    class Meta:
        model = Event
        fields = (
            "slug",
            "name",
            "tagline",
            "description",
            "category",
            "start_at",
            "end_at",
            "venue",
            "city",
            "address",
            "reporting_time",
            "location_url",
            "rules_and_regulations",
            "instructions",
            "status",
            "registration_open",
            "capacity",
            "highlights",
            "schedule",
            "faqs",
            "accent_color",
        )
