from rest_framework.permissions import BasePermission, IsAuthenticated, SAFE_METHODS

from apps.accounts.permissions import IsCustomer


class IsCustomerForReviewWrites(BasePermission):
    """Allow public reads, customer create/edit, and authenticated owner deletes."""

    message = "Only customers can create or edit reviews."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        if request.method == "DELETE":
            return IsAuthenticated().has_permission(request, view)
        return IsCustomer().has_permission(request, view)
