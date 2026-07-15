from django.db import transaction
from django.shortcuts import get_object_or_404

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)

from rest_framework import status
from rest_framework.generics import (
    GenericAPIView,
    RetrieveAPIView,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    GenerationJob,
)
from .permissions import HasValidAPIKey
from .serializers import (
    APIErrorSerializer,
    GenerationJobActionResponseSerializer,
    GenerationJobCreateSerializer,
    GenerationJobSerializer,
)
from .api.views import (
    ContentDetailAPIView,
    ContentExportAPIView,
    ContentListAPIView,
    DatasetAPIView,
    HealthCheckAPIView,
)
from .tasks import run_generation_job_task


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

JOB_ID_PARAMETER = OpenApiParameter(
    name="job_id",
    type=OpenApiTypes.INT,
    location=OpenApiParameter.PATH,
    required=True,
    description="Unique numeric ID of the generation job.",
)

@extend_schema(
    tags=["Generation Jobs"],
    parameters=[
        API_KEY_HEADER,
    ],
)
class GenerationJobListCreateAPIView(APIView):
    permission_classes = [HasValidAPIKey]

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
        jobs = (
            GenerationJob.objects
            .filter(external_client=request.client)
            .order_by("-created_at")[:100]
        )

        serializer = GenerationJobSerializer(
            jobs,
            many=True,
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
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
                name="Create generation job",
                value={
                    "count": 10,
                    "delay_seconds": 1.0,
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
        serializer = GenerationJobCreateSerializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        with transaction.atomic():
            job = serializer.save(
                external_client=request.client,
            )

            job.status = "pending"
            job.should_stop = False
            job.error_message = ""
            job.generated_count = 0
            job.skipped_count = 0
            job.current_step = 0

            job.save(
                update_fields=[
                    "status",
                    "should_stop",
                    "error_message",
                    "generated_count",
                    "skipped_count",
                    "current_step",
                    "updated_at",
                ]
            )

            job_id = job.id

            transaction.on_commit(
                lambda: run_generation_job_task.delay(
                    job_id
                )
            )

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

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=["Generation Jobs"],
    summary="Retrieve generation job details",
    description=(
        "Returns the full status and progress details of one generation "
        "job. Use this endpoint to monitor generated, skipped, remaining, "
        "and current-step values."
    ),
    parameters=[
        API_KEY_HEADER,
    ],
    responses={
        200: OpenApiResponse(
            response=GenerationJobSerializer,
            description="Generation job details.",
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
)
class GenerationJobDetailAPIView(RetrieveAPIView):
    permission_classes = [HasValidAPIKey]
    serializer_class = GenerationJobSerializer

    def get_queryset(self):
        return GenerationJob.objects.filter(
            external_client=self.request.client,
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
        with transaction.atomic():
            job = get_object_or_404(
                GenerationJob.objects.select_for_update(),
                id=job_id,
                external_client=request.client,
            )

            if job.status == "running":
                return Response(
                    {
                        "detail": (
                            f"Job #{job.id} is already running."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if job.generated_count >= job.count:
                return Response(
                    {
                        "detail": (
                            f"Job #{job.id} is already completed "
                            f"({job.generated_count}/{job.count})."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            has_existing_progress = (
                job.generated_count > 0
                or job.skipped_count > 0
                or job.current_step > 0
            )

            job.status = "running"
            job.should_stop = False
            job.error_message = ""

            job.save(
                update_fields=[
                    "status",
                    "should_stop",
                    "error_message",
                    "updated_at",
                ]
            )

            transaction.on_commit(
                lambda: run_generation_job_task.delay(
                    job.id
                )
            )

            action_text = (
                "resumed"
                if has_existing_progress
                else "started"
            )

            response_serializer = self.get_serializer(
                {
                    "message": (
                        f"Generation job #{job.id} "
                        f"{action_text}."
                    ),
                    "job": job,
                }
            )

        return Response(
            response_serializer.data,
            status=status.HTTP_200_OK,
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
        with transaction.atomic():
            job = get_object_or_404(
                GenerationJob.objects.select_for_update(),
                id=job_id,
                external_client=request.client,
            )

            if job.status not in [
                "pending",
                "running",
            ]:
                return Response(
                    {
                        "detail": (
                            f"Job #{job.id} is not pending "
                            "or running."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            job.should_stop = True
            job.status = "stopped"
            job.error_message = (
                "Job stopped by external API."
            )

            job.save(
                update_fields=[
                    "should_stop",
                    "status",
                    "error_message",
                    "updated_at",
                ]
            )

            response_serializer = self.get_serializer(
                {
                    "message": (
                        f"Generation job #{job.id} stopped."
                    ),
                    "job": job,
                }
            )

        return Response(
            response_serializer.data,
            status=status.HTTP_200_OK,
        )
