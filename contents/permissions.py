from rest_framework.permissions import BasePermission

from .models import ExternalClient


class HasValidAPIKey(BasePermission):
    message = "Invalid or missing API key."

    def has_permission(self, request, view):
        api_key = request.headers.get("X-API-Key")

        if not api_key:
            return False

        client = (
            ExternalClient.objects
            .filter(
                api_key=api_key,
                is_active=True,
            )
            .first()
        )

        if client is None:
            return False

        request.client = client

        return True
