from django.contrib import admin

from .models import CollegeStudentTicket, Ticket


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


@admin.register(CollegeStudentTicket)
class CollegeStudentTicketAdmin(admin.ModelAdmin):
    list_display = (
        "ticket_code",
        "student_name",
        "student_email",
        "event",
        "status",
        "email_delivery_enabled",
        "delivery_status",
        "created_at",
    )
    list_filter = ("event", "status", "email_delivery_enabled", "created_at")
    search_fields = ("student_name", "student_email", "ticket_code")
    list_select_related = ("event", "created_by", "email_delivery")
    readonly_fields = (
        "id",
        "ticket_code",
        "token",
        "status",
        "email_delivery_enabled",
        "used_at",
        "cancelled_at",
        "created_at",
        "updated_at",
    )
    fields = (
        "event",
        "student_name",
        "student_email",
        "email_delivery_enabled",
        "created_by",
        "id",
        "ticket_code",
        "token",
        "status",
        "used_at",
        "cancelled_at",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Email status")
    def delivery_status(self, ticket):
        delivery = getattr(ticket, "email_delivery", None)
        return delivery.get_status_display() if delivery else "Not queued"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
