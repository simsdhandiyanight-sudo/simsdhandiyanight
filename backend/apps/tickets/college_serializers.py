from rest_framework import serializers

from apps.events.models import Event

from .models import CollegeStudentTicket


class CollegeStudentTicketCreateSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    student_name = serializers.CharField(max_length=200, trim_whitespace=True)
    student_email = serializers.EmailField()

    def validate_event_id(self, value):
        if not Event.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Unknown event.")
        return value


class CollegeStudentTicketImportSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    file = serializers.FileField()
    dry_run = serializers.BooleanField(default=False)

    def validate_event_id(self, value):
        if not Event.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Unknown event.")
        return value

    def validate_file(self, value):
        if value.size > 2 * 1024 * 1024:
            raise serializers.ValidationError("CSV file must be no larger than 2 MB.")
        return value


class CollegeStudentTicketSerializer(serializers.ModelSerializer):
    event_id = serializers.UUIDField(read_only=True)
    email_delivery_enabled = serializers.SerializerMethodField()
    delivery_status = serializers.SerializerMethodField()

    class Meta:
        model = CollegeStudentTicket
        fields = (
            "id",
            "event_id",
            "student_name",
            "student_email",
            "ticket_code",
            "status",
            "email_delivery_enabled",
            "delivery_status",
            "issued_at",
            "created_at",
        )
        read_only_fields = fields

    def get_email_delivery_enabled(self, _ticket):
        return False

    def get_delivery_status(self, _ticket):
        return "DISABLED"
