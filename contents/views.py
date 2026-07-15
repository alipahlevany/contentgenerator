from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

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
    ListAPIView,
    RetrieveAPIView,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Audience,
    Content,
    ContentExport,
    ContentRule,
    GenerationJob,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)
from .permissions import HasValidAPIKey
from .serializers import (
    APIErrorSerializer,
    ContentDetailSerializer,
    ContentExportItemSerializer,
    ContentExportRequestSerializer,
    ContentExportResponseSerializer,
    ContentListSerializer,
    GenerationJobActionResponseSerializer,
    GenerationJobCreateSerializer,
    GenerationJobSerializer,
    HealthCheckSerializer,
    DatasetCollectionSerializer,
    LanguageDatasetSerializer,
    NamedDatasetSerializer,
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


DATASET_TYPE_PARAMETER = OpenApiParameter(
    name="type",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.QUERY,
    required=False,
    enum=[
        "languages",
        "topics",
        "audiences",
        "goals",
        "rules",
        "prompt_templates",
    ],
    description=(
        "Optional dataset type. Leave it empty to return all active "
        "generation datasets."
    ),
)


@extend_schema(
    tags=["System"],
    summary="Check API health",
    description=(
        "Public health-check endpoint used to verify that the "
        "Content Generator API is online and responding."
    ),
    auth=[],
    responses={
        200: OpenApiResponse(
            response=HealthCheckSerializer,
            description="The API service is online.",
        ),
    },
    examples=[
        OpenApiExample(
            name="Healthy service",
            value={
                "status": "ok",
                "service": "content-generator",
            },
            response_only=True,
            status_codes=["200"],
        ),
    ],
)
class HealthCheckAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                "status": "ok",
                "service": "content-generator",
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["Datasets"],
    parameters=[
        API_KEY_HEADER,
        DATASET_TYPE_PARAMETER,
    ],
)
class DatasetAPIView(APIView):
    permission_classes = [HasValidAPIKey]

    dataset_map = {
        "languages": (
            Language,
            LanguageDatasetSerializer,
        ),
        "topics": (
            Topic,
            NamedDatasetSerializer,
        ),
        "audiences": (
            Audience,
            NamedDatasetSerializer,
        ),
        "goals": (
            Goal,
            NamedDatasetSerializer,
        ),
        "rules": (
            ContentRule,
            NamedDatasetSerializer,
        ),
        "prompt_templates": (
            PromptTemplate,
            NamedDatasetSerializer,
        ),
    }

    @extend_schema(
        summary="Retrieve active generation datasets",
        description=(
            "Returns active languages, topics, audiences, goals, content "
            "rules, and prompt templates. Pass the optional `type` query "
            "parameter to retrieve only one dataset group."
        ),
        responses={
            200: OpenApiResponse(
                response=DatasetCollectionSerializer,
                description="Active datasets retrieved successfully.",
            ),
            400: OpenApiResponse(
                response=APIErrorSerializer,
                description="Unsupported dataset type.",
            ),
            403: OpenApiResponse(
                response=APIErrorSerializer,
                description="Missing or invalid API key.",
            ),
        },
        examples=[
            OpenApiExample(
                name="All datasets",
                value={
                    "languages": [
                        {
                            "id": 1,
                            "name": "English",
                            "code": "en",
                        }
                    ],
                    "topics": [
                        {
                            "id": 10,
                            "name": "Technology",
                        }
                    ],
                    "audiences": [],
                    "goals": [],
                    "rules": [],
                    "prompt_templates": [],
                },
                response_only=True,
                status_codes=["200"],
            ),
        ],
    )
    def get(self, request):
        dataset_type = request.query_params.get("type")

        if dataset_type:
            config = self.dataset_map.get(dataset_type)

            if config is None:
                return Response(
                    {
                        "detail": (
                            "Invalid dataset type. Supported values are: "
                            + ", ".join(self.dataset_map.keys())
                            + "."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            model, serializer_class = config

            queryset = (
                model.objects
                .filter(is_active=True)
                .order_by("name")
            )

            return Response(
                {
                    dataset_type: serializer_class(
                        queryset,
                        many=True,
                    ).data
                },
                status=status.HTTP_200_OK,
            )

        response_data = {}

        for key, (model, serializer_class) in self.dataset_map.items():
            queryset = (
                model.objects
                .filter(is_active=True)
                .order_by("name")
            )

            response_data[key] = serializer_class(
                queryset,
                many=True,
            ).data

        return Response(
            response_data,
            status=status.HTTP_200_OK,
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
            .all()
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
    queryset = GenerationJob.objects.all()


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
        job = get_object_or_404(
            GenerationJob,
            id=job_id,
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

        job.status = "pending"
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
        job = get_object_or_404(
            GenerationJob,
            id=job_id,
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
            .order_by("-created_at")
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

        return queryset[:100]


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
        request_serializer = ContentExportRequestSerializer(
            data=request.data,
        )
        request_serializer.is_valid(raise_exception=True)

        validated_data = request_serializer.validated_data
        requested_count = validated_data["count"]
        client = request.client

        exported_contents = []

        with transaction.atomic():
            queryset = self._build_queryset(
                validated_data,
                client,
            ).select_for_update(of=("self",))

            candidates = list(
                queryset[:requested_count]
            )

            for content in candidates:
                try:
                    ContentExport.objects.create(
                        content=content,
                        client=client,
                        content_hash=content.content_hash,
                        status="success",
                        exported_at=timezone.now(),
                    )
                except IntegrityError:
                    continue

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



