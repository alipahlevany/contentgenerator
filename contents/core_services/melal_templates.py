"""Durable template outbox and idempotent delivery to Melal."""
import hashlib
import logging
from datetime import timedelta
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from contents.models import MelalTemplateDelivery

logger = logging.getLogger(__name__)


def queue_template(content):
    if not settings.MELAL_TEMPLATE_ENABLED:
        return
    external_id = f"{settings.MELAL_TEMPLATE_SOURCE}:{content.pk}"
    if len(external_id) > 100:
        external_id = "sha256:" + hashlib.sha256(external_id.encode()).hexdigest()
    row, _ = MelalTemplateDelivery.objects.get_or_create(
        content=content,
        defaults={
            "external_id": external_id,
            "endpoint": settings.MELAL_TEMPLATE_ENDPOINT,
            "html": content.generated_content,
        },
    )
    transaction.on_commit(lambda: dispatch(row.pk))


def dispatch(pk):
    from contents.tasks import send_melal_template
    try:
        send_melal_template.delay(pk)
    except Exception:
        logger.warning("Melal outbox %s awaits the periodic dispatcher.", pk)


def send_template(pk):
    if not settings.MELAL_TEMPLATE_ENABLED:
        return "disabled"
    with transaction.atomic():
        row = MelalTemplateDelivery.objects.select_for_update().get(pk=pk)
        if row.status != "pending" or row.next_attempt_at > timezone.now():
            return row.status
        try:
            parts = urlsplit(row.endpoint)
        except ValueError:
            parts = urlsplit("")
        local_http = (
            settings.MELAL_TEMPLATE_ALLOW_LOCAL_HTTP and parts.scheme == "http"
            and parts.hostname in {"127.0.0.1", "localhost"}
        )
        if (not (parts.scheme == "https" or local_http) or not parts.hostname
                or parts.username or parts.password or parts.fragment
                or row.endpoint != settings.MELAL_TEMPLATE_ENDPOINT
                or not settings.MELAL_TEMPLATE_API_KEY):
            row.last_error = "Connector configuration is missing or changed."
            row.next_attempt_at = timezone.now() + timedelta(minutes=5)
            row.save(update_fields=["last_error", "next_attempt_at"])
            return "configuration_error"
        row.attempts += 1
        retry = False
        try:
            response = requests.post(
                row.endpoint,
                headers={"Authorization": f"Api-Key {settings.MELAL_TEMPLATE_API_KEY}"},
                json={"external_id": row.external_id, "html": row.html},
                timeout=(5, 20), allow_redirects=False,
            )
            if response.status_code in (200, 201):
                payload = response.json()
                remote_id = payload.get("id") if isinstance(payload, dict) else None
                if type(remote_id) is not int or remote_id <= 0:
                    raise ValueError("Invalid import response")
                row.remote_id = remote_id
                row.status = "sent"
                row.last_error = ""
            else:
                row.last_error = f"Melal returned HTTP {response.status_code}."
                retry = response.status_code in (408, 429) or response.status_code >= 500
                if not retry:
                    row.status = "failed"
        except (requests.RequestException, ValueError):
            row.last_error = "Connection failed or Melal returned an invalid response."
            retry = True
        if retry:
            row.status = "failed" if row.attempts >= 8 else "pending"
            row.next_attempt_at = timezone.now() + timedelta(seconds=min(3600, 30 * 2 ** row.attempts))
        row.save()
        return row.status
