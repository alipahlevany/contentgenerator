from contents.core_services.logger import log_job


def reset_job_for_start(job):
    job.status = "running"
    job.error_message = ""
    job.generated_count = 0
    job.skipped_count = 0
    job.current_step = 0
    job.should_stop = False
    job.save(
        update_fields=[
            "status",
            "error_message",
            "generated_count",
            "skipped_count",
            "current_step",
            "should_stop",
        ]
    )


def mark_job_completed(job):
    job.status = "completed"
    job.error_message = ""
    job.save(update_fields=["status", "error_message"])

    log_job(job, "success", "Job completed successfully.")


def mark_job_stopped(job):
    job.status = "stopped"
    job.error_message = "Job stopped by admin."
    job.save(update_fields=["status", "error_message"])

    log_job(job, "warning", "Job stopped by admin.")


def increment_skipped(job):
    job.skipped_count += 1
    job.current_step += 1
    job.save(update_fields=["skipped_count", "current_step"])


def increment_generated(job):
    job.generated_count += 1
    job.current_step += 1
    job.save(update_fields=["generated_count", "current_step"])