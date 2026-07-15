from django.db.models import Q

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework import status
from rest_framework.response import Response

from contents.api.serializers.content import (
    ContentDetailSerializer,
    ContentListSerializer,
)
from contents.api.serializers.system import APIErrorSerializer
from contents.models import Content
from contents.permissions import HasValidAPIKey
from contents.core_services.pagination import (
    InvalidCursor,
    cursor_mode_requested,
    paginate_queryset,
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

CONTENT_STATUS_PARAMETER = OpenApiParameter(
    name="status",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.QUERY,
    required=False,
    enum=[
        "draft",
        "generated",
        "published",
    ],
    description=(
        "Optional content status filter. Supported values are "
        "`draft`, `generated`, and `published`."
    ),
)

CONTENT_SEARCH_PARAMETER = OpenApiParameter(
    name="q",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.QUERY,
    required=False,
    description=(
        "Optional case-insensitive search query. Searches the title, "
        "prompt, and generated content fields."
    ),
)


@extend_schema(
    tags=["Generated Contents"],
    summary="List generated contents",
    description=(
        "Returns up to 100 of the latest generated content records.\n\n"
        "The results can optionally be filtered by content status or "
        "searched using the `q` query parameter."
    ),
    parameters=[
        API_KEY_HEADER,
        CONTENT_STATUS_PARAMETER,
        CONTENT_SEARCH_PARAMETER,
    ],
    responses={
        200: OpenApiResponse(
            response=ContentListSerializer(many=True),
            description="Latest generated content records.",
        ),
        403: OpenApiResponse(
            response=APIErrorSerializer,
            description="Missing or invalid API key.",
        ),
    },
)
class ContentListAPIView(ListAPIView):
    permission_classes = [HasValidAPIKey]
    serializer_class = ContentListSerializer

    def get_queryset(self):
        queryset = (
            Content.objects
            .select_related(
                "language",
                "topic",
                "audience",
                "goal",
                "prompt_template",
            )
            .all()
            .order_by("-created_at", "-id")
        )

        content_status = (
            self.request.query_params.get(
                "status"
            )
        )

        search_query = (
            self.request.query_params.get(
                "q"
            )
        )

        if content_status:
            queryset = queryset.filter(
                status=content_status,
            )

        if search_query:
            queryset = queryset.filter(
                Q(
                    title__icontains=search_query
                )
                | Q(
                    prompt__icontains=search_query
                )
                | Q(
                    generated_content__icontains=(
                        search_query
                    )
                )
            )

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if not cursor_mode_requested(request):
            serializer = self.get_serializer(queryset[:100], many=True)
            return Response(serializer.data)
        try:
            items, next_cursor = paginate_queryset(queryset, request)
        except InvalidCursor as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = self.get_serializer(items, many=True)
        return Response({"results": serializer.data, "next_cursor": next_cursor})


@extend_schema(
    tags=["Generated Contents"],
    summary="Retrieve generated content details",
    description=(
        "Returns one generated content record, including its title, "
        "body, prompt, language, topic, audience, goal, prompt template, "
        "content rules, status, and timestamps."
    ),
    parameters=[
        API_KEY_HEADER,
    ],
    responses={
        200: OpenApiResponse(
            response=ContentDetailSerializer,
            description="Generated content details.",
        ),
        403: OpenApiResponse(
            response=APIErrorSerializer,
            description="Missing or invalid API key.",
        ),
        404: OpenApiResponse(
            response=APIErrorSerializer,
            description="Generated content not found.",
        ),
    },
)
class ContentDetailAPIView(RetrieveAPIView):
    permission_classes = [HasValidAPIKey]
    serializer_class = ContentDetailSerializer

    queryset = (
        Content.objects
        .select_related(
            "language",
            "topic",
            "audience",
            "goal",
            "prompt_template",
        )
        .prefetch_related(
            "rules"
        )
        .all()
    )
