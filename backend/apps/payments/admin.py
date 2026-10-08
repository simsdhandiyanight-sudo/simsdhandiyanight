from django.contrib import admin

from .models import EmailDailyUsage, Payment, PaymentIntent, TicketDelivery


@admin.register(PaymentIntent)
class PaymentIntentAdmin(admin.ModelAdmin):
    list_display = ("idempotency_key", "event", "ticket_tier", "status", "created_at")
    list_select_related = ("event", "ticket_tier", "ticket_tier__event", "registration")
    list_filter = ("status", "event", "created_at")
    search_fields = ("idempotency_key", "buyer_email", "buyer_name")
    raw_id_fields = ("registration",)
    list_per_page = 25
    show_full_result_count = False
    readonly_fields = (
        "idempotency_key",
        "request_hash",
        "event",
        "ticket_tier",
        "buyer_name",
        "buyer_email",
        "buyer_phone",
        "buyer_organization",
        "buyer_job_title",
        "attendee_names",
        "status",
        "registration",
        "expires_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "razorpay_order_id",
        "razorpay_payment_id",
        "amount",
        "currency",
        "status",
        "verification_status",
        "ticket_issuance_status",
    )
    list_select_related = ("intent", "intent__event", "intent__registration")
    list_filter = (
        "status",
        "verification_status",
        "ticket_issuance_status",
        "currency",
        "created_at",
    )
    search_fields = ("id", "razorpay_order_id", "razorpay_payment_id")
    raw_id_fields = ("intent",)
    list_per_page = 25
    show_full_result_count = False
    readonly_fields = (
        "id",
        "intent",
        "razorpay_order_id",
        "razorpay_payment_id",
        "amount",
        "currency",
        "status",
        "verification_status",
        "ticket_issuance_status",
        "ticket_issuance_failure",
        "failure_message",
        "expires_at",
        "captured_at",
        "verified_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TicketDelivery)
class TicketDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "ticket",
        "recipient",
        "priority",
        "status",
        "attempt_count",
        "provider_message_id",
        "created_at",
        "last_attempt_at",
        "updated_at",
    )
    list_select_related = ("ticket", "ticket__registration", "ticket__registration__event")
    list_filter = ("status", "priority", "created_at")
    search_fields = ("id", "ticket__id", "recipient", "provider_message_id")
    raw_id_fields = ("ticket",)
    list_per_page = 25
    show_full_result_count = False
    readonly_fields = (
        "id",
        "ticket",
        "recipient",
        "priority",
        "status",
        "provider_message_id",
        "attempt_count",
        "failure_reason",
        "pdf_size",
        "quota_date",
        "quota_reserved",
        "claim_token",
        "retry_after",
        "last_attempt_at",
        "sent_at",
        "delivered_at",
        "failed_at",
        "created_at",
        "updated_at",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).defer("pdf_content")

    @admin.display(description="PDF Content")
    def pdf_size(self, obj):
        if not obj or not obj.pdf_content:
            return "Not generated"
        return f"Generated ({len(obj.pdf_content) / 1024:.1f} KB)"


@admin.register(EmailDailyUsage)
class EmailDailyUsageAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "regular_sent",
        "regular_slots_used",
        "priority_sent",
        "priority_slots_used",
        "updated_at",
    )
    readonly_fields = (
        "date",
        "regular_sent",
        "regular_slots_used",
        "priority_sent",
        "priority_slots_used",
        "updated_at",
    )
    ordering = ("-date",)
    date_hierarchy = "date"
    list_per_page = 25
    show_full_result_count = False
    has_add_permission = lambda self, request: False
    has_delete_permission = lambda self, request, obj=None: False
