from drf_spectacular.utils import (
    OpenApiResponse,
    extend_schema,
)

from contents.api.serializers.generation_jobs import (
    GenerationJobActionResponseSerializer,
    GenerationJobCreateSerializer,
)
from contents.api.serializers.system import APIErrorSerializer

from .common import API_KEY_HEADER
from .list_create import GenerationJobListCreateAPIView


@extend_schema(
    tags=["Content Generation"],
    parameters=[API_KEY_HEADER],
)
class ContentGenerationJobCreateAPIView(
    GenerationJobListCreateAPIView
):
    generation_type = "standard"
    idempotency_operation = "content-generation-job-create"

    @extend_schema(
        operation_id="create_content_generation_job",
        summary="Create and start a standard content generation job",
        description=(
            "Creates and queues a standard content generation job. "
            "The generation type is set automatically by the server."
        ),
        request=GenerationJobCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=GenerationJobActionResponseSerializer,
                description="The content generation job was created.",
            ),
            400: OpenApiResponse(
                response=APIErrorSerializer,
                description="The request data is invalid.",
            ),
            403: OpenApiResponse(
                response=APIErrorSerializer,
                description="Missing or invalid API key.",
            ),
        },
    )
    def post(self, request):
        return super().post(request)


@extend_schema(
    tags=["Reply Generation"],
    parameters=[API_KEY_HEADER],
)
class ReplyGenerationJobCreateAPIView(
    GenerationJobListCreateAPIView
):
    generation_type = "email_reply"
    idempotency_operation = "reply-generation-job-create"

    @extend_schema(
        operation_id="create_reply_generation_job",
        summary="Create and start an email reply generation job",
        description=(
            "Creates and queues an email reply generation job. "
            "The generation type is set automatically by the server."
        ),
        request=GenerationJobCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=GenerationJobActionResponseSerializer,
                description="The reply generation job was created.",
            ),
            400: OpenApiResponse(
                response=APIErrorSerializer,
                description="The request data is invalid.",
            ),
            403: OpenApiResponse(
                response=APIErrorSerializer,
                description="Missing or invalid API key.",
            ),
        },
    )
    def post(self, request):
        return super().post(request)

