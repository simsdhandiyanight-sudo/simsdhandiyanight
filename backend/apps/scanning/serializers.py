from rest_framework import serializers

from .models import TicketScan


class ScanRequestSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=64, trim_whitespace=True)


class TicketScanSerializer(serializers.ModelSerializer):
    ticket_id = serializers.UUIDField(allow_null=True)
    event_id = serializers.UUIDField()
    event_name = serializers.CharField(source="event.name")
    attendee_name = serializers.SerializerMethodField()
    gate = serializers.CharField(source="gate.name")
    staff_name = serializers.CharField(source="scanned_by.name")

    class Meta:
        model = TicketScan
        fields = (
            "id",
            "ticket_id",
            "event_id",
            "event_name",
            "attendee_name",
            "result",
            "gate",
            "staff_name",
            "scanned_at",
        )

    def get_attendee_name(self, scan):
        if scan.ticket_id:
            return scan.ticket.registration.buyer_name
        return "Unknown"


class ScannedTicketSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    registration_id = serializers.UUIDField()
    event_id = serializers.UUIDField(source="registration.event_id")
    event_name = serializers.CharField(source="registration.event.name")
    buyer_name = serializers.CharField(source="registration.buyer_name")
    tier_name = serializers.CharField(source="registration.ticket_tier.name")
    source = serializers.CharField(source="registration.source")
    status = serializers.CharField()
    venue = serializers.CharField(source="registration.event.venue")
    event_date = serializers.SerializerMethodField()
    event_time = serializers.SerializerMethodField()
    issued_at = serializers.DateTimeField()
    used_at = serializers.DateTimeField(allow_null=True)
    cancelled_at = serializers.DateTimeField(allow_null=True)
    gate = serializers.SerializerMethodField()
    qr_token = serializers.SerializerMethodField()

    def get_event_date(self, ticket):
        from django.utils import timezone

        return timezone.localtime(ticket.registration.event.start_at).date().isoformat()

    def get_event_time(self, ticket):
        from django.utils import timezone

        event = ticket.registration.event
        start = timezone.localtime(event.start_at).strftime("%I:%M %p").lstrip("0")
        end = timezone.localtime(event.end_at).strftime("%I:%M %p").lstrip("0")
        return f"{start} – {end}"

    def get_gate(self, ticket):
        scan = next(
            (item for item in ticket.scan_history.all() if item.result == "ENTRY_GRANTED"),
            None,
        )
        return scan.gate.name if scan else None

    def get_qr_token(self, ticket):
        return ""
