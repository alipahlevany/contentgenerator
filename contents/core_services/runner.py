from contents.core_services.logger import log_job


def reset_job_for_start(job):
    """
    Start or resume a generation job.

    Existing progress is preserved so a stopped job continues
    from its previous generated and skipped counts.
    """
    job.status = "running"
    job.error_message = ""
    job.should_stop = False

    job.save(
        update_fields=[
            "status",
            "error_message",
            "should_stop",
            "updated_at",
        ]
    )


def mark_job_completed(job):
    job.status = "completed"
    job.error_message = ""

    job.save(
        update_fields=[
            "status",
            "error_message",
            "updated_at",
        ]
    )

    log_job(
        job,
        "success",
        "Job completed successfully.",
    )


def mark_job_stopped(job):
    job.status = "stopped"
    job.error_message = "Job stopped by admin."

    job.save(
        update_fields=[
            "status",
            "error_message",
            "updated_at",
        ]
    )

    log_job(
        job,
        "warning",
        "Job stopped by admin.",
    )


def increment_skipped(job):
    job.skipped_count += 1
    job.current_step += 1

    job.save(
        update_fields=[
            "skipped_count",
            "current_step",
            "updated_at",
        ]
    )


def increment_generated(job):
    job.generated_count += 1
    job.current_step += 1

    job.save(
        update_fields=[
            "generated_count",
            "current_step",
            "updated_at",
        ]
    )