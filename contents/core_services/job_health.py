"""Recover abandoned generation jobs without competing with a live worker."""
import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from contents.models import GenerationJob
from contents.core_services.generation.lock import generation_job_lock
from contents.core_services.logger import log_job
from contents.core_services.runner import mark_job_completed


logger = logging.getLogger(__name__)
STUCK_JOB_MINUTES = 5
PENDING_JOB_MINUTES = 60
MAX_AUTOMATIC_RECOVERIES = 3


def find_stuck_jobs():
    now = timezone.now()
    # Unstarted pending jobs may be admin drafts. Only recover pending work
    # with evidence that it previously ran (or was explicitly recovered).
    stale = Q(status="running", updated_at__lt=now - timedelta(minutes=STUCK_JOB_MINUTES))
    stale |= (
        Q(status="pending", updated_at__lt=now - timedelta(minutes=PENDING_JOB_MINUTES))
        & (Q(last_attempt_at__isnull=False) | Q(recovery_count__gt=0))
    )
    return GenerationJob.objects.filter(stale, should_stop=False)


def recover_stuck_jobs():
    from contents.tasks import queue_generation_job

    recovered_count = 0
    for job_id in find_stuck_jobs().values_list("pk", flat=True).iterator():
        # The same PostgreSQL session lock guards the actual generation loop.
        # A slow but live worker must never be failed or queued a second time.
        with generation_job_lock(job_id) as acquired:
            if not acquired:
                continue
            with transaction.atomic():
                # Recheck after locking: another recovery or a user may have
                # updated/stopped the job since the initial scan.
                job = find_stuck_jobs().select_for_update().filter(pk=job_id).first()
                if job is None:
                    continue
                if job.generated_count >= job.count:
                    mark_job_completed(job)
                    continue
                if job.recovery_count >= MAX_AUTOMATIC_RECOVERIES:
                    job.status = "failed"
                    job.error_message = (
                        "Automatic recovery limit reached; saved progress is preserved. "
                        "Inspect the worker and use Resume to retry."
                    )
                    job.save(update_fields=["status", "error_message", "updated_at"])
                    log_job(job, "error", job.error_message)
                    continue
                job.recovery_count += 1
                job.status = "pending"
                job.error_message = (
                    f"Interrupted generation queued for recovery "
                    f"({job.recovery_count}/{MAX_AUTOMATIC_RECOVERIES}); "
                    f"continuing from {job.generated_count}/{job.count}."
                )
                job.save(update_fields=["status", "recovery_count", "error_message", "updated_at"])
                log_job(job, "warning", job.error_message)
                generation_type = job.generation_type

        # Publish after both the transaction and worker lock are released.
        # If publication/process dies here, the stale pending scan repairs it.
        try:
            queue_generation_job(job_id, generation_type, auto_resume=True)
        except Exception:
            logger.exception("Unable to dispatch recovered generation job %s", job_id)
        else:
            recovered_count += 1
    return recovered_count
