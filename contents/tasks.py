import logging
import uuid

import requests
from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from contents.core_services.job_health import recover_stuck_jobs
from contents.core_services.delivery import RetryableDeliveryError, deliver_content
from contents.core_services.warmup_template_renderer import WarmupTemplateError
from contents.core_services.warmup_runs import (
    get_manual_batch,
    record_batch_dispatch,
    record_template_progress,
)
from contents.core_services.warmup_templates import (
    WarmupTemplateInProgress,
    generate_warmup_template,
    photo_source_status,
)
from contents.models import AppSettings, GenerationJob
from contents.services import run_generation_job


logger = logging.getLogger(__name__)
WARMUP_RETRYABLE_ERRORS = (
    requests.RequestException,
    WarmupTemplateInProgress,
)


GENERATION_QUEUE_BY_TYPE = {
    "standard": "generation_standard",
    "email_reply": "generation_reply",
    "greeting": "generation_greeting",
}


def get_generation_queue(generation_type):
    return GENERATION_QUEUE_BY_TYPE.get(
        generation_type,
        GENERATION_QUEUE_BY_TYPE["standard"],
    )


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


@shared_task(bind=True)
def run_generation_job_task(self, job_id, auto_resume=False):
    if auto_resume:
        job = GenerationJob.objects.filter(pk=job_id).first()
        if not job or job.status != "pending":
            logger.info(
                "Generation job auto-resume skipped | "
                "job_id=%s | status=%s",
                job_id,
                getattr(job, "status", None),
            )
            return

    logger.info(
        "Generation job task started | job_id=%s | auto_resume=%s",
        job_id,
        auto_resume,
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


def queue_generation_job(
    job_id,
    generation_type=None,
    *,
    auto_resume=False,
    countdown=None,
):
    if generation_type is None:
        generation_type = (
            GenerationJob.objects
            .filter(pk=job_id)
            .values_list("generation_type", flat=True)
            .first()
        )

    queue = get_generation_queue(generation_type)
    kwargs = {}

    if auto_resume:
        kwargs["auto_resume"] = True

    # Persist intent before publishing: broker failure must remain recoverable
    # even when this job has not made its first generation attempt yet.
    now = timezone.now()
    GenerationJob.objects.filter(pk=job_id).update(dispatch_requested_at=now, updated_at=now)
    return run_generation_job_task.apply_async(
        args=[job_id],
        kwargs=kwargs,
        queue=queue,
        routing_key=queue,
        countdown=countdown,
    )




@shared_task
def run_daily_warmup_template_task(force=False, batch_key=None):
    """Schedule the configured number of independent daily template jobs."""
    lock_key = "daily_warmup_template_task_lock"
    if not cache.add(lock_key, "locked", timeout=60 * 10):
        record_batch_dispatch(batch_key, 0, "Another batch is being scheduled. Please try again shortly.")
        return "Warmup template scheduling is already in progress."

    accepted = 0
    def reject(message):
        record_batch_dispatch(batch_key, 0, message)
        return message

    try:
        manual = get_manual_batch(batch_key) if batch_key else None
        if batch_key and (not force or manual is None):
            return "Manual batch progress has expired. Please submit a new request."
        app_settings = (
            AppSettings.objects.filter(is_active=True).order_by("-id").first()
        )
        if not app_settings:
            return reject("No active generation settings found.")
        if not force and not app_settings.auto_daily_warmup_template_enabled:
            return "Daily warmup template generation is disabled."

        now = timezone.localtime()
        today = now.date()
        if not force:
            target_minutes = (
                app_settings.daily_warmup_template_hour * 60
                + app_settings.daily_warmup_template_minute
            )
            if now.hour * 60 + now.minute < target_minutes:
                return "Daily warmup template generation time has not arrived yet."
            if app_settings.last_daily_warmup_template_date == today:
                return "Daily warmup templates already ran today."

        source = photo_source_status()
        config_error = source["error"]
        if config_error:
            if cache.add(f"warmup-template-config-error:{today}", 1, timeout=86400):
                logger.error("Warmup template generation skipped: %s", config_error)
            return reject(config_error)

        count = manual["count"] if manual else app_settings.daily_warmup_template_count
        delay = manual["delay"] if manual else app_settings.daily_warmup_template_delay_seconds
        if not 1 <= count <= 50 or delay < 0:
            return reject("Warmup template count or delay is outside its allowed range.")
        batch_key = batch_key or (
            f"{today.isoformat()}-manual-{uuid.uuid4().hex[:10]}"
            if force else today.isoformat()
        )
        run_date = manual["run_date"] if manual else today.isoformat()
        for sequence in range(count):
            generate_warmup_template_task.apply_async(
                args=[run_date, sequence, batch_key],
                countdown=sequence * delay,
                queue="generation_standard",
                routing_key="generation_standard",
            )
            accepted += 1
        record_batch_dispatch(batch_key, accepted)

        if not force:
            app_settings.last_daily_warmup_template_date = today
            app_settings.save(update_fields=["last_daily_warmup_template_date"])
        logger.info(
            "Warmup templates queued | count=%s | batch=%s", count, batch_key
        )
        return f"Queued {count} warmup templates in batch {batch_key}."
    except Exception:
        record_batch_dispatch(batch_key, accepted, "Some templates could not be queued. Saved results remain available below.")
        logger.exception("Daily warmup template scheduling failed.")
        raise
    finally:
        cache.delete(lock_key)


def _record_warmup_template_failure(run_date, sequence, exc):
    """Persist the last terminal failure for the settings screen."""
    try:
        app_settings = AppSettings.objects.filter(is_active=True).order_by("-id").first()
        if not app_settings:
            return
        detail = (
            " ".join(str(exc).split())[:400]
            if isinstance(exc, WarmupTemplateError)
            else type(exc).__name__
        )
        app_settings.last_warmup_template_error = (
            f"{run_date} #{int(sequence) + 1}: {detail}"
        )
        app_settings.last_warmup_template_error_at = timezone.now()
        app_settings.save(update_fields=[
            "last_warmup_template_error",
            "last_warmup_template_error_at",
        ])
    except Exception:
        logger.exception("Unable to record warmup template failure.")


@shared_task(
    bind=True,
    autoretry_for=WARMUP_RETRYABLE_ERRORS,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def generate_warmup_template_task(self, run_date, sequence, batch_key=None):
    from datetime import date

    try:
        record_template_progress(batch_key, int(sequence), "generating")
        content = generate_warmup_template(
            run_date=date.fromisoformat(run_date),
            sequence=int(sequence),
            batch_key=batch_key,
        )
    except Exception as exc:
        if not isinstance(exc, WARMUP_RETRYABLE_ERRORS) or self.request.retries >= 3:
            detail = str(exc)[:400] if isinstance(exc, WarmupTemplateError) else "The template could not be created after retries. Please try again."
            record_template_progress(batch_key, int(sequence), "failed", detail)
            _record_warmup_template_failure(run_date, sequence, exc)
            logger.exception(
                "Warmup template generation failed | date=%s | sequence=%s",
                run_date, sequence,
            )
        else:
            record_template_progress(batch_key, int(sequence), "retrying")
            logger.warning(
                "Warmup template generation will retry | date=%s | sequence=%s | attempt=%s",
                run_date, sequence, self.request.retries + 1,
            )
        raise
    record_template_progress(batch_key, int(sequence), "complete")
    return {"content_id": content.pk, "title": content.title}


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

        has_active_standard_job = GenerationJob.objects.filter(
            generation_type="standard",
            status__in=[
                "pending",
                "running",
            ]
        ).exists()

        if has_active_standard_job:
            logger.warning(
                "Daily generation skipped because another "
                "standard job is pending or running."
            )

            return (
                "Another standard generation job is already "
                "pending or running."
            )

        job = GenerationJob.objects.create(
            generation_type="standard",
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

        task_result = queue_generation_job(
            job.id,
            job.generation_type,
        )

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

        task_result = queue_generation_job(
            job.id,
            job.generation_type,
        )

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
def run_daily_greeting_generation_task(force=False):
    logger.info(
        "Daily greeting generation task started | force=%s",
        force,
    )

    lock_key = "daily_greeting_generation_task_lock"

    lock_created = cache.add(
        lock_key,
        "locked",
        timeout=60 * 10,
    )

    if not lock_created:
        logger.warning(
            "Daily greeting generation skipped because lock exists."
        )
        return (
            "Daily greeting generation is already being checked."
        )

    try:
        app_settings = (
            AppSettings.objects
            .filter(is_active=True)
            .order_by("-id")
            .first()
        )

        if not app_settings:
            logger.error(
                "Daily greeting generation failed: "
                "no active AppSettings."
            )
            return "No active AppSettings found."

        if (
            not force
            and not (
                app_settings
                .auto_daily_greeting_generation_enabled
            )
        ):
            logger.info(
                "Daily greeting generation skipped because "
                "it is disabled."
            )
            return "Daily greeting generation is disabled."

        now = timezone.localtime()
        today = now.date()

        if not force:
            target_minutes = (
                app_settings.daily_greeting_generation_hour * 60
                + app_settings.daily_greeting_generation_minute
            )

            current_minutes = (
                now.hour * 60
                + now.minute
            )

            if current_minutes < target_minutes:
                logger.info(
                    "Daily greeting generation time has not "
                    "arrived | current=%s:%s | target=%s:%s",
                    now.hour,
                    now.minute,
                    app_settings.daily_greeting_generation_hour,
                    app_settings.daily_greeting_generation_minute,
                )

                return (
                    "Daily greeting generation time has not "
                    "arrived yet."
                )

            if (
                app_settings
                .last_daily_greeting_generation_date
                == today
            ):
                logger.info(
                    "Daily greeting generation already ran "
                    "today | date=%s",
                    today,
                )

                return (
                    "Daily greeting generation already ran today."
                )

        has_active_greeting_job = (
            GenerationJob.objects.filter(
                generation_type="greeting",
                status__in=[
                    "pending",
                    "running",
                ],
            ).exists()
        )

        if has_active_greeting_job:
            logger.warning(
                "Daily greeting generation skipped because "
                "another greeting job is pending or running."
            )

            return (
                "Another greeting generation job is already "
                "pending or running."
            )

        job = GenerationJob.objects.create(
            generation_type="greeting",
            count=(
                app_settings.daily_greeting_generation_count
            ),
            delay_seconds=(
                app_settings
                .daily_greeting_generation_delay_seconds
            ),
        )

        logger.info(
            "Daily greeting generation job created | "
            "job_id=%s | count=%s | delay=%s",
            job.id,
            job.count,
            job.delay_seconds,
        )

        app_settings.last_daily_greeting_generation_date = (
            today
        )

        app_settings.save(
            update_fields=[
                "last_daily_greeting_generation_date",
            ]
        )

        task_result = queue_generation_job(
            job.id,
            job.generation_type,
        )

        logger.info(
            "Daily greeting generation job queued | "
            "job_id=%s | celery_task_id=%s",
            job.id,
            task_result.id,
        )

        return (
            f"Daily greeting generation job #{job.id} "
            "created and started."
        )

    except Exception:
        logger.exception(
            "Daily greeting generation task failed "
            "unexpectedly."
        )
        raise

    finally:
        cache.delete(lock_key)

        logger.info(
            "Daily greeting generation lock released."
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


@shared_task(queue="delivery")
def send_melal_template(pk):
    from contents.core_services.melal_templates import send_template
    return send_template(pk)


@shared_task(queue="maintenance")
def dispatch_melal_templates():
    from django.conf import settings
    from contents.models import MelalTemplateDelivery
    from contents.core_services.melal_templates import dispatch
    if not settings.MELAL_TEMPLATE_ENABLED:
        return
    ids = MelalTemplateDelivery.objects.filter(
        status="pending", next_attempt_at__lte=timezone.now(),
    ).order_by("next_attempt_at").values_list("pk", flat=True)[:50]
    for pk in ids:
        dispatch(pk)


@shared_task(queue="maintenance")
def recover_callback_deliveries():
    from contents.core_services.delivery_queue import recover_pending_deliveries
    return recover_pending_deliveries()
