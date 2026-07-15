from rest_framework.permissions import BasePermission

from .models import ExternalClient


class HasValidAPIKey(BasePermission):
    message = "Invalid or missing API key."

    def has_permission(self, request, view):
        api_key = request.headers.get("X-API-Key")

        if not api_key:
            return False

        client = None

        parts = api_key.split("_", 2)
        if len(parts) == 3 and parts[0] == "cg":
            prefix, secret = parts[1:]
            candidate = (
                ExternalClient.objects
                .filter(
                    api_key_prefix=prefix,
                    is_active=True,
                )
                .first()
            )
            if (
                candidate is not None
                and candidate.matches_api_key_secret(secret)
            ):
                client = candidate
        else:
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
