from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from contents.api.responses import (
    api_error,
    api_success,
)

from contents.api.serializers.generation_jobs import (
    GenerationJobActionResponseSerializer,
    GenerationJobCreateSerializer,
    GenerationJobSerializer,
)
from contents.api.serializers.system import APIErrorSerializer
from contents.core_services.generation_jobs.creation import (
    create_generation_job,
)
from contents.core_services.generation_jobs.queries import (
    get_generation_jobs_for_client,
)
from contents.core_services.idempotency import execute_idempotent
from contents.permissions import HasValidAPIKey

from .common import API_KEY_HEADER


@extend_schema(
    tags=["Generation Jobs"],
    parameters=[
        API_KEY_HEADER,
    ],
)
class GenerationJobListCreateAPIView(APIView):
    permission_classes = [HasValidAPIKey]

    generation_type = None
    idempotency_operation = "generation-job-create"

    @extend_schema(
        operation_id="list_generation_jobs",
        summary="List generation jobs",
        description=(
            "Returns up to 100 of the latest generation jobs, ordered "
            "from newest to oldest. Each record includes its current "
            "status, progress counters, configuration, and timestamps."
        ),
        responses={
            200: OpenApiResponse(
                response=GenerationJobSerializer(many=True),
                description="Latest generation jobs.",
            ),
            403: OpenApiResponse(
                response=APIErrorSerializer,
                description="Missing or invalid API key.",
            ),
        },
    )
    def get(self, request):
        result = get_generation_jobs_for_client(
            client=request.client,
            request=request,
        )

        if result.error is not None:
            return api_error(
                code="invalid_cursor",
                detail=result.error,
                message="Unable to retrieve generation jobs.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        serializer = GenerationJobSerializer(
            result.jobs,
            many=True,
        )

        if result.cursor_mode:
            response_data = {
                "results": serializer.data,
                "next_cursor": result.next_cursor,
            }
        else:
            response_data = serializer.data

        return api_success(
            data=response_data,
            message="Generation jobs retrieved successfully.",
            status_code=status.HTTP_200_OK,
        )


    @extend_schema(
        operation_id="create_generation_job",
        summary="Create and start a generation job",
        description=(
            "Creates a new AI content generation job and queues it for "
            "asynchronous execution using Celery.\n\n"
            "The response is returned immediately after the job is saved "
            "and queued. Use the job detail endpoint to monitor progress."
        ),
        request=GenerationJobCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=GenerationJobActionResponseSerializer,
                description=(
                    "The generation job was created and queued "
                    "successfully."
                ),
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
        examples=[
            OpenApiExample(
                name="Create standard generation job",
                value={
                    "generation_type": "standard",
                    "count": 10,
                    "delay_seconds": 1.0,
                },
                request_only=True,
            ),
            OpenApiExample(
                name="Create email reply generation job",
                value={
                    "generation_type": "email_reply",
                    "count": 10,
                    "delay_seconds": 1.0,
                    "languages": "all",
                    "topics": "all",
                    "audiences": "all",
                    "goals": "all",
                    "rules": "all",
                    "prompt_templates": "all",
                },
                request_only=True,
            ),
            OpenApiExample(
                name="Job created",
                value={
                    "message": (
                        "Generation job #7 created and started."
                    ),
                    "job": {
                        "id": 7,
                        "generation_type": "standard",
                        "status": "pending",
                        "count": 10,
                        "generated_count": 0,
                        "skipped_count": 0,
                        "current_step": 0,
                    },
                },
                response_only=True,
                status_codes=["201"],
            ),
        ],
    )
    def post(self, request):
        return execute_idempotent(
            request,
            self.idempotency_operation,
            lambda: self._create_job(request),
        )

    def _create_job(self, request):
        request_data = request.data.copy()

        if self.generation_type is not None:
            request_data["generation_type"] = (
                self.generation_type
            )

        serializer = GenerationJobCreateSerializer(
            data=request_data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        result = create_generation_job(
            client=request.client,
            serializer=serializer,
        )

        if not result.success:
            return result.response

        job = result.job

        response_serializer = (
            GenerationJobActionResponseSerializer(
                {
                    "message": (
                        f"Generation job #{job.id} "
                        "created and started."
                    ),
                    "job": job,
                }
            )
        )

        return api_success(
            data={
                "job": response_serializer.data["job"],
            },
            message=response_serializer.data["message"],
            status_code=status.HTTP_201_CREATED,
        )

