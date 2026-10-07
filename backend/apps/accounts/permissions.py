from rest_framework.permissions import BasePermission


class HasRole(BasePermission):
    allowed_roles = ()

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in self.allowed_roles
        )


class IsAdministrator(HasRole):
    allowed_roles = ("ADMIN",)


class CanRegisterOnSpot(HasRole):
    allowed_roles = ("ADMIN", "REGISTRATION_STAFF")


class CanScan(HasRole):
    allowed_roles = ("ADMIN", "SCANNER_STAFF")


class CanViewOperations(HasRole):
    allowed_roles = ("ADMIN", "REGISTRATION_STAFF", "SCANNER_STAFF")
