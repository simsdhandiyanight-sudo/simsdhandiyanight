from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/internal/", include("apps.payments.internal_urls")),
    path("api/v1/", include("apps.api_urls")),
]
