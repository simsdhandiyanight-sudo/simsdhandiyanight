from django.contrib import admin

from .models import Gate, StaffAssignment, TicketScan


@admin.register(Gate)
class GateAdmin(admin.ModelAdmin):
    list_display = ("name", "event", "is_active")
    list_filter = ("event", "is_active")


@admin.register(StaffAssignment)
class StaffAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "gate", "assigned_at")
    list_filter = ("gate__event",)


@admin.register(TicketScan)
class TicketScanAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "gate", "scanned_by", "result", "scanned_at")
    list_filter = ("event", "gate", "result", "scanned_at")
    readonly_fields = ("id", "ticket", "event", "gate", "scanned_by", "result", "scanned_at")
