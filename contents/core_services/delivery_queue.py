from django.core.exceptions import ValidationError
from django.db import transaction

from contents.core_services.delivery import validate_callback_url
from contents.models import ContentDelivery, ExternalClient


def queue_content_deliveries(content):
    """
    Create and enqueue callback deliveries for eligible external clients.

    The operation is idempotent because ContentDelivery has a unique
    constraint for client, content, content_hash and purpose.
    """
    clients = ExternalClient.objects.all()

    model_fields = {
        field.name
        for field in ExternalClient._meta.get_fields()
    }

    if "is_active" in model_fields:
        clients = clients.filter(is_active=True)

    queued_delivery_ids = []

    for client in clients.iterator():
        callback_url = (client.callback_url or "").strip()

        if not callback_url:
            continue

        try:
            validate_callback_url(callback_url)
        except ValidationError:
            continue

        delivery, created = ContentDelivery.objects.get_or_create(
            client=client,
            content=content,
            content_hash=content.content_hash or "",
            purpose="callback",
            defaults={
                "destination_url": callback_url,
            },
        )

        if not created:
            continue

        delivery_id = delivery.pk
        queued_delivery_ids.append(delivery_id)

        def enqueue(pk=delivery_id):
            from contents.tasks import deliver_content_callback

            deliver_content_callback.delay(pk)

        transaction.on_commit(enqueue)

    return queued_delivery_ids
