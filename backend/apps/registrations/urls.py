from django.urls import path

from .views import RegistrationDetailView, RegistrationListCreateView

urlpatterns = [
    path("registrations/", RegistrationListCreateView.as_view(), name="registration-list-create"),
    path("registrations/<uuid:registration_id>/", RegistrationDetailView.as_view(), name="registration-detail"),
]
