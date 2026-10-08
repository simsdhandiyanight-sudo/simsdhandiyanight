from django.urls import path

from .views import AdminEventContextView, EventDetailView, EventListView

urlpatterns = [
    path("events/", EventListView.as_view(), name="event-list"),
    path(
        "events/admin-context/<slug:event_slug>/",
        AdminEventContextView.as_view(),
        name="admin-event-context",
    ),
    path("events/<str:event_identifier>/", EventDetailView.as_view(), name="event-detail"),
]
