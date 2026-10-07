from django.urls import path

from .views import EventDetailView, EventListView

urlpatterns = [
    path("events/", EventListView.as_view(), name="event-list"),
    path("events/<str:event_identifier>/", EventDetailView.as_view(), name="event-detail"),
]
