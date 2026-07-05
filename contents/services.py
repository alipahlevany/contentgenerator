from .core_services.ai import generate_content
from .core_services.dataset_manager import run_dataset_refill
from .core_services.cache import get_app_settings, get_blocked_keywords
from .core_services.cleaner import normalize
from .core_services.duplicate import is_duplicate_content
from .core_services.logger import fail_job, log_job
from .core_services.prompt import (
    build_context,
    extract_title_and_content,
    render_template,
)
from .core_services.runner import (
    increment_generated,
    increment_skipped,
    mark_job_completed,
    mark_job_stopped,
    reset_job_for_start,
)
from .core_services.selector import (
    get_optional_pool,
    get_required_pool,
    weighted_choice,
    weighted_sample,
)
from .models import (
    Audience,
    Content,
    ContentRule,
    GenerationJob,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)


def contains_blocked_keyword(text):
    normalized_text = normalize(text)

    for keyword in get_blocked_keywords():
        if normalize(keyword) in normalized_text:
            return True, keyword

    return False, None


def run_generation_job(job_id):
    job = GenerationJob.objects.get(id=job_id)

    if job.status == "running":
        log_job(job, "warning", "Job is already running.")
        return

    reset_job_for_start(job)
    log_job(job, "info", "Job started.")

    try:
        app_settings = get_app_settings()

        languages = get_required_pool(Language, "languages")
        topics = get_required_pool(Topic, "topics")
        audiences = get_required_pool(Audience, "audiences")
        goals = get_required_pool(Goal, "goals")
        prompt_templates = get_required_pool(PromptTemplate, "prompt templates")
        content_rules = get_optional_pool(ContentRule)

        target_count = job.count
        max_attempts = max(target_count * 10, 50)
        attempts = 0

        log_job(
            job,
            "info",
            (
                "Using global weighted pools. "
                f"Languages: {len(languages)}, "
                f"Topics: {len(topics)}, "
                f"Audiences: {len(audiences)}, "
                f"Goals: {len(goals)}, "
                f"PromptTemplates: {len(prompt_templates)}, "
                f"ContentRules: {len(content_rules)}."
            ),
        )

        while job.generated_count < target_count and attempts < max_attempts:
            attempts += 1
            job.refresh_from_db()

            if job.should_stop:
                mark_job_stopped(job)
                return

            language = weighted_choice(languages)
            topic = weighted_choice(topics)
            audience = weighted_choice(audiences)
            goal = weighted_choice(goals)
            prompt_template = weighted_choice(prompt_templates)
            selected_rules = weighted_sample(content_rules, max_count=3)

            context = build_context(
                app_settings=app_settings,
                language=language,
                topic=topic,
                audience=audience,
                goal=goal,
                selected_rules=selected_rules,
            )

            system_prompt = render_template(
                prompt_template.system_prompt,
                context,
            )

            user_prompt = render_template(
                prompt_template.user_prompt_template,
                context,
            )

            fallback_title = f"{topic.name} for {audience.name}"

            try:
                generated_text = generate_content(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
            except Exception as exc:
                increment_skipped(job)
                log_job(job, "error", f"Generation attempt failed: {exc}")

                run_dataset_refill(
                    job=job,
                    app_settings=app_settings,
                )

                continue

            has_blocked_keyword, blocked_keyword = contains_blocked_keyword(
                generated_text
            )

            if has_blocked_keyword:
                increment_skipped(job)

                log_job(
                    job,
                    "warning",
                    f"Skipped because blocked keyword was found: {blocked_keyword}",
                )

                run_auto_refill(
                    job=job,
                    app_settings=app_settings,
                )

                continue

            title, content_body = extract_title_and_content(
                generated_text,
                fallback_title,
            )

            is_duplicate, duplicate_reason, content_hash = is_duplicate_content(
                title,
                content_body,
            )

            if is_duplicate:
                increment_skipped(job)

                log_job(
                    job,
                    "warning",
                    f"Skipped {duplicate_reason}: {title}",
                )

                run_auto_refill(
                    job=job,
                    app_settings=app_settings,
                )

                continue

            content = Content.objects.create(
                title=title,
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

            if selected_rules:
                content.rules.set(selected_rules)

            increment_generated(job)

            log_job(
                job,
                "success",
                (
                    f"Generated content #{content.id}: "
                    f"{language.name} | {topic.name} | "
                    f"{audience.name} | {goal.name} | "
                    f"{prompt_template.name}"
                ),
            )

            if job.delay_seconds:
                import time
                time.sleep(job.delay_seconds)

        job.refresh_from_db()

        if job.generated_count >= target_count:
            mark_job_completed(job)
            return

        fail_job(
            job,
            (
                f"Job failed before reaching target. "
                f"Generated: {job.generated_count}/{target_count}. "
                f"Skipped: {job.skipped_count}. "
                f"Attempts: {attempts}/{max_attempts}."
            ),
        )

    except Exception as exc:
        fail_job(job, str(exc))