import random
from dataclasses import dataclass
import time

from django.utils import timezone

from contents.core_services.ai import generate_content
from contents.core_services.cache import get_app_settings
from contents.core_services.duplicate import is_duplicate_content
from contents.core_services.delivery_queue import queue_content_deliveries
from contents.core_services.generation.reservation import (
    reserve_generation_context,
)
from contents.core_services.generation.fingerprint import (
    complete_fingerprint,
    fail_fingerprint,
)
from contents.core_services.generation_outcome import (
    handle_generation_failure,
    handle_generation_success,
)
from contents.core_services.datasets.job_pool_v2 import get_job_generation_pool_v2
from contents.core_services.pipeline.blocked_keywords import (
    contains_blocked_keyword,
    remove_blocked_keywords,
)
from contents.core_services.pipeline.validator import (
    validate_content_body,
    validate_final_blocked_keyword,
    validate_generated_text,
)
from contents.core_services.logger import fail_job, log_job
from contents.core_services.generators.base import GeneratorOutputError
from contents.core_services.generators.factory import get_generator
from contents.core_services.runner import (
    increment_generated,
    mark_job_completed,
    pause_job_for_resume,
    mark_job_stopped,
    reset_job_for_start,
)
from contents.models import Content, GenerationJob


MAX_GENERATED_ITEMS_PER_RUN = 100
MAX_GENERATION_ATTEMPTS_PER_RUN = 250


def _get_generation_run_limits(
    *,
    job,
    app_settings,
):
    target_count = job.count

    max_attempts = job.max_attempts or max(
        (
            target_count
            * app_settings.generation_attempt_multiplier
        ),
        app_settings.generation_minimum_attempts,
    )

    max_runtime_seconds = (
        app_settings.generation_max_runtime_seconds
    )

    return (
        target_count,
        max_attempts,
        max_runtime_seconds,
    )


def _build_generation_pool_summary(
    generation_pool,
):
    return ", ".join(
        (
            f"{dataset_key}: "
            f"{len(dataset_config['items'])}"
        )
        for dataset_key, dataset_config
        in generation_pool.items()
    )


def _record_generation_attempt(job):
    job.attempted_count += 1
    job.last_attempt_at = timezone.now()

    job.save(
        update_fields=[
            "attempted_count",
            "last_attempt_at",
            "updated_at",
        ]
    )


def _runtime_limit_reached(
    *,
    run_started_at,
    max_runtime_seconds,
):
    return (
        time.monotonic() - run_started_at
        >= max_runtime_seconds
    )


def _run_slice_limit_reached(
    *,
    job,
    run_started_generated_count,
    run_started_attempted_count,
):
    generated_in_run = (
        job.generated_count - run_started_generated_count
    )
    attempted_in_run = (
        job.attempted_count - run_started_attempted_count
    )

    return (
        generated_in_run >= MAX_GENERATED_ITEMS_PER_RUN
        or attempted_in_run >= MAX_GENERATION_ATTEMPTS_PER_RUN
    )


def _pause_job_and_schedule_resume(job, message):
    pause_job_for_resume(job, message)

    from contents.tasks import queue_generation_job

    queue_generation_job(
        job.id,
        job.generation_type,
        auto_resume=True,
        countdown=2,
    )



@dataclass
class PreparedGenerationOutput:
    ok: bool
    title: str = ""
    content_body: str = ""
    event_type: str = ""
    message: str = ""
    failure_kind: str = ""


def _prepare_generated_output(
    *,
    job,
    generator,
    generated_text,
    fallback_title,
):
    generated_validation = validate_generated_text(
        generated_text
    )

    if not generated_validation.ok:
        return PreparedGenerationOutput(
            ok=False,
            event_type=generated_validation.event_type,
            message=generated_validation.message,
            failure_kind=(
                generated_validation.failure_kind
            ),
        )

    has_blocked_keyword, blocked_keyword = (
        contains_blocked_keyword(generated_text)
    )

    if has_blocked_keyword:
        generated_text = remove_blocked_keywords(
            generated_text
        )

        still_blocked, remaining_keyword = (
            contains_blocked_keyword(generated_text)
        )

        if still_blocked:
            return PreparedGenerationOutput(
                ok=False,
                event_type="blocked",
                message=(
                    "Blocked keyword remained after cleanup: "
                    f"{remaining_keyword}"
                ),
                failure_kind="failed",
            )

        if not generated_text.strip():
            return PreparedGenerationOutput(
                ok=False,
                event_type="blocked",
                message=(
                    "Generated content became empty after "
                    "blocked keyword cleanup."
                ),
                failure_kind="empty",
            )

        log_job(
            job,
            "warning",
            (
                "Blocked keyword removed before saving: "
                f"{blocked_keyword}"
            ),
        )

    try:
        title, content_body = generator.extract_output(
            generated_text,
            fallback_title,
        )
    except GeneratorOutputError as exc:
        # A format/length violation belongs to this attempt. Let the
        # generation loop reserve a fresh context and retry instead of
        # failing the entire job.
        return PreparedGenerationOutput(
            ok=False,
            event_type="validation",
            message=str(exc),
            failure_kind="failed",
        )

    title = title.strip()
    content_body = content_body.strip()

    if not title:
        title = fallback_title

    body_validation = validate_content_body(
        content_body
    )

    if not body_validation.ok:
        return PreparedGenerationOutput(
            ok=False,
            event_type=body_validation.event_type,
            message=body_validation.message,
            failure_kind=body_validation.failure_kind,
        )

    final_text = f"{title}\n{content_body}"

    final_has_blocked, final_blocked_keyword = (
        contains_blocked_keyword(final_text)
    )

    final_validation = validate_final_blocked_keyword(
        final_has_blocked,
        final_blocked_keyword,
    )

    if not final_validation.ok:
        return PreparedGenerationOutput(
            ok=False,
            event_type=final_validation.event_type,
            message=final_validation.message,
            failure_kind=final_validation.failure_kind,
        )

    return PreparedGenerationOutput(
        ok=True,
        title=title,
        content_body=content_body,
    )


@dataclass
class PersistGenerationResult:
    created: bool
    content: object = None
    duplicate_reason: str = ""


def _persist_generated_content(
    *,
    job,
    title,
    content_body,
    language,
    topic,
    audience,
    goal,
    prompt_template,
    selected_rules,
    user_prompt,
    fingerprint,
):
    (
        is_duplicate,
        duplicate_reason,
        content_hash,
    ) = is_duplicate_content(
        title,
        content_body,
        content_type=job.generation_type,
    )

    if is_duplicate:
        return PersistGenerationResult(
            created=False,
            duplicate_reason=duplicate_reason,
        )

    content = Content.objects.create(
        title=title,
        content_type=job.generation_type,
        generation_job=job,
        language=language,
        topic=topic,
        audience=audience,
        goal=goal,
        prompt_template=prompt_template,
        prompt=user_prompt,
        generated_content=content_body,
        content_hash=content_hash,
        status="generated",
    )

    complete_fingerprint(
        fingerprint=fingerprint,
        content=content,
    )

    if selected_rules:
        content.rules.set(selected_rules)

    if content.content_type in {"standard", "greeting"}:
        queue_content_deliveries(content)

    handle_generation_success(
        job=job,
        language=language,
        topic=topic,
        audience=audience,
        goal=goal,
        prompt_template=prompt_template,
        content=content,
    )

    increment_generated(job)

    return PersistGenerationResult(
        created=True,
        content=content,
    )

def run_generation_job(job_id):
    job = GenerationJob.objects.get(id=job_id)

    if job.status == "running":
        log_job(job, "warning", "Job is already running.")
        return

    reset_job_for_start(job)
    log_job(job, "info", "Job started.")

    active_fingerprint = None
    retry_feedback = ""

    try:
        app_settings = get_app_settings()

        generation_pool = get_job_generation_pool_v2(job)

        (
            target_count,
            max_attempts,
            max_runtime_seconds,
        ) = _get_generation_run_limits(
            job=job,
            app_settings=app_settings,
        )

        run_started_at = time.monotonic()
        run_started_generated_count = job.generated_count
        run_started_attempted_count = job.attempted_count

        pool_summary = (
            _build_generation_pool_summary(
                generation_pool
            )
        )

        log_job(
            job,
            "info",
            (
                "Using Generation V2 dataset pool. "
                f"{pool_summary or 'No datasets configured'}."
            ),
        )

        while (
            job.generated_count < target_count
            and job.attempted_count < max_attempts
        ):
            job.refresh_from_db()

            if job.should_stop:
                mark_job_stopped(job)
                return

            if _run_slice_limit_reached(
                job=job,
                run_started_generated_count=run_started_generated_count,
                run_started_attempted_count=run_started_attempted_count,
            ):
                _pause_job_and_schedule_resume(
                    job,
                    (
                        "Generation batch completed. "
                        f"Generated: {job.generated_count}/{target_count}; "
                        "continuing automatically."
                    ),
                )
                return

            if _runtime_limit_reached(
                run_started_at=run_started_at,
                max_runtime_seconds=max_runtime_seconds,
            ):
                message = (
                    "Generation paused at runtime limit. "
                    f"Generated: {job.generated_count}/{target_count}; "
                    "continuing automatically."
                )

                _pause_job_and_schedule_resume(job, message)
                return

            _record_generation_attempt(job)

            generator = get_generator(job.generation_type)

            reservation = reserve_generation_context(
                job=job,
                generator=generator,
                random_module=random,
            )
            if not reservation.acquired:
                log_job(
                    job,
                    "warning",
                    "Unable to reserve a unique generation context.",
                    )
                continue
            context = reservation.context
            fingerprint = reservation.fingerprint
            active_fingerprint = fingerprint
            language = context["language"]
            topic = context["topic"]
            audience = context["audience"]
            goal = context["goal"]
            prompt_template = context["prompt_template"]
            selected_rules = context["selected_rules"]
            variation_key = context.get("variation_key")

            prompt_data = generator.build_prompt_data(
                app_settings=app_settings,
                language=language,
                topic=topic,
                audience=audience,
                goal=goal,
                prompt_template=prompt_template,
                selected_rules=selected_rules,
                variation_key=variation_key,
                retry_feedback=retry_feedback,
            )

            system_prompt = prompt_data["system_prompt"]
            user_prompt = prompt_data["user_prompt"]
            fallback_title = prompt_data["fallback_title"]

            try:
                generated_text = generate_content(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
            except Exception as exc:
                retry_feedback = (
                    "The previous generation attempt failed with an internal "
                    f"error: {str(exc)[:240]}. Produce a fresh valid output."
                )
                fail_fingerprint(
                    fingerprint=fingerprint,
                    error_message=str(exc),
                )
                active_fingerprint = None
                handle_generation_failure(
                    job=job,
                    app_settings=app_settings,
                    event_type="error",
                    language=language,
                    topic=topic,
                    audience=audience,
                    goal=goal,
                    prompt_template=prompt_template,
                    message=f"Generation attempt failed: {exc}",
                    failure_kind="failed",
                )
                continue

            prepared = _prepare_generated_output(
                job=job,
                generator=generator,
                generated_text=generated_text,
                fallback_title=fallback_title,
            )

            if not prepared.ok:
                retry_feedback = (
                    "The previous output was rejected because: "
                    f"{prepared.message} Fix this constraint in the next output."
                )
                fail_fingerprint(
                    fingerprint=fingerprint,
                )
                active_fingerprint = None

                handle_generation_failure(
                    job=job,
                    app_settings=app_settings,
                    event_type=prepared.event_type,
                    language=language,
                    topic=topic,
                    audience=audience,
                    goal=goal,
                    prompt_template=prompt_template,
                    message=prepared.message,
                    failure_kind=prepared.failure_kind,
                )
                continue

            title = prepared.title
            content_body = prepared.content_body

            persist_result = (
                _persist_generated_content(
                    job=job,
                    title=title,
                    content_body=content_body,
                    language=language,
                    topic=topic,
                    audience=audience,
                    goal=goal,
                    prompt_template=prompt_template,
                    selected_rules=selected_rules,
                    user_prompt=user_prompt,
                    fingerprint=fingerprint,
                )
            )

            if not persist_result.created:
                retry_feedback = (
                    "The previous output duplicated existing content. "
                    "Use substantially different wording and structure."
                )
                fail_fingerprint(
                    fingerprint=fingerprint,
                )
                active_fingerprint = None

                handle_generation_failure(
                    job=job,
                    app_settings=app_settings,
                    event_type="duplicate",
                    language=language,
                    topic=topic,
                    audience=audience,
                    goal=goal,
                    prompt_template=prompt_template,
                    message=(
                        "Duplicate reason: "
                        f"{persist_result.duplicate_reason}"
                    ),
                    failure_kind="duplicate",
                )
                continue

            active_fingerprint = None
            retry_feedback = ""

            if job.delay_seconds:
                time.sleep(job.delay_seconds)

        job.refresh_from_db()

        if job.generated_count >= target_count:
            mark_job_completed(job)
            return

        fail_job(
            job,
            (
                "Job failed before reaching target. "
                f"Generated: {job.generated_count}/{target_count}. "
                f"Skipped: {job.skipped_count}. "
                f"Attempts: {job.attempted_count}/{max_attempts}."
            ),
        )

    except Exception as exc:
        if active_fingerprint:
            try:
                fail_fingerprint(
                    fingerprint=active_fingerprint,
                    error_message=str(exc),
                )
            except Exception:
                pass

        fail_job(job, str(exc))
