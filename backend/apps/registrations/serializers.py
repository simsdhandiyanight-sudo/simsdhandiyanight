from rest_framework import serializers
from django.utils import timezone


class BuyerSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    email = serializers.EmailField(max_length=254)
    phone = serializers.RegexField(r"^\+91[0-9]{10}$", max_length=16)
    organization = serializers.CharField(max_length=200, required=False, allow_blank=True)
    job_title = serializers.CharField(max_length=120, required=False, allow_blank=True)

    def validate_name(self, value):
        value = value.strip()
        if not value or not all(
            character.isalpha() or character in " '-\u2019"
            for character in value
        ):
            raise serializers.ValidationError(
                "Use letters, spaces, apostrophes, or hyphens only."
            )
        return value


class CreateRegistrationSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    ticket_tier_id = serializers.UUIDField()
    buyer = BuyerSerializer()
    attendee_names = serializers.ListField(
        child=serializers.CharField(max_length=200, trim_whitespace=True),
        required=False,
        allow_empty=False,
        max_length=10,
    )

    def validate_attendee_names(self, names):
        for name in names:
            if not name or not all(
                character.isalpha() or character in " '-\u2019"
                for character in name
            ):
                raise serializers.ValidationError(
                    "Use letters, spaces, apostrophes, or hyphens for attendee names."
                )
        return names


class RegistrationTicketSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    registration_id = serializers.UUIDField()
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
    qr_token = serializers.CharField(source="token")

    def get_attendee_name(self, ticket):
        return ticket.attendee_name or ticket.registration.buyer_name

    def get_event_date(self, ticket):
        return timezone.localtime(ticket.registration.event.start_at).date().isoformat()

    def get_event_time(self, ticket):
        event = ticket.registration.event
        start = timezone.localtime(event.start_at).strftime("%I:%M %p").lstrip("0")
        end = timezone.localtime(event.end_at).strftime("%I:%M %p").lstrip("0")
        return (
            f"{start} – {end}"
        )


class RegistrationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    event_id = serializers.UUIDField()
    event_name = serializers.CharField(source="event.name")
    buyer = serializers.SerializerMethodField()
    ticket_tier_id = serializers.UUIDField()
    ticket_tier_name = serializers.CharField(source="ticket_tier.name")
    source = serializers.CharField()
    created_at = serializers.DateTimeField()
    tickets = RegistrationTicketSerializer(many=True)

    def get_buyer(self, registration):
        return {
            "name": registration.buyer_name,
            "email": registration.buyer_email,
            "phone": registration.buyer_phone,
            "organization": registration.buyer_organization,
            "job_title": registration.buyer_job_title,
        }


class RegistrationListSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    event_id = serializers.UUIDField()
    event_name = serializers.CharField(source="event.name")
    buyer = serializers.SerializerMethodField()
    ticket_tier_id = serializers.UUIDField()
    ticket_tier_name = serializers.CharField(source="ticket_tier.name")
    source = serializers.CharField()
    created_at = serializers.DateTimeField()
    ticket_ids = serializers.SerializerMethodField()

    def get_buyer(self, registration):
        return {
            "name": registration.buyer_name,
            "email": registration.buyer_email,
            "phone": registration.buyer_phone,
            "organization": registration.buyer_organization,
            "job_title": registration.buyer_job_title,
        }

    def get_ticket_ids(self, registration):
        return list(registration.tickets.values_list("id", flat=True))
