import hashlib
import json
import re
from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from contents.models import APIIdempotencyRecord


KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,255}$")
DEFAULT_TTL = timedelta(hours=24)


def get_idempotency_key(request):
    key = request.headers.get("Idempotency-Key")
    if not key or not KEY_PATTERN.fullmatch(key):
        return None
    return key


def request_fingerprint(request):
    canonical = json.dumps(
        {
            "path": request.path,
            "data": request.data,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def execute_idempotent(request, operation, callback):
    key = get_idempotency_key(request)
    if key is None:
        return callback()

    fingerprint = request_fingerprint(request)
    lock_value = _lock_value(request.client.pk, operation, key)

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_value])

        record = APIIdempotencyRecord.objects.filter(
            client=request.client,
            operation=operation,
            key=key,
        ).first()
        now = timezone.now()

        if record is not None and record.expires_at <= now:
            record.delete()
            record = None

        if record is not None:
            if record.request_fingerprint != fingerprint:
                return Response(
                    {"detail": "Idempotency key was already used with a different request."},
                    status=status.HTTP_409_CONFLICT,
                )
            return Response(record.response_payload, status=record.response_status)

        record = APIIdempotencyRecord.objects.create(
            client=request.client,
            operation=operation,
            key=key,
            request_fingerprint=fingerprint,
            expires_at=now + DEFAULT_TTL,
        )

        response = callback()
        if response.status_code >= 400:
            record.delete()
            return response

        resource_type, resource_id = _resource_reference(operation, response.data)
        record.response_status = response.status_code
        record.response_payload = response.data
        record.resource_type = resource_type
        record.resource_id = resource_id
        record.save(
            update_fields=[
                "response_status",
                "response_payload",
                "resource_type",
                "resource_id",
            ]
        )
        return response


def _lock_value(client_id, operation, key):
    digest = hashlib.sha256(f"{client_id}:{operation}:{key}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _resource_reference(operation, payload):
    if operation == "generation-job-create":
        return "generation_job", payload.get("job", {}).get("id")
    if operation == "content-delivery-create":
        return "content_delivery", payload.get("id")
    return "", None
