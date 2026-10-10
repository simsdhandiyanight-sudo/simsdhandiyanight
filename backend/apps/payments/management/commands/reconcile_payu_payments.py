from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from apps.payments.models import Payment
from apps.payments.services import (
    PAYU_MAX_AUTOMATIC_VERIFICATION_ATTEMPTS,
    PaymentReviewRequired,
    refresh_payu_payment_status,
)


class Command(BaseCommand):
    help = "Run one bounded pass of due PayU payment verifications."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1:
            raise CommandError("--limit must be at least one.")

        now = timezone.now()
        unresolved = Q(
            verification_status__in=(
                Payment.VerificationStatus.PENDING,
                Payment.VerificationStatus.FAILED,
            ),
            status__in=(
                Payment.Status.CREATED,
                Payment.Status.PENDING,
                Payment.Status.CAPTURED,
            ),
            verification_attempt_count__lt=PAYU_MAX_AUTOMATIC_VERIFICATION_ATTEMPTS,
        )
        interrupted_ticket_issuance = Q(
            verification_status=Payment.VerificationStatus.VERIFIED,
            ticket_issuance_status=Payment.TicketIssuanceStatus.PENDING,
        )
        due_payments = (
            Payment.objects.filter(provider=Payment.Provider.PAYU)
            .filter(unresolved | interrupted_ticket_issuance)
            .filter(Q(next_verification_at__isnull=True) | Q(next_verification_at__lte=now))
            .order_by("next_verification_at", "created_at")
            .values_list("id", flat=True)[:limit]
        )

        processed = 0
        for payment_id in due_payments:
            payment = Payment.objects.only("provider_order_id").get(pk=payment_id)
            try:
                refresh_payu_payment_status(
                    payment.provider_order_id,
                    trigger="SCHEDULED",
                )
            except PaymentReviewRequired:
                self.stderr.write(
                    f"Payment {payment_id} remains unresolved and requires administrator review."
                )
            processed += 1

        self.stdout.write(self.style.SUCCESS(f"PayU reconciliation attempts: {processed}"))
