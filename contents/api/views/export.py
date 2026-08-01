
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from contents.api.serializers.export import (
    ContentExportItemSerializer,
    ContentExportRequestSerializer,
    ContentExportResponseSerializer,
)
from contents.api.serializers.system import APIErrorSerializer
from contents.permissions import HasValidAPIKey
from contents.core_services.idempotency import execute_idempotent
from contents.core_services.exports import (
    export_contents_for_client,
)
from contents.core_services.exports.query import (
    build_export_queryset,
)


API_KEY_HEADER = OpenApiParameter(
    name="X-API-Key",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=True,
    description=(
        "External API key generated in Django Admin under "
        "System Settings. Include this header in every protected request."
    ),
)


@extend_schema(
    tags=["Content Export"],
    parameters=[
        API_KEY_HEADER,
    ],
)
class ContentExportAPIView(APIView):
    permission_classes = [HasValidAPIKey]

    content_type = "standard"
    idempotency_operation = "content-export"

    def _build_queryset(self, validated_data, client):
        """
        Backward-compatible wrapper around the Export query service.

        Query construction lives in the Service Layer.
        """
        return build_export_queryset(
            validated_data=validated_data,
            client=client,
            content_type=self.content_type,
        )

    @extend_schema(
        summary="Export existing contents for the current client",
        description=(
            "Returns matching existing generated contents instead of "
            "creating a new generation job. The API key identifies the "
            "destination client. A content version already exported "
            "successfully to the same client is not returned again. "
            "The same version remains available to other clients."
        ),
        request=ContentExportRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=ContentExportResponseSerializer,
                description=(
                    "Matching contents were exported and recorded."
                ),
            ),
            400: OpenApiResponse(
                response=APIErrorSerializer,
                description="Invalid filters or request body.",
            ),
            403: OpenApiResponse(
                response=APIErrorSerializer,
                description="Missing or invalid client API key.",
            ),
        },
        examples=[
            OpenApiExample(
                name="Export selected existing contents",
                value={
                    "count": 2,
                    "delay_seconds": 0,
                    "languages": [1],
                    "topics": [15],
                    "audiences": [2],
                    "goals": [8],
                    "rules": [],
                    "prompt_templates": [1],
                },
                request_only=True,
            ),
            OpenApiExample(
                name="Export from all datasets",
                value={
                    "count": 100,
                    "delay_seconds": 0,
                    "languages": "all",
                    "topics": "all",
                    "audiences": "all",
                    "goals": "all",
                    "rules": "all",
                    "prompt_templates": "all",
                },
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        return execute_idempotent(
            request,
            self.idempotency_operation,
            lambda: self._export(request),
        )

    def _export(self, request):
        request_serializer = (
            ContentExportRequestSerializer(
                data=request.data,
            )
        )

        request_serializer.is_valid(
            raise_exception=True,
        )

        result = export_contents_for_client(
            validated_data=(
                request_serializer.validated_data
            ),
            client=request.client,
            content_type=self.content_type,
        )

        if result.quota_exceeded:
            return Response(
                {
                    "success": False,
                    "message": "Unable to export contents.",
                    "error": {
                        "code": "daily_export_quota_exceeded",
                        "detail": (
                            "Daily export item quota exceeded."
                        ),
                    },
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        return Response(
            {
                "success": True,
                "message": (
                    "Email replies exported successfully."
                    if self.content_type == "email_reply"
                    else "Contents exported successfully."
                ),
                "data": {
                    "client": request.client.code,
                    "requested": result.requested,
                    "exported": len(
                        result.exported_contents
                    ),
                    "remaining": result.remaining,
                    "items": ContentExportItemSerializer(
                        result.exported_contents,
                        many=True,
                    ).data,
                },
            },
            status=status.HTTP_200_OK,
        )

@extend_schema(
    tags=["Reply Export"],
    parameters=[
        API_KEY_HEADER,
    ],
)
class ReplyExportAPIView(ContentExportAPIView):
    content_type = "email_reply"
    idempotency_operation = "reply-export"

    @extend_schema(
        summary="Export existing email replies for the current client",
        description=(
            "Returns generated email replies that have not already been "
            "exported successfully to the current client."
        ),
        request=ContentExportRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=ContentExportResponseSerializer,
                description="Matching email replies were exported.",
            ),
            400: OpenApiResponse(
                response=APIErrorSerializer,
                description="Invalid filters or request body.",
            ),
            403: OpenApiResponse(
                response=APIErrorSerializer,
                description="Missing or invalid client API key.",
            ),
        },
    )
    def post(self, request):
        return super().post(request)

