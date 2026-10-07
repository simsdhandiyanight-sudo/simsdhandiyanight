from django.contrib import admin

from .models import Ticket


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "registration", "status", "issued_at", "used_at", "cancelled_at")
    list_filter = ("status", "issued_at")
    search_fields = ("id", "registration__buyer_name", "registration__buyer_email")
    readonly_fields = ("id", "registration", "token", "status", "issued_at", "used_at", "cancelled_at", "created_at", "updated_at")
