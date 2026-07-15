import hashlib

from django.db import connection
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from contents.models import ContentExport, GenerationJob


def lock_client_limit(client_id, operation):
    digest = hashlib.sha256(f"limit:{client_id}:{operation}".encode()).digest()
    value = int.from_bytes(digest[:8], byteorder="big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [value])


def validate_generation_limits(client, requested_count):
    if not client.limits_enabled:
        return None
    if (
        client.max_generation_content_count is not None
        and requested_count > client.max_generation_content_count
    ):
        return Response(
            {"detail": "Generation content quota exceeded."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    if client.max_active_generation_jobs is not None:
        active_count = GenerationJob.objects.filter(
            external_client=client,
            status__in=["pending", "running"],
        ).count()
        if active_count >= client.max_active_generation_jobs:
            return Response(
                {"detail": "Active generation job quota exceeded."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
    return None


def remaining_daily_export_quota(client):
    if not client.limits_enabled or client.daily_export_item_quota is None:
        return None
    today = timezone.localdate()
    used = ContentExport.objects.filter(
        client=client,
        status="success",
        exported_at__date=today,
    ).count()
    return max(client.daily_export_item_quota - used, 0)
