import logging
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction

from contents.core_services.delivery import validate_callback_url
from contents.models import ContentDelivery, ExternalClient


logger = logging.getLogger(__name__)


def dispatch_delivery(delivery_id):
    from contents.tasks import deliver_content_callback
    try:
        deliver_content_callback.delay(delivery_id)
    except Exception:
        logger.warning("Callback %s awaits the periodic dispatcher.", delivery_id)
        return False
    return True


def recover_pending_deliveries():
    cutoff = timezone.now() - timedelta(minutes=5)
    candidates = ContentDelivery.objects.filter(
        Q(status="pending") | Q(status="processing", last_attempt_at__lt=cutoff),
        purpose="callback", updated_at__lt=cutoff, attempt_count__lt=4,
    ).exclude(content__content_type="warmup_template")
    count = 0
    for pk in list(candidates.order_by("pk").values_list("pk", flat=True)[:100]):
        claimed = candidates.filter(pk=pk).update(updated_at=timezone.now())
        if claimed and dispatch_delivery(pk):
            count += 1
    return count


def queue_content_deliveries(content):
    """
    Create and enqueue callback deliveries for eligible external clients.

    The operation is idempotent because ContentDelivery has a unique
    constraint for client, content, content_hash and purpose.
    """
    if content.content_type == "warmup_template":
        return []

    clients = ExternalClient.objects.all()

    preference_field = {
        "standard": "receives_standard_content",
        "email_reply": "receives_email_replies",
        "greeting": "receives_greetings",
    }.get(content.content_type)

    if preference_field:
        clients = clients.filter(**{preference_field: True})

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
            dispatch_delivery(pk)

        transaction.on_commit(enqueue)

    return queued_delivery_ids
