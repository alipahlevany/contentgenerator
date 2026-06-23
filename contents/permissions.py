from rest_framework.permissions import BasePermission

from .models import AppSettings


class HasValidAPIKey(BasePermission):
    message = "Invalid or missing API key."

    def has_permission(self, request, view):
        api_key = request.headers.get("X-API-Key")

        if not api_key:
            return False

        app_settings = (
            AppSettings.objects
            .filter(
                is_active=True,
                api_secret_key=api_key,
            )
            .first()
        )

        if not app_settings:
            return False

        return True