from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

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
from contents.models import Content, ContentExport
from contents.permissions import HasValidAPIKey
from contents.core_services.idempotency import execute_idempotent


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

    filter_map = {
        "languages": "language_id__in",
        "topics": "topic_id__in",
        "audiences": "audience_id__in",
        "goals": "goal_id__in",
        "prompt_templates": "prompt_template_id__in",
    }

    def _build_queryset(self, validated_data, client):
        successful_export = (
            ContentExport.objects
            .filter(
                client=client,
                content_id=OuterRef("pk"),
                content_hash=OuterRef("content_hash"),
                status="success",
            )
        )

        queryset = (
            Content.objects
            .filter(status="generated")
            .annotate(
                already_exported=Exists(successful_export)
            )
            .filter(already_exported=False)
            .select_related(
                "language",
                "topic",
                "audience",
                "goal",
                "prompt_template",
            )
            .prefetch_related("rules")
            .order_by("id")
        )

        for request_field, lookup in self.filter_map.items():
            selection = validated_data[request_field]

            if selection != "all":
                queryset = queryset.filter(
                    **{
                        lookup: selection,
                    }
                )

        rule_selection = validated_data["rules"]

        if (
            rule_selection != "all"
            and rule_selection
        ):
            queryset = queryset.filter(
                rules__id__in=rule_selection,
            ).distinct()

        return queryset

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
            "content-export",
            lambda: self._export(request),
        )

    def _export(self, request):
        request_serializer = ContentExportRequestSerializer(
            data=request.data,
        )
        request_serializer.is_valid(raise_exception=True)

        validated_data = request_serializer.validated_data
        requested_count = validated_data["count"]
        client = request.client

        exported_contents = []

        with transaction.atomic():
            candidate_ids = list(
                self._build_queryset(
                    validated_data,
                    client,
                ).values_list(
                    "id",
                    flat=True,
                )[:requested_count]
            )

            candidates = list(
                Content.objects
                .filter(id__in=candidate_ids)
                .select_for_update(of=("self",))
                .select_related(
                    "language",
                    "topic",
                    "audience",
                    "goal",
                    "prompt_template",
                )
                .prefetch_related("rules")
                .order_by("id")
            )

            for content in candidates:
                export = (
                    ContentExport.objects
                    .filter(
                        content=content,
                        client=client,
                        content_hash=content.content_hash,
                    )
                    .first()
                )

                if export is not None:
                    if export.status == "success":
                        continue

                    export.status = "success"
                    export.exported_at = timezone.now()
                    export.error_message = ""
                    export.save(
                        update_fields=[
                            "status",
                            "exported_at",
                            "error_message",
                            "updated_at",
                        ]
                    )
                else:
                    try:
                        with transaction.atomic():
                            ContentExport.objects.create(
                                content=content,
                                client=client,
                                content_hash=content.content_hash,
                                status="success",
                                exported_at=timezone.now(),
                            )
                    except IntegrityError:
                        export = (
                            ContentExport.objects
                            .filter(
                                content=content,
                                client=client,
                                content_hash=content.content_hash,
                            )
                            .first()
                        )

                        if export is None:
                            raise

                        if export.status == "success":
                            continue

                        export.status = "success"
                        export.exported_at = timezone.now()
                        export.error_message = ""
                        export.save(
                            update_fields=[
                                "status",
                                "exported_at",
                                "error_message",
                                "updated_at",
                            ]
                        )

                exported_contents.append(content)

            remaining_queryset = self._build_queryset(
                validated_data,
                client,
            )
            remaining = remaining_queryset.count()

        return Response(
            {
            "client": client.code,
            "requested": requested_count,
            "exported": len(exported_contents),
            "remaining": remaining,
            "items": ContentExportItemSerializer(
                exported_contents,
                many=True,
            ).data,
        },
        status=status.HTTP_200_OK,
        )
