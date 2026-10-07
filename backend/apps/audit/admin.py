from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "resource_type", "resource_id", "actor", "created_at")
    list_filter = ("action", "resource_type", "created_at")
    readonly_fields = ("id", "actor", "action", "resource_type", "resource_id", "metadata", "created_at")
