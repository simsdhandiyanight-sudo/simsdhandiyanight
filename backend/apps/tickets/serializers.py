from django.utils import timezone
from rest_framework import serializers

from .models import Ticket


class TicketSerializer(serializers.ModelSerializer):
    registration_id = serializers.UUIDField()
    event_id = serializers.UUIDField(source="registration.event_id")
    event_name = serializers.CharField(source="registration.event.name")
    buyer_name = serializers.CharField(source="registration.buyer_name")
    attendee_name = serializers.SerializerMethodField()
    tier_name = serializers.CharField(source="registration.ticket_tier.name")
    source = serializers.CharField(source="registration.source")
    venue = serializers.CharField(source="registration.event.venue")
    event_date = serializers.SerializerMethodField()
    event_time = serializers.SerializerMethodField()
    qr_token = serializers.CharField(source="token")
    gate = serializers.SerializerMethodField()
    attendee_email = serializers.SerializerMethodField()
    attendee_phone = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = (
            "id",
            "registration_id",
            "event_id",
            "event_name",
            "buyer_name",
            "attendee_name",
            "attendee_email",
            "attendee_phone",
            "tier_name",
            "source",
            "status",
            "venue",
            "event_date",
            "event_time",
            "issued_at",
            "used_at",
            "cancelled_at",
            "gate",
            "qr_token",
        )

    def get_event_date(self, ticket):
        return timezone.localtime(ticket.registration.event.start_at).date().isoformat()

    def get_attendee_name(self, ticket):
        return ticket.attendee_name or ticket.registration.buyer_name

    def get_event_time(self, ticket):
        event = ticket.registration.event
        start = timezone.localtime(event.start_at).strftime("%I:%M %p").lstrip("0")
        end = timezone.localtime(event.end_at).strftime("%I:%M %p").lstrip("0")
        return f"{start} – {end}"

    def get_gate(self, ticket):
        scan = next(
            (
                item
                for item in ticket.scan_history.all()
                if item.result == "ENTRY_GRANTED"
            ),
            None,
        )
        return scan.gate.name if scan else None

    def get_attendee_email(self, ticket):
        request = self.context.get("request")
        if request and request.user.is_authenticated and request.user.role in ("ADMIN", "REGISTRATION_STAFF"):
            return ticket.registration.buyer_email
        return None

    def get_attendee_phone(self, ticket):
        request = self.context.get("request")
        if request and request.user.is_authenticated and request.user.role in ("ADMIN", "REGISTRATION_STAFF"):
            return ticket.registration.buyer_phone
        return None
