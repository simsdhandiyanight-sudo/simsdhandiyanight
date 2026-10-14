from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .internal_views import HasN8nApiKey, N8nTokenAuthentication
from .models import TicketSheetSync
from .sheets import (
    MAX_SHEET_SYNC_ATTEMPTS,
    sheet_sync_data,
    sheet_sync_lease_expiry,
    sheet_sync_retry_time,
    ticket_sheet_sync_is_eligible,
)


class SheetJobAttemptSerializer(serializers.Serializer):
    attempt = serializers.IntegerField(min_value=1)


class SheetJobFailureSerializer(SheetJobAttemptSerializer):
    error_code = serializers.CharField(max_length=80, allow_blank=False)


class ClaimTicketEmailFromSheetView(APIView):
    permission_classes = [HasN8nApiKey]
    authentication_classes = [N8nTokenAuthentication]

    def post(self, request):
        return Response({"claimed": False, "reason": "Email delivery is disabled."})


class PendingTicketSheetJobsView(APIView):
    permission_classes = [HasN8nApiKey]
    authentication_classes = [N8nTokenAuthentication]

    def get(self, request):
        raw_limit = request.query_params.get("limit", "10")
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError) as error:
            raise ValidationError({"limit": "Provide an integer from 1 to 50."}) from error
        if not 1 <= limit <= 50:
            raise ValidationError({"limit": "Provide an integer from 1 to 50."})

        now = timezone.now()
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
                failure_reason="Previous Sheets upsert lease expired; safe upsert will retry.",
                updated_at=now,
            )
            candidates = (
                TicketSheetSync.objects.select_for_update(
                    skip_locked=True,
                    of=("self",),
                )
                .select_related(
                    "ticket__registration__event",
                    "college_ticket__event",
                )
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
                claimed.append(
                    {"job_id": str(sync.id), "attempt": sync.attempt_count}
                )
        return Response({"count": len(claimed), "jobs": claimed})


class TicketSheetJobDataView(APIView):
    permission_classes = [HasN8nApiKey]
    authentication_classes = [N8nTokenAuthentication]

    def get(self, request, job_id):
        serializer = serializers.IntegerField(min_value=1)
        attempt = serializer.run_validation(request.query_params.get("attempt"))
        with transaction.atomic():
            sync = get_object_or_404(
                TicketSheetSync.objects.select_for_update().select_related(
                    "ticket__registration__event",
                    "college_ticket__event",
                ),
                pk=job_id,
            )
            if (
                sync.status != TicketSheetSync.Status.PROCESSING
                or sync.attempt_count != attempt
                or sync.lease_expires_at is None
                or sync.lease_expires_at <= timezone.now()
            ):
                raise ValidationError({"status": "Sheet sync job is not owned by this attempt."})
            data = sheet_sync_data(sync)
            if data is None:
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
                return Response({"status": "FAILED"}, status=409)
        return Response(data)


class TicketSheetJobSyncedView(APIView):
    permission_classes = [HasN8nApiKey]
    authentication_classes = [N8nTokenAuthentication]

    def post(self, request, job_id):
        serializer = SheetJobAttemptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attempt = serializer.validated_data["attempt"]
        with transaction.atomic():
            sync = get_object_or_404(
                TicketSheetSync.objects.select_for_update(),
                pk=job_id,
            )
            if (
                sync.status == TicketSheetSync.Status.SYNCED
                and sync.attempt_count == attempt
            ):
                return Response({"success": True, "status": "SYNCED"})
            if (
                sync.status == TicketSheetSync.Status.PENDING
                and sync.attempt_count == attempt
            ):
                return Response({"success": True, "status": "PENDING"})
            if (
                sync.status != TicketSheetSync.Status.PROCESSING
                or sync.attempt_count != attempt
            ):
                raise ValidationError({"status": "Sheet sync job is not owned by this attempt."})
            now = timezone.now()
            if sync.resync_requested:
                sync.status = TicketSheetSync.Status.PENDING
                sync.retry_after = now
            else:
                sync.status = TicketSheetSync.Status.SYNCED
                sync.synced_at = now
                sync.retry_after = None
            sync.lease_expires_at = None
            sync.resync_requested = False
            sync.failure_reason = ""
            sync.failed_at = None
            sync.save(
                update_fields=(
                    "status",
                    "synced_at",
                    "retry_after",
                    "lease_expires_at",
                    "resync_requested",
                    "failure_reason",
                    "failed_at",
                    "updated_at",
                )
            )
        return Response({"success": True, "status": sync.status})


class TicketSheetJobFailedView(APIView):
    permission_classes = [HasN8nApiKey]
    authentication_classes = [N8nTokenAuthentication]

    def post(self, request, job_id):
        serializer = SheetJobFailureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            sync = get_object_or_404(
                TicketSheetSync.objects.select_for_update(),
                pk=job_id,
            )
            if (
                sync.status == TicketSheetSync.Status.FAILED
                and sync.attempt_count == data["attempt"]
            ):
                return Response({"success": True, "status": "FAILED"})
            if (
                sync.status != TicketSheetSync.Status.PROCESSING
                or sync.attempt_count != data["attempt"]
            ):
                raise ValidationError({"status": "Sheet sync job is not owned by this attempt."})
            now = timezone.now()
            sync.failure_reason = data["error_code"][:500]
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
        return Response({"success": True, "status": sync.status})
