from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from contents.api.responses import (
    api_error,
    api_success,
)

from contents.api.serializers.generation_jobs import (
    GenerationJobActionResponseSerializer,
)
from contents.api.serializers.system import APIErrorSerializer
from contents.core_services.generation_jobs.actions import (
    start_generation_job,
    stop_generation_job,
)
from contents.models import GenerationJob
from contents.permissions import HasValidAPIKey

from .common import (
    API_KEY_HEADER,
    JOB_ID_PARAMETER,
)


@extend_schema(
    tags=["Generation Jobs"],
    parameters=[
        API_KEY_HEADER,
        JOB_ID_PARAMETER,
    ],
)
class GenerationJobStartAPIView(GenericAPIView):
    permission_classes = [HasValidAPIKey]
    serializer_class = GenerationJobActionResponseSerializer
    queryset = GenerationJob.objects.all()

    @extend_schema(
        operation_id="start_or_resume_generation_job",
        summary="Start or resume a generation job",
        description=(
            "Starts a pending job or resumes a stopped or failed job.\n\n"
            "Existing progress is preserved. For example, a stopped job "
            "at 12/100 continues from 12 instead of resetting to zero.\n\n"
            "A completed job cannot be started again through this endpoint."
        ),
        request=None,
        responses={
            200: OpenApiResponse(
                response=GenerationJobActionResponseSerializer,
                description="The job was queued successfully.",
            ),
            400: OpenApiResponse(
                response=APIErrorSerializer,
                description=(
                    "The job is already running or has already completed."
                ),
            ),
            403: OpenApiResponse(
                response=APIErrorSerializer,
                description="Missing or invalid API key.",
            ),
            404: OpenApiResponse(
                response=APIErrorSerializer,
                description="Generation job not found.",
            ),
        },
        examples=[
            OpenApiExample(
                name="Job resumed",
                value={
                    "message": "Generation job #7 resumed.",
                    "job": {
                        "id": 7,
                        "status": "pending",
                        "count": 100,
                        "generated_count": 12,
                        "skipped_count": 2,
                        "current_step": 14,
                    },
                },
                response_only=True,
                status_codes=["200"],
            ),
        ],
    )
    def post(self, request, job_id):
        result = start_generation_job(
            job_id=job_id,
            external_client=request.client,
        )

        if not result.success:
            error_code = (
                "job_already_running"
                if "already running" in result.error.lower()
                else "job_already_completed"
            )

            return api_error(
                code=error_code,
                detail=result.error,
                message="Unable to start generation job.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        response_serializer = self.get_serializer(
            {
                "message": result.message,
                "job": result.job,
            }
        )

        return api_success(
            data={
                "job": response_serializer.data["job"],
            },
            message=response_serializer.data["message"],
            status_code=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["Generation Jobs"],
    parameters=[
        API_KEY_HEADER,
        JOB_ID_PARAMETER,
    ],
)
class GenerationJobStopAPIView(GenericAPIView):
    permission_classes = [HasValidAPIKey]
    serializer_class = GenerationJobActionResponseSerializer
    queryset = GenerationJob.objects.all()

    @extend_schema(
        operation_id="stop_generation_job",
        summary="Stop a generation job",
        description=(
            "Requests a pending or running generation job to stop.\n\n"
            "The existing progress is preserved, allowing the job to be "
            "resumed later through the start endpoint."
        ),
        request=None,
        responses={
            200: OpenApiResponse(
                response=GenerationJobActionResponseSerializer,
                description="The stop request was recorded successfully.",
            ),
            400: OpenApiResponse(
                response=APIErrorSerializer,
                description="The selected job is not pending or running.",
            ),
            403: OpenApiResponse(
                response=APIErrorSerializer,
                description="Missing or invalid API key.",
            ),
            404: OpenApiResponse(
                response=APIErrorSerializer,
                description="Generation job not found.",
            ),
        },
        examples=[
            OpenApiExample(
                name="Job stopped",
                value={
                    "message": "Generation job #7 stopped.",
                    "job": {
                        "id": 7,
                        "status": "stopped",
                        "count": 100,
                        "generated_count": 12,
                        "skipped_count": 2,
                        "current_step": 14,
                    },
                },
                response_only=True,
                status_codes=["200"],
            ),
        ],
    )
    def post(self, request, job_id):
        result = stop_generation_job(
            job_id=job_id,
            external_client=request.client,
        )

        if not result.success:
            return api_error(
                code="job_not_stoppable",
                detail=result.error,
                message="Unable to stop generation job.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        response_serializer = self.get_serializer(
            {
                "message": result.message,
                "job": result.job,
            }
        )

        return api_success(
            data={
                "job": response_serializer.data["job"],
            },
            message=response_serializer.data["message"],
            status_code=status.HTTP_200_OK,
        )

