from django.contrib import admin

from .models import Registration


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "buyer_name", "buyer_email", "source", "created_at")
    list_select_related = ("event", "ticket_tier", "ticket_tier__event", "created_by")
    list_filter = ("event", "source", "created_at")
    search_fields = ("buyer_name", "buyer_email", "buyer_phone", "id")
    raw_id_fields = ("created_by", "ticket_tier")
    list_per_page = 25
    show_full_result_count = False
    readonly_fields = ("id", "created_at", "updated_at")
