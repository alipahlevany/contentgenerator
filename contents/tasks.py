import logging

import requests
from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from contents.core_services.job_health import recover_stuck_jobs
from contents.core_services.delivery import RetryableDeliveryError, deliver_content
from contents.models import AppSettings, GenerationJob
from contents.services import run_generation_job


logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    queue="delivery",
    routing_key="delivery",
    autoretry_for=(RetryableDeliveryError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def deliver_content_callback(self, delivery_id):
    delivery = deliver_content(delivery_id)
    return {
        "delivery_id": delivery.pk,
        "status": delivery.status,
        "attempt_count": delivery.attempt_count,
    }


@shared_task
def run_generation_job_task(job_id):
    logger.info(
        "Generation job task started | job_id=%s",
        job_id,
    )

    try:
        run_generation_job(job_id)

        logger.info(
            "Generation job task finished | job_id=%s",
            job_id,
        )

    except Exception:
        logger.exception(
            "Generation job task failed | job_id=%s",
            job_id,
        )
        raise


@shared_task
def run_daily_generation_task(force=False):
    logger.info(
        "Daily generation task started | force=%s",
        force,
    )

    lock_key = "daily_generation_task_lock"

    lock_created = cache.add(
        lock_key,
        "locked",
        timeout=60 * 10,
    )

    if not lock_created:
        logger.warning(
            "Daily generation task skipped because lock exists."
        )
        return "Daily generation is already being checked."

    try:
        app_settings = (
            AppSettings.objects
            .filter(is_active=True)
            .order_by("-id")
            .first()
        )

        if not app_settings:
            logger.error(
                "Daily generation failed: no active AppSettings."
            )
            return "No active AppSettings found."

        if (
            not force
            and not app_settings.auto_daily_generation_enabled
        ):
            logger.info(
                "Daily generation skipped because it is disabled."
            )
            return "Daily generation is disabled."

        now = timezone.localtime()
        today = now.date()

        if not force:
            target_minutes = (
                app_settings.daily_generation_hour * 60
                + app_settings.daily_generation_minute
            )

            current_minutes = (
                now.hour * 60
                + now.minute
            )

            if current_minutes < target_minutes:
                logger.info(
                    "Daily generation time has not arrived | "
                    "current=%s:%s | target=%s:%s",
                    now.hour,
                    now.minute,
                    app_settings.daily_generation_hour,
                    app_settings.daily_generation_minute,
                )

                return (
                    "Daily generation time has not arrived yet."
                )

            if app_settings.last_daily_generation_date == today:
                logger.info(
                    "Daily generation already ran today | date=%s",
                    today,
                )

                return "Daily generation already ran today."

        has_active_job = GenerationJob.objects.filter(
            status__in=[
                "pending",
                "running",
            ]
        ).exists()

        if has_active_job:
            logger.warning(
                "Daily generation skipped because another job "
                "is pending or running."
            )

            return (
                "Another generation job is already "
                "pending or running."
            )

        job = GenerationJob.objects.create(
            count=app_settings.daily_generation_count,
            delay_seconds=(
                app_settings.daily_generation_delay_seconds
            ),
        )

        logger.info(
            "Daily generation job created | "
            "job_id=%s | count=%s | delay=%s",
            job.id,
            job.count,
            job.delay_seconds,
        )

        app_settings.last_daily_generation_date = today

        app_settings.save(
            update_fields=[
                "last_daily_generation_date",
            ]
        )

        task_result = run_generation_job_task.delay(job.id)

        logger.info(
            "Daily generation job queued | "
            "job_id=%s | celery_task_id=%s",
            job.id,
            task_result.id,
        )

        return (
            f"Daily generation job #{job.id} "
            "created and started."
        )

    except Exception:
        logger.exception(
            "Daily generation task failed unexpectedly."
        )
        raise

    finally:
        cache.delete(lock_key)

        logger.info(
            "Daily generation lock released."
        )


@shared_task
def run_daily_reply_generation_task(force=False):
    logger.info(
        "Daily reply generation task started | force=%s",
        force,
    )

    lock_key = "daily_reply_generation_task_lock"

    lock_created = cache.add(
        lock_key,
        "locked",
        timeout=60 * 10,
    )

    if not lock_created:
        logger.warning(
            "Daily reply generation skipped because lock exists."
        )
        return "Daily reply generation is already being checked."

    try:
        app_settings = (
            AppSettings.objects
            .filter(is_active=True)
            .order_by("-id")
            .first()
        )

        if not app_settings:
            logger.error(
                "Daily reply generation failed: no active AppSettings."
            )
            return "No active AppSettings found."

        if (
            not force
            and not app_settings.auto_daily_reply_generation_enabled
        ):
            logger.info(
                "Daily reply generation skipped because it is disabled."
            )
            return "Daily reply generation is disabled."

        now = timezone.localtime()
        today = now.date()

        if not force:
            target_minutes = (
                app_settings.daily_reply_generation_hour * 60
                + app_settings.daily_reply_generation_minute
            )

            current_minutes = now.hour * 60 + now.minute

            if current_minutes < target_minutes:
                logger.info(
                    "Daily reply generation time has not arrived | "
                    "current=%s:%s | target=%s:%s",
                    now.hour,
                    now.minute,
                    app_settings.daily_reply_generation_hour,
                    app_settings.daily_reply_generation_minute,
                )
                return (
                    "Daily reply generation time has not arrived yet."
                )

            if (
                app_settings.last_daily_reply_generation_date
                == today
            ):
                logger.info(
                    "Daily reply generation already ran today | date=%s",
                    today,
                )
                return "Daily reply generation already ran today."

        has_active_reply_job = GenerationJob.objects.filter(
            generation_type="email_reply",
            status__in=[
                "pending",
                "running",
            ],
        ).exists()

        if has_active_reply_job:
            logger.warning(
                "Daily reply generation skipped because another "
                "email reply job is pending or running."
            )
            return (
                "Another email reply generation job is already "
                "pending or running."
            )

        job = GenerationJob.objects.create(
            generation_type="email_reply",
            count=app_settings.daily_reply_generation_count,
            delay_seconds=(
                app_settings.daily_reply_generation_delay_seconds
            ),
        )

        logger.info(
            "Daily reply generation job created | "
            "job_id=%s | count=%s | delay=%s",
            job.id,
            job.count,
            job.delay_seconds,
        )

        app_settings.last_daily_reply_generation_date = today
        app_settings.save(
            update_fields=[
                "last_daily_reply_generation_date",
            ]
        )

        task_result = run_generation_job_task.delay(job.id)

        logger.info(
            "Daily reply generation job queued | "
            "job_id=%s | celery_task_id=%s",
            job.id,
            task_result.id,
        )

        return (
            f"Daily reply generation job #{job.id} "
            "created and started."
        )

    except Exception:
        logger.exception(
            "Daily reply generation task failed unexpectedly."
        )
        raise

    finally:
        cache.delete(lock_key)

        logger.info(
            "Daily reply generation lock released."
        )


@shared_task
def recover_stuck_generation_jobs():
    logger.info(
        "Recover stuck generation jobs task started."
    )

    try:
        result = recover_stuck_jobs()

        logger.info(
            "Recover stuck generation jobs task finished | "
            "result=%s",
            result,
        )

        return result

    except Exception:
        logger.exception(
            "Recover stuck generation jobs task failed."
        )
        raise


@shared_task(
    bind=True,
    autoretry_for=(
        requests.exceptions.RequestException,
    ),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    retry_kwargs={
        "max_retries": 3,
    },
)
def send_model_data_to_api(
    self,
    title,
    description,
    category,
):
    return {
        "success": False,
        "message": "Legacy automatic delivery is disabled.",
    }
