from django.urls import path

from .internal_views import (
    PendingEmailJobsView,
)
from .sheet_views import (
    ClaimTicketEmailFromSheetView,
    PendingTicketSheetJobsView,
    TicketSheetJobDataView,
    TicketSheetJobFailedView,
    TicketSheetJobSyncedView,
)

urlpatterns = [
    path("email-jobs/pending", PendingEmailJobsView.as_view(), name="n8n-email-jobs-pending"),
    path(
        "email-jobs/claim-from-sheet",
        ClaimTicketEmailFromSheetView.as_view(),
        name="n8n-email-job-claim-from-sheet",
    ),
    path(
        "sheet-jobs/pending",
        PendingTicketSheetJobsView.as_view(),
        name="n8n-sheet-jobs-pending",
    ),
    path(
        "sheet-jobs/<uuid:job_id>/data",
        TicketSheetJobDataView.as_view(),
        name="n8n-sheet-job-data",
    ),
    path(
        "sheet-jobs/<uuid:job_id>/synced",
        TicketSheetJobSyncedView.as_view(),
        name="n8n-sheet-job-synced",
    ),
    path(
        "sheet-jobs/<uuid:job_id>/failed",
        TicketSheetJobFailedView.as_view(),
        name="n8n-sheet-job-failed",
    ),
]
