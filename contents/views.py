from django.db.models import Q
from django.shortcuts import get_object_or_404

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Content, GenerationJob
from .permissions import HasValidAPIKey
from .serializers import (
    APIErrorSerializer,
    ContentDetailSerializer,
    ContentListSerializer,
    GenerationJobActionResponseSerializer,
    GenerationJobCreateSerializer,
    GenerationJobSerializer,
    HealthCheckSerializer,
)
from .tasks import run_generation_job_task


API_KEY_HEADER = OpenApiParameter(
    name="X-API-Key",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=True,
    description="External API key from Admin → App Settings.",
)


@extend_schema(
    tags=["System"],
    responses={
        200: HealthCheckSerializer,
    },
)
class HealthCheckAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                "status": "ok",
                "service": "content-generator",
            }
        )


@extend_schema(
    tags=["Generation Jobs"],
    parameters=[API_KEY_HEADER],
)
class GenerationJobListCreateAPIView(APIView):
    permission_classes = [HasValidAPIKey]

    @extend_schema(
        summary="List generation jobs",
        description="Returns the latest generation jobs.",
        responses={
            200: GenerationJobSerializer(many=True),
            403: APIErrorSerializer,
        },
    )
    def get(self, request):
        jobs = (
            GenerationJob.objects
            .all()
            .order_by("-created_at")[:100]
        )

        serializer = GenerationJobSerializer(jobs, many=True)

        return Response(serializer.data)

    @extend_schema(
        summary="Create and start a generation job",
        description=(
            "Creates a new generation job and starts it asynchronously "
            "using Celery."
        ),
        request=GenerationJobCreateSerializer,
        responses={
            201: GenerationJobActionResponseSerializer,
            400: APIErrorSerializer,
            403: APIErrorSerializer,
        },
    )
    def post(self, request):
        serializer = GenerationJobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        job = serializer.save()

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
            ]
        )

        run_generation_job_task.delay(job.id)

        return Response(
            {
                "message": f"Generation job #{job.id} created and started.",
                "job": GenerationJobSerializer(job).data,
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=["Generation Jobs"],
    parameters=[API_KEY_HEADER],
    responses={
        200: GenerationJobSerializer,
        403: APIErrorSerializer,
        404: APIErrorSerializer,
    },
)
class GenerationJobDetailAPIView(RetrieveAPIView):
    permission_classes = [HasValidAPIKey]
    serializer_class = GenerationJobSerializer
    queryset = GenerationJob.objects.all()


@extend_schema(
    tags=["Generation Jobs"],
    parameters=[API_KEY_HEADER],
)
class GenerationJobStartAPIView(APIView):
    permission_classes = [HasValidAPIKey]

    @extend_schema(
        summary="Start a generation job",
        description="Starts an existing generation job asynchronously.",
        responses={
            200: GenerationJobActionResponseSerializer,
            400: APIErrorSerializer,
            403: APIErrorSerializer,
            404: APIErrorSerializer,
        },
    )
    def post(self, request, job_id):
        job = get_object_or_404(GenerationJob, id=job_id)

        if job.status == "running":
            return Response(
                {
                    "detail": f"Job #{job.id} is already running."
                },
                status=status.HTTP_400_BAD_REQUEST,
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
            ]
        )

        run_generation_job_task.delay(job.id)

        return Response(
            {
                "message": f"Generation job #{job.id} started.",
                "job": GenerationJobSerializer(job).data,
            }
        )


@extend_schema(
    tags=["Generation Jobs"],
    parameters=[API_KEY_HEADER],
)
class GenerationJobStopAPIView(APIView):
    permission_classes = [HasValidAPIKey]

    @extend_schema(
        summary="Stop a running generation job",
        description="Requests a running generation job to stop.",
        responses={
            200: GenerationJobActionResponseSerializer,
            400: APIErrorSerializer,
            403: APIErrorSerializer,
            404: APIErrorSerializer,
        },
    )
    def post(self, request, job_id):
        job = get_object_or_404(GenerationJob, id=job_id)

        if job.status != "running":
            return Response(
                {
                    "detail": f"Job #{job.id} is not running."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        job.should_stop = True
        job.status = "stopped"
        job.error_message = "Job stopped by external API."
        job.save(
            update_fields=[
                "should_stop",
                "status",
                "error_message",
            ]
        )

        return Response(
            {
                "message": f"Generation job #{job.id} stopped.",
                "job": GenerationJobSerializer(job).data,
            }
        )


@extend_schema(
    tags=["Contents"],
    parameters=[
        API_KEY_HEADER,
        OpenApiParameter(
            name="status",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Filter contents by status.",
        ),
        OpenApiParameter(
            name="q",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Search in title, prompt, and generated content.",
        ),
    ],
    responses={
        200: ContentListSerializer(many=True),
        403: APIErrorSerializer,
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
            .order_by("-created_at")
        )

        content_status = self.request.query_params.get("status")
        search_query = self.request.query_params.get("q")

        if content_status:
            queryset = queryset.filter(status=content_status)

        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query)
                | Q(prompt__icontains=search_query)
                | Q(generated_content__icontains=search_query)
            )

        return queryset[:100]


@extend_schema(
    tags=["Contents"],
    parameters=[API_KEY_HEADER],
    responses={
        200: ContentDetailSerializer,
        403: APIErrorSerializer,
        404: APIErrorSerializer,
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
        .prefetch_related("rules")
        .all()
    )