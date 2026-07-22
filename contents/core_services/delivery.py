import ipaddress
import socket
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from contents.models import ContentDelivery


class RetryableDeliveryError(Exception):
    pass


def validate_callback_url(url):
    parsed = urlparse(url)

    if parsed.scheme != "https" or not parsed.hostname:
        raise ValidationError("Callback URL must be a valid HTTPS URL.")

    if parsed.username or parsed.password:
        raise ValidationError("Callback URL must not contain credentials.")

    allow_private = getattr(
        settings,
        "CALLBACK_DELIVERY_ALLOW_PRIVATE_NETWORKS",
        False,
    )

    if allow_private:
        return url

    try:
        addresses = socket.getaddrinfo(
            parsed.hostname,
            parsed.port or 443,
        )
    except socket.gaierror as exc:
        raise ValidationError(
            "Callback URL hostname could not be resolved."
        ) from exc

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])

        if not ip.is_global:
            raise ValidationError(
                "Callback URL resolves to a blocked network."
            )

    return url


def deliver_content(delivery_id):
    with transaction.atomic():
        delivery = (
            ContentDelivery.objects
            .select_for_update()
            .select_related("content", "client")
            .get(pk=delivery_id)
        )

        if delivery.status == "success":
            return delivery

        validate_callback_url(delivery.destination_url)

        delivery.status = "processing"
        delivery.attempt_count += 1
        delivery.last_attempt_at = timezone.now()
        delivery.last_error = ""

        delivery.save(
            update_fields=[
                "status",
                "attempt_count",
                "last_attempt_at",
                "last_error",
                "updated_at",
            ]
        )

    payload = {
        "id": delivery.content_id,
        "title": delivery.content.title,
        "content": delivery.content.generated_content,
        "content_hash": delivery.content_hash,
    }

    api_key = getattr(settings, "MTA_API_KEY", "")

    if not api_key:
        _mark_failed(
            delivery.pk,
            "MTA API key is not configured.",
        )
        return ContentDelivery.objects.get(pk=delivery.pk)

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-API-Key": api_key,
    }

    try:
        response = requests.post(
            delivery.destination_url,
            json=payload,
            headers=headers,
            timeout=(5, 15),
            allow_redirects=False,
        )

    except (
        requests.Timeout,
        requests.ConnectionError,
    ) as exc:
        message = "Temporary callback connection failure."

        _mark_failed(
            delivery.pk,
            message,
        )

        raise RetryableDeliveryError(message) from exc

    except requests.RequestException as exc:
        _mark_failed(
            delivery.pk,
            f"Callback request failed: {str(exc)[:300]}",
        )
        return ContentDelivery.objects.get(pk=delivery.pk)

    if 200 <= response.status_code < 300:
        with transaction.atomic():
            delivery = (
                ContentDelivery.objects
                .select_for_update()
                .get(pk=delivery.pk)
            )

            delivery.status = "success"
            delivery.delivered_at = timezone.now()
            delivery.last_error = ""

            delivery.save(
                update_fields=[
                    "status",
                    "delivered_at",
                    "last_error",
                    "updated_at",
                ]
            )

        return delivery

    response_body = response.text[:500].strip()

    message = f"Callback returned HTTP {response.status_code}."

    if response_body:
        message += f" Response: {response_body}"

    _mark_failed(
        delivery.pk,
        message,
    )

    if response.status_code >= 500:
        raise RetryableDeliveryError(message)

    return ContentDelivery.objects.get(pk=delivery.pk)


def _mark_failed(delivery_id, message):
    ContentDelivery.objects.filter(
        pk=delivery_id
    ).update(
        status="failed",
        last_error=message,
        updated_at=timezone.now(),
    )
