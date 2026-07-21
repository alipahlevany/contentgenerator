from django.urls import path

from .views import (
    ContentExportAPIView,
    ContentGenerationJobCreateAPIView,
    ReplyExportAPIView,
    ReplyGenerationJobCreateAPIView,
)


app_name = "contents"


urlpatterns = [
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
        "contents/export/",
        ContentExportAPIView.as_view(),
        name="api-content-export",
    ),
    path(
        "replies/export/",
        ReplyExportAPIView.as_view(),
        name="api-reply-export",
    ),
]
