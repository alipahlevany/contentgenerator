from django.urls import path

from .views import (
    ContentListAPIView,
    GenerateContentAPIView,
    start_job_api,
    stop_job_api,
    job_status_api,
    run_default_job_api,
)

urlpatterns = [
    path("contents/", ContentListAPIView.as_view(), name="content-list"),
    path("generate-content/", GenerateContentAPIView.as_view(), name="generate-content"),

    path("run/", run_default_job_api, name="default-job-run"),

    path("jobs/<int:job_id>/start/", start_job_api, name="job-start"),
    path("jobs/<int:job_id>/stop/", stop_job_api, name="job-stop"),
    path("jobs/<int:job_id>/status/", job_status_api, name="job-status"),
]