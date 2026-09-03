import hashlib

from django.db import connection
from django.utils import timezone
from rest_framework import status

from contents.api.responses import api_error
from contents.models import ContentExport, GenerationJob


def lock_client_limit(client_id, operation):
    digest = hashlib.sha256(f"limit:{client_id}:{operation}".encode()).digest()
    value = int.from_bytes(digest[:8], byteorder="big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [value])


def validate_generation_limits(client, requested_count, generation_type=None):
    if not client.limits_enabled:
        return None
    if (
        client.max_generation_content_count is not None
        and requested_count > client.max_generation_content_count
    ):
        return api_error(
            code="generation_content_quota_exceeded",
            detail="Generation content quota exceeded.",
            message="Generation quota exceeded.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    if client.max_active_generation_jobs is not None:
        active_jobs = GenerationJob.objects.filter(
            external_client=client,
            status__in=["pending", "running"],
        )

        if generation_type:
            active_jobs = active_jobs.filter(
                generation_type=generation_type,
            )

        active_count = active_jobs.count()
        if active_count >= client.max_active_generation_jobs:
            return api_error(
                code="active_generation_job_quota_exceeded",
                detail="Active generation job quota exceeded.",
                message="Generation quota exceeded.",
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
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
