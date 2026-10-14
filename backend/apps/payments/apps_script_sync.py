import logging
import re
import time
from uuid import UUID
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.payments.models import TicketSheetSync

from .sheets import (
    MAX_SHEET_SYNC_ATTEMPTS,
    sheet_sync_data,
    sheet_sync_lease_expiry,
    ticket_sheet_sync_is_eligible,
)

logger = logging.getLogger(__name__)
MAX_WEBHOOK_ATTEMPTS = 3
WEBHOOK_TIMEOUT = (3.05, 6)
SAFE_ERROR_CODE = re.compile(r"^[A-Z0-9_]{1,48}$")


class AppsScriptSyncError(RuntimeError):
    def __init__(self, category, *, retryable=False):
        super().__init__(category)
        self.category = category
        self.retryable = retryable


def _mark_unconfigured(sync_ids):
    with transaction.atomic():
        TicketSheetSync.objects.filter(
            pk__in=sync_ids,
            status=TicketSheetSync.Status.PENDING,
        ).update(
            failure_reason="APPS_SCRIPT_NOT_CONFIGURED",
            updated_at=timezone.now(),
        )
    logger.error(
        "Apps Script ticket sync is not configured for jobs %s.",
        ", ".join(str(sync_id) for sync_id in sync_ids),
    )


def _claim_jobs(sync_ids):
    claimed = []
    now = timezone.now()
    with transaction.atomic():
        stale_jobs = TicketSheetSync.objects.select_for_update().filter(
            pk__in=sync_ids,
            status=TicketSheetSync.Status.PROCESSING,
            lease_expires_at__lte=now,
        )
        stale_jobs.update(
            status=TicketSheetSync.Status.PENDING,
            lease_expires_at=None,
            retry_after=now,
            failure_reason="Previous Apps Script sync lease expired; retrying the safe upsert.",
            updated_at=now,
        )
        jobs = (
            TicketSheetSync.objects.select_for_update(of=("self",))
            .select_related(
                "ticket__registration__event",
                "ticket__registration__ticket_tier",
                "college_ticket__event",
            )
            .filter(
                pk__in=sync_ids,
                status=TicketSheetSync.Status.PENDING,
            )
            .filter(Q(retry_after__isnull=True) | Q(retry_after__lte=now))
            .order_by("created_at", "id")
        )
        for sync in jobs:
            if sync.attempt_count >= MAX_SHEET_SYNC_ATTEMPTS:
                sync.status = TicketSheetSync.Status.FAILED
                sync.failed_at = now
                sync.failure_reason = "Maximum Apps Script sync attempts reached."
                sync.save(
                    update_fields=(
                        "status",
                        "failed_at",
                        "failure_reason",
                        "updated_at",
                    )
                )
                continue
            if not ticket_sheet_sync_is_eligible(sync):
                sync.status = TicketSheetSync.Status.FAILED
                sync.failed_at = now
                sync.failure_reason = "Ticket is no longer eligible for sheet sync."
                sync.save(
                    update_fields=(
                        "status",
                        "failed_at",
                        "failure_reason",
                        "updated_at",
                    )
                )
                continue
            data = sheet_sync_data(sync)
            if data is None:
                sync.status = TicketSheetSync.Status.FAILED
                sync.failed_at = now
                sync.failure_reason = "Ticket is no longer eligible for sheet sync."
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
            sync.lease_expires_at = sheet_sync_lease_expiry(now)
            sync.resync_requested = False
            sync.failure_reason = ""
            sync.failed_at = None
            sync.save(
                update_fields=(
                    "status",
                    "lease_expires_at",
                    "resync_requested",
                    "failure_reason",
                    "failed_at",
                    "updated_at",
                )
            )
            claimed.append((sync.id, data))
    return claimed


def _record_attempt(sync_ids):
    now = timezone.now()
    permitted = []
    with transaction.atomic():
        jobs = TicketSheetSync.objects.select_for_update().filter(
            pk__in=sync_ids,
            status=TicketSheetSync.Status.PROCESSING,
        )
        for sync in jobs:
            if sync.attempt_count >= MAX_SHEET_SYNC_ATTEMPTS:
                sync.status = TicketSheetSync.Status.FAILED
                sync.failed_at = now
                sync.lease_expires_at = None
                sync.failure_reason = "Maximum Apps Script sync attempts reached."
                sync.save(
                    update_fields=(
                        "status",
                        "failed_at",
                        "lease_expires_at",
                        "failure_reason",
                        "updated_at",
                    )
                )
                continue
            sync.attempt_count += 1
            sync.last_attempt_at = now
            sync.lease_expires_at = sheet_sync_lease_expiry(now)
            sync.save(
                update_fields=(
                    "attempt_count",
                    "last_attempt_at",
                    "lease_expires_at",
                    "updated_at",
                )
            )
            permitted.append(sync.id)
    return permitted


def _finish_jobs(sync_ids, *, error=None):
    now = timezone.now()
    resync_ids = []
    with transaction.atomic():
        jobs = TicketSheetSync.objects.select_for_update().filter(
            pk__in=sync_ids,
            status=TicketSheetSync.Status.PROCESSING,
        )
        for sync in jobs:
            sync.lease_expires_at = None
            if error is None and not sync.resync_requested:
                sync.status = TicketSheetSync.Status.SYNCED
                sync.synced_at = now
                sync.retry_after = None
                sync.attempt_count = 0
                sync.failure_reason = ""
                sync.failed_at = None
            elif error is None:
                sync.status = TicketSheetSync.Status.PENDING
                sync.retry_after = now
                sync.resync_requested = False
                resync_ids.append(sync.id)
            else:
                sync.status = TicketSheetSync.Status.FAILED
                sync.failed_at = now
                sync.retry_after = None
                sync.resync_requested = False
                sync.failure_reason = (
                    f"APPS_SCRIPT_SYNC_FAILED ({error.category})"
                )
            sync.save(
                update_fields=(
                    "status",
                    "synced_at",
                    "attempt_count",
                    "failure_reason",
                    "failed_at",
                    "retry_after",
                    "lease_expires_at",
                    "resync_requested",
                    "updated_at",
                )
            )
    if resync_ids:
        _schedule_dispatch(resync_ids)


def _post_ticket_rows(rows, expected_ids):
    last_error = None
    for attempt in range(1, MAX_WEBHOOK_ATTEMPTS + 1):
        allowed_ids = _record_attempt(expected_ids)
        if not allowed_ids:
            return
        allowed = set(allowed_ids)
        batch = [
            {"sheet_name": row["sheet_name"], "row": row["row"]}
            for row in rows
            if UUID(row["job_id"]) in allowed
        ]
        try:
            response = requests.post(
                settings.GOOGLE_APPS_SCRIPT_WEBHOOK_URL,
                json={
                    "secret": settings.GOOGLE_APPS_SCRIPT_WEBHOOK_SECRET,
                    "tickets": batch,
                },
                timeout=WEBHOOK_TIMEOUT,
            )
            try:
                response.raise_for_status()
            except requests.HTTPError as error:
                status = response.status_code
                raise AppsScriptSyncError(
                    f"HTTP_{status}",
                    retryable=status == 429 or status >= 500,
                ) from error
            try:
                result = response.json()
            except (ValueError, requests.exceptions.JSONDecodeError) as error:
                raise AppsScriptSyncError("INVALID_RESPONSE") from error
            if not isinstance(result, dict):
                raise AppsScriptSyncError("INVALID_RESPONSE")
            processed = result.get("processed_ticket_ids")
            expected = [row["row"]["ticket_id"] for row in batch]
            if (
                result.get("success") is not True
                or not isinstance(processed, list)
                or not all(isinstance(item, str) for item in processed)
                or len(processed) != len(expected)
                or set(processed) != set(expected)
            ):
                code = result.get("error_code")
                category = (
                    code
                    if isinstance(code, str) and SAFE_ERROR_CODE.fullmatch(code)
                    else "APPLICATION_ERROR"
                )
                raise AppsScriptSyncError(
                    category,
                    retryable=result.get("retryable") is True,
                )
            _finish_jobs(allowed_ids)
            return
        except AppsScriptSyncError as error:
            last_error = error
        except requests.exceptions.RequestException as error:
            last_error = AppsScriptSyncError(
                type(error).__name__.upper(),
                retryable=True,
            )
        if (
            last_error is None
            or not last_error.retryable
            or attempt == MAX_WEBHOOK_ATTEMPTS
        ):
            _finish_jobs(allowed_ids, error=last_error)
            logger.error(
                "Apps Script sync failed for jobs %s (%s).",
                ", ".join(str(sync_id) for sync_id in allowed_ids),
                last_error.category,
            )
            return
        time.sleep(0.25 * (2 ** (attempt - 1)))


def _schedule_dispatch(sync_ids):
    normalized_ids = tuple(UUID(str(sync_id)) for sync_id in sync_ids)
    if not normalized_ids:
        return
    transaction.on_commit(
        lambda: dispatch_ticket_sheet_syncs(normalized_ids),
        robust=True,
    )


def dispatch_ticket_sheet_syncs(sync_ids):
    normalized_ids = tuple(dict.fromkeys(UUID(str(sync_id)) for sync_id in sync_ids))
    if not normalized_ids:
        return
    webhook_url = urlparse(settings.GOOGLE_APPS_SCRIPT_WEBHOOK_URL)
    if (
        webhook_url.scheme != "https"
        or webhook_url.hostname != "script.google.com"
        or not webhook_url.path.endswith("/exec")
        or not settings.GOOGLE_APPS_SCRIPT_WEBHOOK_SECRET
    ):
        _mark_unconfigured(normalized_ids)
        return
    claimed = _claim_jobs(normalized_ids)
    if not claimed:
        return
    _post_ticket_rows(
        [data for _, data in claimed],
        [sync_id for sync_id, _ in claimed],
    )


def schedule_ticket_sheet_syncs(sync_ids):
    _schedule_dispatch(sync_ids)
