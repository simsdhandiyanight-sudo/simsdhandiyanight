from django.contrib import admin
from django.contrib import messages
from django.db import transaction
import logging

from .models import (
    EmailDailyUsage,
    Payment,
    PaymentIntent,
    PaymentVerificationAttempt,
    TicketDelivery,
    TicketSheetSync,
)
from .sheets import ticket_sheet_sync_is_eligible
from apps.registrations.services import retry_on_spot_ticket_issuance

logger = logging.getLogger(__name__)

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


@admin.register(TicketSheetSync)
class TicketSheetSyncAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "ticket",
        "college_ticket",
        "status",
        "attempt_count",
        "retry_after",
        "last_attempt_at",
        "failure_reason",
        "synced_at",
        "failed_at",
    )
    list_select_related = (
        "ticket",
        "ticket__registration",
        "college_ticket",
    )
    list_filter = ("status", "created_at")
    search_fields = ("id", "ticket__ticket_code", "college_ticket__ticket_code")
    raw_id_fields = ("ticket", "college_ticket")
    list_per_page = 50
    show_full_result_count = False
    readonly_fields = tuple(field.name for field in TicketSheetSync._meta.fields)
    actions = ("retry_failed_syncs",)

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.role == "ADMIN"

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Retry selected eligible failed sheet syncs")
    def retry_failed_syncs(self, request, queryset):
        requeued = 0
        with transaction.atomic():
            for sync in queryset.select_for_update().filter(
                status=TicketSheetSync.Status.FAILED
            ):
                if not ticket_sheet_sync_is_eligible(sync):
                    continue
                sync.status = TicketSheetSync.Status.PENDING
                sync.attempt_count = 0
                sync.failure_reason = ""
                sync.retry_after = None
                sync.last_attempt_at = None
                sync.lease_expires_at = None
                sync.failed_at = None
                sync.save(
                    update_fields=(
                        "status",
                        "attempt_count",
                        "failure_reason",
                        "retry_after",
                        "last_attempt_at",
                        "lease_expires_at",
                        "failed_at",
                        "updated_at",
                    )
                )
                requeued += 1
        self.message_user(
            request,
            f"Requeued {requeued} eligible sheet sync job(s).",
            messages.SUCCESS,
        )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "provider",
        "provider_order_id",
        "provider_payment_id",
        "amount",
        "currency",
        "status",
        "verification_status",
        "ticket_issuance_status",
    )
    list_select_related = ("intent", "intent__event", "intent__registration")
    list_filter = (
        "provider",
        "status",
        "verification_status",
        "ticket_issuance_status",
        "currency",
        "created_at",
    )
    search_fields = ("id", "provider_order_id", "provider_payment_id")
    raw_id_fields = ("intent",)
    list_per_page = 25
    show_full_result_count = False
    readonly_fields = (
        "id",
        "intent",
        "provider",
        "provider_order_id",
        "provider_payment_id",
        "provider_status",
        "payment_method",
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
        "verification_attempt_count",
        "last_verification_attempt_at",
        "next_verification_at",
        "created_at",
        "updated_at",
    )
    actions = ("retry_on_spot_ticket_issuance_action",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Retry selected verified on-spot ticket issuance")
    def retry_on_spot_ticket_issuance_action(self, request, queryset):
        retried = 0
        failed = 0
        for payment in queryset.filter(
            provider=Payment.Provider.ON_SPOT,
            status=Payment.Status.VERIFIED,
            ticket_issuance_status=Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED,
        ):
            try:
                retry_on_spot_ticket_issuance(
                    payment_id=payment.pk,
                    administrator=request.user,
                )
            except Exception:
                logger.exception(
                    "Admin retry failed for on-spot payment %s.",
                    payment.pk,
                )
                failed += 1
            else:
                retried += 1
        if retried:
            self.message_user(
                request,
                f"Successfully retried ticket issuance for {retried} payment(s).",
                messages.SUCCESS,
            )
        if failed:
            self.message_user(
                request,
                f"Ticket issuance retry failed for {failed} payment(s); see server logs.",
                messages.ERROR,
            )


@admin.register(PaymentVerificationAttempt)
class PaymentVerificationAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "payment",
        "attempt_number",
        "trigger",
        "environment",
        "outcome",
        "http_status",
        "api_status",
        "created_at",
    )
    list_filter = ("trigger", "environment", "outcome", "created_at")
    search_fields = ("payment__provider_order_id", "returned_txnid")
    readonly_fields = tuple(field.name for field in PaymentVerificationAttempt._meta.fields)
    list_select_related = ("payment",)
    list_per_page = 50
    show_full_result_count = False

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TicketDelivery)
class TicketDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "ticket",
        "college_ticket",
        "recipient",
        "priority",
        "status",
        "attempt_count",
        "provider_message_id",
        "created_at",
        "last_attempt_at",
        "updated_at",
    )
    list_select_related = (
        "ticket",
        "ticket__registration",
        "ticket__registration__event",
        "college_ticket",
    )
    list_filter = ("status", "priority", "created_at")
    search_fields = (
        "id",
        "ticket__id",
        "ticket__ticket_code",
        "college_ticket__ticket_code",
        "college_ticket__student_name",
        "recipient",
        "provider_message_id",
    )
    raw_id_fields = ("ticket", "college_ticket")
    list_per_page = 25
    show_full_result_count = False
    readonly_fields = (
        "id",
        "ticket",
        "college_ticket",
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

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

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
