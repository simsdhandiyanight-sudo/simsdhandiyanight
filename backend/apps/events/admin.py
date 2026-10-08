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
    list_per_page = 25
    show_full_result_count = False
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


@admin.register(TicketTier)
class TicketTierAdmin(admin.ModelAdmin):
    list_display = ("name", "event", "price", "currency", "admission_count", "is_available")
    list_select_related = ("event",)
    list_filter = ("event", "is_available")
    search_fields = ("name", "slug")
    list_per_page = 25
    show_full_result_count = False
