from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.shortcuts import get_object_or_404

from contents.models import GenerationJob
from contents.tasks import run_generation_job_task


@dataclass
class GenerationJobActionResult:
    job: Optional[GenerationJob]
    message: str
    error: Optional[str] = None

    @property
    def success(self):
        return self.error is None


def start_generation_job(
    *,
    job_id,
    external_client,
):
    with transaction.atomic():
        job = get_object_or_404(
            GenerationJob.objects.select_for_update(),
            id=job_id,
            external_client=external_client,
        )

        if job.status == "running":
            return GenerationJobActionResult(
                job=job,
                message="",
                error=f"Job #{job.id} is already running.",
            )

        if job.generated_count >= job.count:
            return GenerationJobActionResult(
                job=job,
                message="",
                error=(
                    f"Job #{job.id} is already completed "
                    f"({job.generated_count}/{job.count})."
                ),
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
            lambda: run_generation_job_task.delay(job.id)
        )

        action_text = (
            "resumed"
            if has_existing_progress
            else "started"
        )

        return GenerationJobActionResult(
            job=job,
            message=(
                f"Generation job #{job.id} "
                f"{action_text}."
            ),
        )


def stop_generation_job(
    *,
    job_id,
    external_client,
):
    with transaction.atomic():
        job = get_object_or_404(
            GenerationJob.objects.select_for_update(),
            id=job_id,
            external_client=external_client,
        )

        if job.status not in [
            "pending",
            "running",
        ]:
            return GenerationJobActionResult(
                job=job,
                message="",
                error=(
                    f"Job #{job.id} is not pending "
                    "or running."
                ),
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

        return GenerationJobActionResult(
            job=job,
            message=f"Generation job #{job.id} stopped.",
        )
