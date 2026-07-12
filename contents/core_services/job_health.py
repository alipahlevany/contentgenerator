from datetime import timedelta

from django.utils import timezone

from contents.models import GenerationJob
from contents.core_services.logger import log_job


STUCK_JOB_MINUTES = 60


def find_stuck_jobs():
    threshold = timezone.now() - timedelta(minutes=STUCK_JOB_MINUTES)

    return GenerationJob.objects.filter(
        status="running",
        updated_at__lt=threshold,
    )


def recover_stuck_jobs():
    stuck_jobs = find_stuck_jobs()

    recovered_count = 0

    for job in stuck_jobs:
        job.status = "failed"
        job.error_message = (
            f"Job marked as failed automatically because it was stuck "
            f"for more than {STUCK_JOB_MINUTES} minutes."
        )
        job.save(update_fields=["status", "error_message", "updated_at"])

        log_job(
            job,
            "error",
            f"Auto recovery: job was stuck for more than {STUCK_JOB_MINUTES} minutes.",
        )

        recovered_count += 1

    return recovered_count