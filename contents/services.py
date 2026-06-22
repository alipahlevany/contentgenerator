import random
import re
import time

from django.conf import settings
from django.core.cache import cache

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

from .models import (
    AppSettings,
    Audience,
    BlockedKeyword,
    Content,
    ContentRule,
    GenerationJob,
    GenerationJobLog,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)


client = OpenAI(api_key=settings.OPENAI_API_KEY)


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
    job.save(
        update_fields=[
            "status",
            "error_message",
        ]
    )

    log_job(job, "error", message)


def get_app_settings():
    cache_key = "active_app_settings"

    app_settings = cache.get(cache_key)

    if app_settings:
        return app_settings

    app_settings = AppSettings.objects.filter(is_active=True).first()

    if not app_settings:
        app_settings = AppSettings.objects.create(
            min_words=45,
            max_words=70,
            max_output_tokens=1200,
            temperature=1.05,
            model_name="gpt-4.1-mini",
            is_active=True,
        )

    cache.set(cache_key, app_settings, 300)

    return app_settings


def get_blocked_keywords():
    cache_key = "active_blocked_keywords"

    keywords = cache.get(cache_key)

    if keywords is not None:
        return keywords

    keywords = list(
        BlockedKeyword.objects
        .filter(is_active=True)
        .values_list("keyword", flat=True)
    )

    cache.set(cache_key, keywords, 300)

    return keywords


def normalize(text):
    return re.sub(r"\s+", " ", text or "").strip().casefold()


def contains_blocked_keyword(text):
    normalized_text = normalize(text)

    for keyword in get_blocked_keywords():
        if normalize(keyword) in normalized_text:
            return True, keyword

    return False, None


class SafeFormatDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def render_template(template_text, context):
    return (template_text or "").format_map(
        SafeFormatDict(**context)
    )


def get_weight(obj):
    weight = getattr(obj, "weight", 1) or 1

    try:
        weight = int(weight)
    except (TypeError, ValueError):
        weight = 1

    return max(weight, 1)


def weighted_choice(items):
    items = list(items)

    if not items:
        return None

    weights = [
        get_weight(item)
        for item in items
    ]

    return random.choices(
        items,
        weights=weights,
        k=1,
    )[0]


def weighted_sample(items, max_count=3):
    items = list(items)

    if not items or max_count <= 0:
        return []

    selected = []
    remaining = items[:]

    count = min(max_count, len(remaining))

    for _ in range(count):
        picked = weighted_choice(remaining)

        if not picked:
            break

        selected.append(picked)
        remaining.remove(picked)

    return selected


def get_required_pool(model, model_name):
    pool = list(
        model.objects
        .filter(is_active=True)
        .filter(weight__gt=0)
        .order_by("-weight", "id")
    )

    if not pool:
        raise ValueError(f"No active {model_name} found.")

    return pool


def get_optional_pool(model):
    return list(
        model.objects
        .filter(is_active=True)
        .filter(weight__gt=0)
        .order_by("-weight", "id")
    )


def get_response_text_from_content(content):
    if isinstance(content, dict):
        return content.get("text", "")

    return getattr(content, "text", "")


def extract_response_text(response):
    output_text = getattr(response, "output_text", None)

    if output_text:
        return output_text.strip()

    parts = []

    for item in getattr(response, "output", []) or []:
        item_content = getattr(item, "content", None)

        if item_content is None and isinstance(item, dict):
            item_content = item.get("content", [])

        for content in item_content or []:
            text = get_response_text_from_content(content)

            if text:
                parts.append(text)

    return "\n".join(parts).strip()


def generate_content(system_prompt, user_prompt=None, max_retries=3):
    app_settings = get_app_settings()

    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            response = client.responses.create(
                model=app_settings.model_name,
                instructions=system_prompt,
                input=user_prompt or "",
                max_output_tokens=app_settings.max_output_tokens,
                temperature=app_settings.temperature,
            )

            text = extract_response_text(response)

            if not text:
                raise ValueError("OpenAI returned empty output.")

            return text

        except (
            APIConnectionError,
            APIError,
            APITimeoutError,
            RateLimitError,
            ValueError,
        ) as exc:
            last_error = exc

            print(
                f"OpenAI generation failed "
                f"(attempt {attempt}/{max_retries}): {exc}"
            )

            if attempt < max_retries:
                time.sleep(2 * attempt)

    raise RuntimeError(f"OpenAI generation failed: {last_error}")


def extract_title_and_content(text, fallback_title):
    text = (text or "").strip()

    if not text:
        return fallback_title[:255], ""

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    title = fallback_title
    content = text

    if lines:
        first_line = lines[0]

        if first_line.lower().startswith("title:"):
            title = first_line.split(":", 1)[1].strip()
            content = "\n".join(lines[1:]).strip() or text

        elif first_line.startswith("#"):
            title = first_line.lstrip("#").strip()
            content = "\n".join(lines[1:]).strip() or text

    if not title:
        title = fallback_title

    return title[:255], content


def build_context(
    app_settings,
    language,
    topic,
    audience,
    goal,
    selected_rules,
):
    rules_text = "\n".join(
        f"- {rule.prompt_text}"
        for rule in selected_rules
        if rule.prompt_text
    )

    if not rules_text:
        rules_text = "- No additional rules."

    return {
        "language": language.name,
        "language_name": language.name,
        "language_code": language.code,
        "topic": topic.name,
        "audience": audience.name,
        "goal": goal.name,
        "rules": rules_text,
        "min_words": app_settings.min_words,
        "max_words": app_settings.max_words,
    }


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
    job.save(
        update_fields=[
            "status",
            "error_message",
        ]
    )

    log_job(job, "success", "Job completed successfully.")


def mark_job_stopped(job):
    job.status = "stopped"
    job.error_message = "Job stopped by admin."
    job.save(
        update_fields=[
            "status",
            "error_message",
        ]
    )

    log_job(job, "warning", "Job stopped by admin.")


def increment_skipped(job):
    job.skipped_count += 1
    job.current_step += 1
    job.save(
        update_fields=[
            "skipped_count",
            "current_step",
        ]
    )


def increment_generated(job):
    job.generated_count += 1
    job.current_step += 1
    job.save(
        update_fields=[
            "generated_count",
            "current_step",
        ]
    )


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
        prompt_templates = get_required_pool(
            PromptTemplate,
            "prompt templates",
        )
        content_rules = get_optional_pool(ContentRule)

        target_count = job.count
        max_attempts = max(target_count * 3, target_count)
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

            selected_rules = weighted_sample(
                content_rules,
                max_count=3,
            )

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

                log_job(
                    job,
                    "error",
                    f"Generation attempt failed: {exc}",
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

                continue

            title, content_body = extract_title_and_content(
                generated_text,
                fallback_title,
            )

            if Content.objects.filter(title__iexact=title).exists():
                increment_skipped(job)

                log_job(
                    job,
                    "warning",
                    f"Skipped duplicate title: {title}",
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