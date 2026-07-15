from django.urls import path

from .views import (
    ContentDetailAPIView,
    ContentExportAPIView,
    ContentListAPIView,
    DatasetAPIView,
    GenerationJobDetailAPIView,
    GenerationJobListCreateAPIView,
    GenerationJobStartAPIView,
    GenerationJobStopAPIView,
    HealthCheckAPIView,
)


app_name = "contents"


urlpatterns = [
    path(
        "health/",
        HealthCheckAPIView.as_view(),
        name="api-health",
    ),

    path(
        "datasets/",
        DatasetAPIView.as_view(),
        name="api-datasets",
    ),

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

    path(
        "contents/export/",
        ContentExportAPIView.as_view(),
        name="api-content-export",
    ),
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
]
