from django.urls import path

from .api.views import (
    ContentDeliveryAPIView,
    ContentDetailAPIView,
    ContentExportAPIView,
    ContentGenerationJobCreateAPIView,
    ContentListAPIView,
    DatasetAPIView,
    GenerationJobDetailAPIView,
    GenerationJobListCreateAPIView,
    GenerationJobStartAPIView,
    GenerationJobStopAPIView,
    GreetingGenerationJobCreateAPIView,
    GreetingExportAPIView,
    HealthCheckAPIView,
    ReplyExportAPIView,
    ReplyGenerationJobCreateAPIView,
)

app_name = "contents"

urlpatterns = [
    # Health
    path(
        "health/",
        HealthCheckAPIView.as_view(),
        name="api-health",
    ),

    # Datasets
    path(
        "datasets/",
        DatasetAPIView.as_view(),
        name="api-datasets",
    ),

    # Generation Jobs
    path(
        "generation-jobs/",
        GenerationJobListCreateAPIView.as_view(),
        name="api-generation-job-list-create",
    ),
    path(
        "generation-jobs/<int:pk>/",
        GenerationJobDetailAPIView.as_view(),
        name="api-generation-job-detail",
    ),
    path(
        "generation-jobs/<int:job_id>/start/",
        GenerationJobStartAPIView.as_view(),
        name="api-generation-job-start",
    ),
    path(
        "generation-jobs/<int:job_id>/stop/",
        GenerationJobStopAPIView.as_view(),
        name="api-generation-job-stop",
    ),

    # Contents
    path(
        "contents/",
        ContentListAPIView.as_view(),
        name="api-content-list",
    ),
    path(
        "contents/<int:pk>/",
        ContentDetailAPIView.as_view(),
        name="api-content-detail",
    ),
    path(
        "contents/<int:pk>/delivery/",
        ContentDeliveryAPIView.as_view(),
        name="api-content-delivery",
    ),

    # Create generation jobs
    path(
        "generation-jobs/content/",
        ContentGenerationJobCreateAPIView.as_view(),
        name="api-content-generation-job-create",
    ),
    path(
        "generation-jobs/reply/",
        ReplyGenerationJobCreateAPIView.as_view(),
        name="api-reply-generation-job-create",
    ),
    path(
        "generation-jobs/greeting/",
        GreetingGenerationJobCreateAPIView.as_view(),
        name="api-greeting-generation-job-create",
    ),

    # Export
    path(
        "contents/export/",
        ContentExportAPIView.as_view(),
        name="api-content-export",
    ),
    path(
        "replies/export/",
        ReplyExportAPIView.as_view(),
        name="api-reply-export",
    ),
    path(
        "greetings/export/",
        GreetingExportAPIView.as_view(),
        name="api-greeting-export",
    ),
]
