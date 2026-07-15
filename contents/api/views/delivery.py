from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from contents.api.serializers.delivery import ContentDeliverySerializer
from contents.core_services.delivery import validate_callback_url
from contents.core_services.idempotency import execute_idempotent
from contents.models import Content, ContentDelivery
from contents.permissions import HasValidAPIKey
from contents.tasks import deliver_content_callback


class ContentDeliveryAPIView(APIView):
    permission_classes = [HasValidAPIKey]

    def post(self, request, pk):
        return execute_idempotent(
            request,
            "content-delivery-create",
            lambda: self._create_delivery(request, pk),
        )

    def _create_delivery(self, request, pk):
        content = get_object_or_404(Content, pk=pk)
        callback_url = request.client.callback_url

        try:
            validate_callback_url(callback_url)
        except ValidationError as exc:
            return Response(
                {"detail": exc.messages[0]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            delivery, created = ContentDelivery.objects.get_or_create(
                client=request.client,
                content=content,
                content_hash=content.content_hash,
                purpose="callback",
                defaults={
                    "destination_url": callback_url,
                },
            )
            if created:
                transaction.on_commit(
                    lambda: deliver_content_callback.delay(delivery.pk)
                )

        return Response(
            ContentDeliverySerializer(delivery).data,
            status=status.HTTP_202_ACCEPTED,
        )
