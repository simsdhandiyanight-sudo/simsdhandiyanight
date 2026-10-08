from django.urls import path

from .views import (
    RegistrationTicketsPdfView,
    TicketCancelView,
    TicketDetailView,
    TicketListView,
    TicketPdfView,
)

urlpatterns = [
    path("tickets/", TicketListView.as_view(), name="ticket-list"),
    path("tickets/<uuid:ticket_id>/", TicketDetailView.as_view(), name="ticket-detail"),
    path("tickets/<uuid:ticket_id>/pdf/", TicketPdfView.as_view(), name="ticket-pdf"),
    path(
        "registrations/<uuid:registration_id>/tickets.pdf",
        RegistrationTicketsPdfView.as_view(),
        name="registration-tickets-pdf",
    ),
    path("tickets/<uuid:ticket_id>/cancel/", TicketCancelView.as_view(), name="ticket-cancel"),
]
