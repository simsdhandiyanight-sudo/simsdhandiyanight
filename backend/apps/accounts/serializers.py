from rest_framework import serializers

from apps.scanning.models import StaffAssignment
from .models import User


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class CurrentUserSerializer(serializers.ModelSerializer):
    assigned_gate = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "email", "name", "role", "assigned_gate")

    def get_assigned_gate(self, user):
        assignments = list(
            StaffAssignment.objects.filter(user=user, gate__is_active=True)
            .select_related("gate")
            .order_by("assigned_at")[:2]
        )
        return assignments[0].gate.name if len(assignments) == 1 else None
