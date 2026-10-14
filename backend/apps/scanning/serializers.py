from rest_framework import serializers

from .models import TicketScan


class ScanRequestSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=64, trim_whitespace=True)


class TicketScanSerializer(serializers.ModelSerializer):
    ticket_id = serializers.UUIDField(allow_null=True)
    college_ticket_id = serializers.UUIDField(allow_null=True)
    ticket_source = serializers.SerializerMethodField()
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
            "college_ticket_id",
            "ticket_source",
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
            return scan.ticket.attendee_name or scan.ticket.registration.buyer_name
        if scan.college_ticket_id:
            return scan.college_ticket.student_name
        return "Unknown"

    def get_ticket_source(self, scan):
        if scan.college_ticket_id:
            return "COLLEGE_STUDENT"
        if scan.ticket_id:
            return scan.ticket.registration.source
        return None


class ScannedCollegeStudentTicketSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    ticket_code = serializers.CharField()
    registration_id = serializers.UUIDField(allow_null=True, default=None)
    registration_code = serializers.CharField(allow_null=True, default=None)
    event_id = serializers.UUIDField()
    event_name = serializers.CharField(source="event.name")
    buyer_name = serializers.CharField(source="student_name")
    attendee_name = serializers.CharField(source="student_name")
    tier_name = serializers.SerializerMethodField()
    source = serializers.SerializerMethodField()
    status = serializers.CharField()
    venue = serializers.CharField(source="event.venue")
    event_date = serializers.SerializerMethodField()
    event_time = serializers.SerializerMethodField()
    issued_at = serializers.DateTimeField()
    used_at = serializers.DateTimeField(allow_null=True)
    cancelled_at = serializers.DateTimeField(allow_null=True)
    gate = serializers.SerializerMethodField()
    qr_token = serializers.SerializerMethodField()

    def get_tier_name(self, ticket):
        return "College Student"

    def get_source(self, ticket):
        return "COLLEGE_STUDENT"

    def get_event_date(self, ticket):
        from django.utils import timezone

        return timezone.localtime(ticket.event.start_at).date().isoformat()

    def get_event_time(self, ticket):
        from django.utils import timezone

        event = ticket.event
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


class ScannedTicketSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    ticket_code = serializers.CharField()
    registration_id = serializers.UUIDField()
    registration_code = serializers.CharField(source="registration.registration_code")
    event_id = serializers.UUIDField(source="registration.event_id")
    event_name = serializers.CharField(source="registration.event.name")
    buyer_name = serializers.CharField(source="registration.buyer_name")
    attendee_name = serializers.SerializerMethodField()
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

    def get_attendee_name(self, ticket):
        return ticket.attendee_name or ticket.registration.buyer_name

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
