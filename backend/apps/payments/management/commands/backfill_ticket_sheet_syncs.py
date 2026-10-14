from django.core.management.base import BaseCommand

from apps.payments.sheets import backfill_ticket_sheet_syncs


class Command(BaseCommand):
    help = "Reconcile eligible database tickets against Google Sheets."

    def handle(self, *args, **options):
        ticket_count = backfill_ticket_sheet_syncs()
        self.stdout.write(
            self.style.SUCCESS(
                f"Queued reconciliation for {ticket_count} eligible online/on-spot tickets."
            )
        )
