from django.core.management.base import BaseCommand, CommandError

from apps.payments.proof import expire_payment_proof_reservations


class Command(BaseCommand):
    help = "Expire unpaid or rejection-correction reservations and release inventory."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=500,
            help="Maximum reservations to expire in this run.",
        )

    def handle(self, *args, **options):
        if options["limit"] < 1:
            raise CommandError("--limit must be at least one.")
        expired = expire_payment_proof_reservations(limit=options["limit"])
        self.stdout.write(
            self.style.SUCCESS(f"Payment-proof reservations expired: {expired}")
        )
