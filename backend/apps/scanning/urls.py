from django.urls import path

from .views import (
    DashboardSummaryView,
    ManifestExportView,
    ReportsView,
    ScanListCreateView,
)

urlpatterns = [
    path("scans/", ScanListCreateView.as_view(), name="scan-list-create"),
    path("reports/dashboard/", DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("reports/", ReportsView.as_view(), name="reports"),
    path("reports/manifest.csv/", ManifestExportView.as_view(), name="manifest-export"),
]
