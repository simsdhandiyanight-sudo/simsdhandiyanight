from django.urls import path

from .views import OnSpotRegistrationView, RegistrationDetailView, RegistrationListCreateView

urlpatterns = [
    path("registrations/", RegistrationListCreateView.as_view(), name="registration-list-create"),
    path("registrations/on-spot/", OnSpotRegistrationView.as_view(), name="on-spot-registration"),
    path("registrations/<uuid:registration_id>/", RegistrationDetailView.as_view(), name="registration-detail"),
]
