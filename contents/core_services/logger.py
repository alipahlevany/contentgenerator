from contents.models import GenerationJobLog


def log_job(job, level, message):
    GenerationJobLog.objects.create(
        job=job,
        level=level,
        message=message,
    )

    print(f"[Job #{job.id}] {level.upper()}: {message}")


def fail_job(job, message):
    job.status = "failed"
    job.error_message = message
    job.save(update_fields=["status", "error_message"])

    log_job(job, "error", message)