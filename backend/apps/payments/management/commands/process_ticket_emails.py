import logging
import time

from django.core.management.base import BaseCommand, CommandError

from apps.payments.delivery import (
    BrevoConfigurationError,
    process_next_ticket_email,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Process pending individual ticket emails through Brevo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-emails",
            type=int,
            default=300,
            help="Maximum number of email attempts per pass.",
        )
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Keep polling the queue; useful as a supervised worker process.",
        )
        parser.add_argument(
            "--poll-seconds",
            type=float,
            default=10,
            help="Queue polling interval when --loop is enabled.",
        )

    def handle(self, *args, **options):
        if options["max_emails"] < 1:
            raise CommandError("--max-emails must be at least one.")
        if options["poll_seconds"] <= 0:
            raise CommandError("--poll-seconds must be greater than zero.")

        while True:
            processed = 0
            try:
                while processed < options["max_emails"]:
                    result = process_next_ticket_email()
                    if result is None:
                        break
                    processed += 1
            except BrevoConfigurationError as error:
                raise CommandError(str(error)) from error
            except Exception as error:
                logger.exception(
                    "Email worker pass failed; claimed sends will require reconciliation."
                )
                if not options["loop"]:
                    raise CommandError("The email worker pass failed.") from error

            self.stdout.write(
                self.style.SUCCESS(f"Email queue attempts processed: {processed}")
            )
            if not options["loop"]:
                break
            time.sleep(options["poll_seconds"])
