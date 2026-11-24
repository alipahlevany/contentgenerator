from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.views import APIView

from contents.api.responses import (
    api_error,
    api_success,
)

from contents.api.serializers.delivery import ContentDeliverySerializer
from contents.core_services.delivery import validate_callback_url
from contents.core_services.idempotency import execute_idempotent
from contents.models import Content, ContentDelivery
from contents.permissions import HasValidAPIKey
from contents.tasks import deliver_content_callback
from contents.core_services.delivery_queue import dispatch_delivery


class ContentDeliveryAPIView(APIView):
    permission_classes = [HasValidAPIKey]

    @extend_schema(
        operation_id="queue_content_delivery",
        request=None,
        parameters=[
            OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER),
        ],
        responses={
            202: inline_serializer(
                name="QueuedContentDelivery",
                fields={
                    "success": serializers.BooleanField(),
                    "message": serializers.CharField(),
                    "data": inline_serializer(
                        name="QueuedContentDeliveryData",
                        fields={"delivery": ContentDeliverySerializer()},
                    ),
                },
            ),
            400: OpenApiResponse(description="Invalid callback URL."),
            403: OpenApiResponse(description="API key rejected."),
            404: OpenApiResponse(description="Content unavailable for delivery."),
            409: OpenApiResponse(description="Idempotency conflict."),
        },
    )
    def post(self, request, pk):
        return execute_idempotent(
            request,
            "content-delivery-create",
            lambda: self._create_delivery(request, pk),
        )

    def _create_delivery(self, request, pk):
        content = get_object_or_404(
            Content.objects.exclude(content_type="warmup_template"), pk=pk
        )
        callback_url = request.client.callback_url

        try:
            validate_callback_url(callback_url)
        except ValidationError as exc:
            return api_error(
                code="invalid_callback_url",
                detail=exc.messages[0],
                message="Unable to create content delivery.",
                status_code=status.HTTP_400_BAD_REQUEST,
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
                    lambda: dispatch_delivery(delivery.pk)
                )

        return api_success(
            data={
                "delivery": ContentDeliverySerializer(
                    delivery
                ).data,
            },
            message="Content delivery queued successfully.",
            status_code=status.HTTP_202_ACCEPTED,
        )
