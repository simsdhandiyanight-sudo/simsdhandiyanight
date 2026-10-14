import hmac

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import APIException, AuthenticationFailed
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView


class InternalApiConfigurationError(APIException):
    status_code = 503
    default_detail = "Internal API authentication is not configured."
    default_code = "internal_api_not_configured"


class N8nTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header:
            return None
        scheme, separator, supplied = header.partition(" ")
        if not separator or scheme != "Token" or not supplied.strip():
            raise AuthenticationFailed("Invalid internal API credentials.")
        expected = settings.DJANGO_INTERNAL_API_KEY
        if not expected:
            raise InternalApiConfigurationError()
        if not hmac.compare_digest(supplied.strip(), expected):
            raise AuthenticationFailed("Invalid internal API credentials.")
        from django.contrib.auth.models import AnonymousUser

        return AnonymousUser(), "n8n"

    def authenticate_header(self, request):
        return "Token"


class HasN8nApiKey(BasePermission):
    def has_permission(self, request, view):
        if not settings.DJANGO_INTERNAL_API_KEY:
            raise InternalApiConfigurationError()
        return request.auth == "n8n"


class PendingEmailJobsView(APIView):
    permission_classes = [HasN8nApiKey]
    authentication_classes = [N8nTokenAuthentication]

    def get(self, request):
        return Response({"count": 0, "jobs": []})
