from django.contrib import admin

from .models import Gate, StaffAssignment, TicketScan


@admin.register(Gate)
class GateAdmin(admin.ModelAdmin):
    list_display = ("name", "event", "is_active")
    list_select_related = ("event",)
    list_filter = ("event", "is_active")
    list_per_page = 25
    show_full_result_count = False


@admin.register(StaffAssignment)
class StaffAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "gate", "assigned_at")
    list_select_related = ("user", "gate", "gate__event")
    list_filter = ("gate__event",)
    raw_id_fields = ("user", "gate")
    list_per_page = 25
    show_full_result_count = False


@admin.register(TicketScan)
class TicketScanAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "gate", "scanned_by", "result", "scanned_at")
    list_select_related = ("event", "gate", "scanned_by", "ticket")
    list_filter = ("event", "gate", "result", "scanned_at")
    search_fields = ("id", "ticket__id", "scanned_by__email", "scanned_by__name")
    raw_id_fields = ("ticket", "scanned_by", "gate")
    list_per_page = 25
    show_full_result_count = False
    readonly_fields = ("id", "ticket", "event", "gate", "scanned_by", "result", "scanned_at")
