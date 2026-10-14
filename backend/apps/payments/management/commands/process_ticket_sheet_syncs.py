import logging

import google.auth.exceptions
import requests
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.payments.google_sheets import (
    GoogleSheetsError,
    create_google_sheets_client,
)
from apps.payments.models import TicketSheetSync
from apps.payments.sheets import (
    MAX_SHEET_SYNC_ATTEMPTS,
    sheet_sync_data,
    sheet_sync_lease_expiry,
    sheet_sync_retry_time,
    ticket_sheet_sync_is_eligible,
)

logger = logging.getLogger(__name__)
MAX_JOBS_PER_RUN = 50


def _claim_sheet_jobs(limit, now):
    claimed = []
    with transaction.atomic():
        TicketSheetSync.objects.select_for_update(
            skip_locked=True,
            of=("self",),
        ).filter(
            status=TicketSheetSync.Status.PROCESSING,
            lease_expires_at__lte=now,
        ).update(
            status=TicketSheetSync.Status.PENDING,
            retry_after=now,
            lease_expires_at=None,
            resync_requested=False,
            failure_reason="Previous Sheets sync lease expired; retrying the safe upsert.",
            updated_at=now,
        )
        candidates = (
            TicketSheetSync.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(status=TicketSheetSync.Status.PENDING)
            .filter(Q(retry_after__isnull=True) | Q(retry_after__lte=now))
            .order_by("created_at", "id")
        )
        for sync in candidates:
            if len(claimed) >= limit:
                break
            if sync.attempt_count >= MAX_SHEET_SYNC_ATTEMPTS:
                sync.status = TicketSheetSync.Status.FAILED
                sync.failed_at = now
                sync.failure_reason = "Maximum Google Sheets sync attempts reached."
                sync.save(
                    update_fields=(
                        "status",
                        "failed_at",
                        "failure_reason",
                        "updated_at",
                    )
                )
                continue
            sync.status = TicketSheetSync.Status.PROCESSING
            sync.attempt_count += 1
            sync.last_attempt_at = now
            sync.lease_expires_at = sheet_sync_lease_expiry(now)
            sync.resync_requested = False
            sync.failure_reason = ""
            sync.failed_at = None
            sync.save(
                update_fields=(
                    "status",
                    "attempt_count",
                    "last_attempt_at",
                    "lease_expires_at",
                    "resync_requested",
                    "failure_reason",
                    "failed_at",
                    "updated_at",
                )
            )
            claimed.append((sync.id, sync.attempt_count))
    return claimed


def _mark_job_failed(job_id, attempt, error):
    now = timezone.now()
    with transaction.atomic():
        sync = TicketSheetSync.objects.select_for_update().get(pk=job_id)
        if (
            sync.status != TicketSheetSync.Status.PROCESSING
            or sync.attempt_count != attempt
        ):
            return False
        sync.failure_reason = f"GOOGLE_SHEETS_SYNC_FAILED ({type(error).__name__})"
        sync.lease_expires_at = None
        sync.resync_requested = False
        if sync.attempt_count >= MAX_SHEET_SYNC_ATTEMPTS:
            sync.status = TicketSheetSync.Status.FAILED
            sync.failed_at = now
            sync.retry_after = None
        else:
            sync.status = TicketSheetSync.Status.PENDING
            sync.failed_at = None
            sync.retry_after = sheet_sync_retry_time(sync.attempt_count, now)
        sync.save(
            update_fields=(
                "status",
                "failure_reason",
                "lease_expires_at",
                "resync_requested",
                "failed_at",
                "retry_after",
                "updated_at",
            )
        )
    return True


def _process_sheet_job(job_id, attempt, client):
    with transaction.atomic():
        sync = (
            TicketSheetSync.objects.select_for_update()
            .select_related(
                "ticket__registration__event",
                "ticket__registration__ticket_tier",
                "college_ticket__event",
            )
            .get(pk=job_id)
        )
        if (
            sync.status != TicketSheetSync.Status.PROCESSING
            or sync.attempt_count != attempt
            or not ticket_sheet_sync_is_eligible(sync)
        ):
            sync.status = TicketSheetSync.Status.FAILED
            sync.failed_at = timezone.now()
            sync.lease_expires_at = None
            sync.failure_reason = "Ticket is no longer eligible for sheet sync."
            sync.save(
                update_fields=(
                    "status",
                    "failed_at",
                    "lease_expires_at",
                    "failure_reason",
                    "updated_at",
                )
            )
            return "FAILED"
        data = sheet_sync_data(sync)

    if data is None:
        raise GoogleSheetsError("Ticket is no longer eligible for sheet sync.")

    client.upsert_ticket_row(data["sheet_name"], data["row"])

    now = timezone.now()
    with transaction.atomic():
        sync = TicketSheetSync.objects.select_for_update().get(pk=job_id)
        if (
            sync.status != TicketSheetSync.Status.PROCESSING
            or sync.attempt_count != attempt
        ):
            logger.warning(
                "Google Sheets row upsert completed for an expired job lease (%s).",
                job_id,
            )
            return "LEASE_EXPIRED"
        if sync.resync_requested:
            sync.status = TicketSheetSync.Status.PENDING
            sync.retry_after = now
        else:
            sync.status = TicketSheetSync.Status.SYNCED
            sync.synced_at = now
            sync.retry_after = None
        sync.attempt_count = 0
        sync.lease_expires_at = None
        sync.resync_requested = False
        sync.failure_reason = ""
        sync.failed_at = None
        sync.save(
            update_fields=(
                "status",
                "attempt_count",
                "synced_at",
                "retry_after",
                "lease_expires_at",
                "resync_requested",
                "failure_reason",
                "failed_at",
                "updated_at",
            )
        )
    return sync.status


class Command(BaseCommand):
    help = "Process durable, retryable Google Sheets ticket synchronization jobs."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=MAX_JOBS_PER_RUN)

    def handle(self, *args, **options):
        limit = options["limit"]
        if not 1 <= limit <= MAX_JOBS_PER_RUN:
            self.stderr.write("--limit must be between 1 and 50.")
            return
        jobs = _claim_sheet_jobs(limit, timezone.now())
        if not jobs:
            self.stdout.write("No eligible Google Sheets jobs are pending.")
            return
        client = None
        outcomes = {"SYNCED": 0, "PENDING": 0, "FAILED": 0, "LEASE_EXPIRED": 0}
        for job_id, attempt in jobs:
            try:
                if client is None:
                    client = create_google_sheets_client()
                outcome = _process_sheet_job(job_id, attempt, client)
            except (
                GoogleSheetsError,
                google.auth.exceptions.GoogleAuthError,
                requests.exceptions.RequestException,
            ) as error:
                logger.exception(
                    "Google Sheets sync failed for job %s, attempt %s.",
                    job_id,
                    attempt,
                )
                _mark_job_failed(job_id, attempt, error)
                outcome = "FAILED"
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
        self.stdout.write(
            "Processed Google Sheets jobs: "
            + ", ".join(f"{status}={count}" for status, count in outcomes.items())
        )
