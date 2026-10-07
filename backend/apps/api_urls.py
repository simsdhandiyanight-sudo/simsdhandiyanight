from django.urls import include, path

urlpatterns = [
    path("", include("apps.accounts.urls")),
    path("", include("apps.events.urls")),
    path("", include("apps.registrations.urls")),
    path("", include("apps.tickets.urls")),
    path("", include("apps.scanning.urls")),
]
