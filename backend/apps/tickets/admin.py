from django.contrib import admin

from .models import Ticket


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("ticket_code", "registration", "status", "issued_at", "used_at", "cancelled_at")
    list_select_related = (
        "registration",
        "registration__event",
        "registration__ticket_tier",
        "registration__ticket_tier__event",
    )
    list_filter = ("status", "issued_at")
    search_fields = ("ticket_code", "id", "registration__registration_code", "registration__buyer_name", "registration__buyer_email")
    raw_id_fields = ("registration",)
    list_per_page = 25
    show_full_result_count = False
    ordering = ("-created_at",)
    readonly_fields = ("id", "ticket_code", "registration", "token", "status", "issued_at", "used_at", "cancelled_at", "created_at", "updated_at")
