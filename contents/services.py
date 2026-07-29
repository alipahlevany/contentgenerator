import random
import time

from django.utils import timezone

from .core_services.ai import generate_content
from .core_services.cache import get_app_settings
from .core_services.duplicate import is_duplicate_content
from .core_services.delivery_queue import queue_content_deliveries
from .core_services.generation.reservation import (
    reserve_generation_context,
)
from .core_services.generation.fingerprint import (
    complete_fingerprint,
    fail_fingerprint,
)
from .core_services.generation_outcome import (
    handle_generation_failure,
    handle_generation_success,
)
from .core_services.datasets.job_pool_v2 import get_job_generation_pool_v2
from .core_services.pipeline.blocked_keywords import (
    contains_blocked_keyword,
    remove_blocked_keywords,
)
from .core_services.pipeline.validator import (
    validate_content_body,
    validate_final_blocked_keyword,
    validate_generated_text,
)
from .core_services.logger import fail_job, log_job
from .core_services.generators.factory import get_generator
from .core_services.runner import (
    increment_generated,
    mark_job_completed,
    mark_job_stopped,
    reset_job_for_start,
)
from .models import Content, GenerationJob


def run_generation_job(job_id):
    job = GenerationJob.objects.get(id=job_id)

    if job.status == "running":
        log_job(job, "warning", "Job is already running.")
        return

    reset_job_for_start(job)
    log_job(job, "info", "Job started.")

    active_fingerprint = None

    try:
        app_settings = get_app_settings()

        generation_pool = get_job_generation_pool_v2(job)

        target_count = job.count
        max_attempts = job.max_attempts or max(
            target_count * app_settings.generation_attempt_multiplier,
            app_settings.generation_minimum_attempts,
        )
        max_runtime_seconds = app_settings.generation_max_runtime_seconds
        run_started_at = time.monotonic()

        pool_summary = ", ".join(
            (
                f"{dataset_key}: "
                f"{len(dataset_config['items'])}"
            )
            for dataset_key, dataset_config
            in generation_pool.items()
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

            if time.monotonic() - run_started_at >= max_runtime_seconds:
                fail_job(
                    job,
                    (
                        "Generation runtime limit reached. "
                        f"Generated: {job.generated_count}/{target_count}."
                    ),
                )
                return

            job.attempted_count += 1
            job.last_attempt_at = timezone.now()
            job.save(
                update_fields=["attempted_count", "last_attempt_at", "updated_at"]
            )

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

            prompt_data = generator.build_prompt_data(
                app_settings=app_settings,
                language=language,
                topic=topic,
                audience=audience,
                goal=goal,
                prompt_template=prompt_template,
                selected_rules=selected_rules,
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

            generated_validation = validate_generated_text(
                generated_text
            )

            if not generated_validation.ok:
                fail_fingerprint(
                    fingerprint=fingerprint,
                )
                active_fingerprint = None    
                handle_generation_failure(
                    job=job,
                    app_settings=app_settings,
                    event_type=generated_validation.event_type,
                    language=language,
                    topic=topic,
                    audience=audience,
                    goal=goal,
                    prompt_template=prompt_template,
                    message=generated_validation.message,
                    failure_kind=generated_validation.failure_kind,
                )
                continue

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
                    fail_fingerprint(
                        fingerprint=fingerprint,
                    )
                    handle_generation_failure(
                        job=job,
                        app_settings=app_settings,
                        event_type="blocked",
                        language=language,
                        topic=topic,
                        audience=audience,
                        goal=goal,
                        prompt_template=prompt_template,
                        message=(
                            "Blocked keyword remained after cleanup: "
                            f"{remaining_keyword}"
                        ),
                        failure_kind="failed",
                    )
                    continue

                if not generated_text.strip():
                    fail_fingerprint(
                        fingerprint=fingerprint,
                    )
                    handle_generation_failure(
                        job=job,
                        app_settings=app_settings,
                        event_type="blocked",
                        language=language,
                        topic=topic,
                        audience=audience,
                        goal=goal,
                        prompt_template=prompt_template,
                        message=(
                            "Generated content became empty after "
                            "blocked keyword cleanup."
                        ),
                        failure_kind="empty",
                    )
                    continue

                log_job(
                    job,
                    "warning",
                    (
                        "Blocked keyword removed before saving: "
                        f"{blocked_keyword}"
                    ),
                )

            title, content_body = generator.extract_output(
                generated_text,
                fallback_title,
            )

            title = title.strip()
            content_body = content_body.strip()

            if not title:
                title = fallback_title

            body_validation = validate_content_body(
                content_body
            )

            if not body_validation.ok:
                fail_fingerprint(
                    fingerprint=fingerprint,
                )
                active_fingerprint = None
                handle_generation_failure(
                    job=job,
                    app_settings=app_settings,
                    event_type=body_validation.event_type,
                    language=language,
                    topic=topic,
                    audience=audience,
                    goal=goal,
                    prompt_template=prompt_template,
                    message=body_validation.message,
                    failure_kind=body_validation.failure_kind,
                )
                continue

            final_text = f"{title}\n{content_body}"

            final_has_blocked, final_blocked_keyword = (
                contains_blocked_keyword(final_text)
            )

            final_validation = validate_final_blocked_keyword(
                final_has_blocked,
                final_blocked_keyword,
            )

            if not final_validation.ok:
                fail_fingerprint(
                    fingerprint=fingerprint,
                )
                active_fingerprint = None
                handle_generation_failure(
                    job=job,
                    app_settings=app_settings,
                    event_type=final_validation.event_type,
                    language=language,
                    topic=topic,
                    audience=audience,
                    goal=goal,
                    prompt_template=prompt_template,
                    message=final_validation.message,
                    failure_kind=final_validation.failure_kind,
                )
                continue

            (
                is_duplicate,
                duplicate_reason,
                content_hash,
            ) = is_duplicate_content(
                title,
                content_body,
            )

            if is_duplicate:
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
                        f"Duplicate reason: {duplicate_reason}"
                    ),
                    failure_kind="duplicate",
                )
                continue

            content = Content.objects.create(
                title=title,
                content_type=job.generation_type,
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
            active_fingerprint = None

            if selected_rules:
                content.rules.set(selected_rules)

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

        fail_job(job, str(exc))
