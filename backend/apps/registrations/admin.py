from django.contrib import admin

from .models import Registration


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "buyer_name", "buyer_email", "source", "created_at")
    list_filter = ("event", "source", "created_at")
    search_fields = ("buyer_name", "buyer_email", "buyer_phone", "id")
    readonly_fields = ("id", "created_at", "updated_at")
