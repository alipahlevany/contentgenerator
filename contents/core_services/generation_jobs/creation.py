from dataclasses import dataclass
from typing import Any, Optional

from django.db import transaction

from contents.core_services.client_limits import (
    lock_client_limit,
    validate_generation_limits,
)
from contents.models import GenerationJob
from contents.tasks import queue_generation_job


@dataclass
class GenerationJobCreationResult:
    job: Optional[GenerationJob] = None
    response: Optional[Any] = None

    @property
    def success(self):
        return self.job is not None


def create_generation_job(
    *,
    client,
    serializer,
) -> GenerationJobCreationResult:
    """
    Create and queue a generation job.

    Validation remains in the API serializer. This service owns:
    - client generation limit locking/checking;
    - initial job state;
    - persistence orchestration;
    - Celery dispatch after transaction commit.
    """
    with transaction.atomic():
        lock_client_limit(
            client.pk,
            "generation",
        )

        limit_response = validate_generation_limits(
            client,
            serializer.validated_data["count"],
            serializer.validated_data.get("generation_type"),
        )

        if limit_response is not None:
            return GenerationJobCreationResult(
                response=limit_response,
            )

        job = serializer.save(
            external_client=client,
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
        generation_type = job.generation_type

        transaction.on_commit(
            lambda: queue_generation_job(job_id, generation_type)
        )

    return GenerationJobCreationResult(
        job=job,
    )
