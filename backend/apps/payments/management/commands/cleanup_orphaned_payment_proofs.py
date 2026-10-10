from django.core.management.base import BaseCommand, CommandError

from apps.payments.cloudinary_storage import (
    PaymentProofStorageUnavailable,
    cleanup_orphaned_payment_proofs,
)


class Command(BaseCommand):
    help = "Delete unreferenced private payment proof assets older than the grace period."

    def add_arguments(self, parser):
        parser.add_argument("--grace-hours", type=int, default=168)

    def handle(self, *args, **options):
        grace_hours = options["grace_hours"]
        if grace_hours < 24:
            raise CommandError("--grace-hours must be at least 24.")
        try:
            deleted = cleanup_orphaned_payment_proofs(grace_hours=grace_hours)
        except PaymentProofStorageUnavailable as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} orphaned proof asset(s)."))
