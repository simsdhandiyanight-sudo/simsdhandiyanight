from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "resource_type", "resource_id", "actor", "created_at")
    list_select_related = ("actor",)
    list_filter = ("action", "resource_type", "created_at")
    raw_id_fields = ("actor",)
    list_per_page = 25
    show_full_result_count = False
    readonly_fields = ("id", "actor", "action", "resource_type", "resource_id", "metadata", "created_at")
