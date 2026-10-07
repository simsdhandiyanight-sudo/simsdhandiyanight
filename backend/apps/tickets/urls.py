from django.urls import path

from .views import TicketCancelView, TicketDetailView, TicketListView

urlpatterns = [
    path("tickets/", TicketListView.as_view(), name="ticket-list"),
    path("tickets/<uuid:ticket_id>/", TicketDetailView.as_view(), name="ticket-detail"),
    path("tickets/<uuid:ticket_id>/cancel/", TicketCancelView.as_view(), name="ticket-cancel"),
]
