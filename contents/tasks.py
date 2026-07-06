from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from contents.core_services.job_health import recover_stuck_jobs

from .models import AppSettings, GenerationJob
from .services import run_generation_job


@shared_task
def run_generation_job_task(job_id):
    run_generation_job(job_id)


@shared_task
def run_daily_generation_task(force=False):
    lock_key = "daily_generation_task_lock"
    lock_created = cache.add(lock_key, "locked", timeout=60 * 10)

    if not lock_created:
        return "Daily generation is already being checked."

    try:
        app_settings = (
            AppSettings.objects
            .filter(is_active=True)
            .order_by("-id")
            .first()
        )

        if not app_settings:
            return "No active AppSettings found."

        if not force and not app_settings.auto_daily_generation_enabled:
            return "Daily generation is disabled."

        now = timezone.localtime()
        today = now.date()

        if not force:
            target_minutes = (
                app_settings.daily_generation_hour * 60
                + app_settings.daily_generation_minute
            )

            current_minutes = now.hour * 60 + now.minute

            if current_minutes < target_minutes:
                return "Daily generation time has not arrived yet."

            if app_settings.last_daily_generation_date == today:
                return "Daily generation already ran today."

        has_active_job = GenerationJob.objects.filter(
            status__in=[
                "pending",
                "running",
            ]
        ).exists()

        if has_active_job:
            return "Another generation job is already pending or running."

        job = GenerationJob.objects.create(
            count=app_settings.daily_generation_count,
            delay_seconds=app_settings.daily_generation_delay_seconds,
        )

        app_settings.last_daily_generation_date = today
        app_settings.save(
            update_fields=[
                "last_daily_generation_date",
            ]
        )

        run_generation_job_task.delay(job.id)

        return f"Daily generation job #{job.id} created and started."

    finally:
        cache.delete(lock_key)


@shared_task
def recover_stuck_generation_jobs():
    return recover_stuck_jobs()