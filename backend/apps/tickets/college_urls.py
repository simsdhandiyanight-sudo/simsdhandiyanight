from django.urls import path

from .college_views import (
    CollegeStudentTicketCreateView,
    CollegeStudentTicketDetailView,
    CollegeStudentTicketImportView,
    CollegeStudentTicketPdfView,
)

urlpatterns = [
    path(
        "college-student-tickets/",
        CollegeStudentTicketCreateView.as_view(),
        name="college-student-ticket-create",
    ),
    path(
        "college-student-tickets/import/",
        CollegeStudentTicketImportView.as_view(),
        name="college-student-ticket-import",
    ),
    path(
        "college-student-tickets/<uuid:ticket_id>/",
        CollegeStudentTicketDetailView.as_view(),
        name="college-student-ticket-detail",
    ),
    path(
        "college-student-tickets/<uuid:ticket_id>/pdf/",
        CollegeStudentTicketPdfView.as_view(),
        name="college-student-ticket-pdf",
    ),
]
