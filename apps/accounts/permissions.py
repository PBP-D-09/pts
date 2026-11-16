from rest_framework import permissions


class IsCustomer(permissions.BasePermission):
    message = "Endpoint ini khusus akun pelanggan."

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and request.user.is_customer
        )


class IsTenant(permissions.BasePermission):
    message = "Endpoint ini khusus akun tenant."

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and request.user.is_tenant
        )
