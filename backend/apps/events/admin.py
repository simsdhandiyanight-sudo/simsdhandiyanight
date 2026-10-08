from django.contrib import admin

from .models import Event, TicketTier


class TicketTierInline(admin.TabularInline):
    model = TicketTier
    extra = 0


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "status", "registration_open", "capacity", "start_at")
    list_filter = ("status", "registration_open")
    search_fields = ("name", "slug")
    inlines = (TicketTierInline,)
    fields = (
        "slug",
        "name",
        "tagline",
        "description",
        "category",
        "start_at",
        "end_at",
        "reporting_time",
        "venue",
        "city",
        "address",
        "location_url",
        "rules_and_regulations",
        "instructions",
        "status",
        "registration_open",
        "capacity",
        "highlights",
        "schedule",
        "faqs",
        "accent_color",
    )
