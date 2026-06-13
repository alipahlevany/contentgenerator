import random
import re
import time

from django.conf import settings
from openai import (
    APIConnectionError,
    APIStatusError,
    OpenAI,
    RateLimitError,
)

from .models import (
    AppSettings,
    BlockedKeyword,
    Content,
    GenerationJob,
    GenerationJobLog,
)


client = OpenAI(api_key=settings.OPENAI_API_KEY)


def add_job_log(job, level, message):
    GenerationJobLog.objects.create(
        job=job,
        level=level,
        message=message,
    )


def fail_job(job, message):
    job.status = "failed"
    job.error_message = message
    job.save()
    add_job_log(job, "error", message)
    print("Generation job failed:", message)


def stop_job(job):
    job.status = "stopped"
    job.error_message = "Job stopped by admin."
    job.should_stop = False
    job.save()
    add_job_log(job, "warning", "Job stopped by admin.")
    print("Generation job stopped by admin.")


def get_app_settings():
    app_settings = AppSettings.objects.filter(is_active=True).first()

    if not app_settings:
        app_settings = AppSettings.objects.create(
            max_output_tokens=1200,
            temperature=1.05,
            model_name="gpt-4.1-mini",
            is_active=True,
        )

    return app_settings


def get_blocked_keywords():
    return list(
        BlockedKeyword.objects
        .filter(is_active=True)
        .values_list("keyword", flat=True)
    )


def is_safe(text):
    if not text:
        return True

    text = text.lower()

    for word in get_blocked_keywords():
        if re.search(r"\b" + re.escape(word.lower()) + r"\b", text):
            return False

    return True


def validate_content(title, content):
    if not title or not title.strip():
        return False, "Missing title."

    if not content or not content.strip():
        return False, "Missing content."

    if not is_safe(title) or not is_safe(content):
        return False, "Content contains blocked keywords."

    return True, None


def clean_content(content):
    if not content:
        return ""

    content = content.replace("\\n", "\n")
    content = re.sub(r"[ \t]+", " ", content)
    content = re.sub(r"\n\s*\n+", "\n\n", content)
    return content.strip()


def extract_title_and_content(text):
    text = text.strip()

    title = ""
    content = text

    title_match = re.search(
        r"Title:\s*(.*?)(?:\n|Content:)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    content_match = re.search(
        r"Content:\s*(.*)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if title_match:
        title = title_match.group(1).strip()
        title = title.replace("**", "").strip()

    if content_match:
        content = content_match.group(1).strip()
        content = content.replace("**", "").strip()

    if not title:
        lines = text.splitlines()
        first_line = lines[0].strip() if lines else ""
        title = first_line.replace("**", "").replace("Title:", "").strip()

    if content.lower().startswith("content:"):
        content = content[8:].strip()

    return title, content


def is_duplicate_title(title):
    if not title:
        return False

    return Content.objects.filter(
        title__iexact=title.strip()
    ).exists()


def build_rules_text(rules):
    active_rules = [rule.prompt_text for rule in rules if rule.is_active]

    if not active_rules:
        return ""

    return "\n".join(f"- {rule_text}" for rule_text in active_rules)


def render_template(
    template_text,
    language,
    topic,
    audience,
    goal,
    rules_text,
):
    return template_text.format(
        language=language.name,
        language_name=language.name,
        language_code=language.code,
        topic=topic.name,
        audience=audience.name,
        goal=goal.name,
        rules=rules_text,
    )


def generate_content(
    system_prompt,
    user_prompt,
    max_retries=3,
):
    app_settings = get_app_settings()
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            response = client.responses.create(
                model=app_settings.model_name,
                instructions=system_prompt,
                input=user_prompt,
                max_output_tokens=app_settings.max_output_tokens,
                temperature=app_settings.temperature,
            )

            raw_text = clean_content(response.output_text.strip())
            title, content = extract_title_and_content(raw_text)

            is_valid, error = validate_content(title, content)

            if not is_valid:
                return None, None, error

            return title, content, None

        except (
            RateLimitError,
            APIConnectionError,
            APIStatusError,
        ) as e:
            last_error = str(e)

            print(
                f"Retry {attempt}/{max_retries}: "
                f"{last_error}"
            )

            if attempt < max_retries:
                time.sleep(attempt * 3)
                continue

            return (
                None,
                None,
                f"OpenAI error after {max_retries} retries: {last_error}",
            )

        except Exception as e:
            return (
                None,
                None,
                f"Unexpected OpenAI error: {str(e)}",
            )


def weighted_choice(items, value_field, weight_field="percentage"):
    population = []
    weights = []

    for item in items:
        value = getattr(item, value_field)
        weight = getattr(item, weight_field, 0)

        if weight > 0:
            population.append(value)
            weights.append(weight)

    if not population:
        return None

    return random.choices(
        population=population,
        weights=weights,
        k=1,
    )[0]


def run_generation_job(job_id):
    job = GenerationJob.objects.get(id=job_id)

    job.status = "running"
    job.generated_count = 0
    job.skipped_count = 0
    job.current_step = 0
    job.error_message = ""
    job.should_stop = False
    job.save()

    add_job_log(job, "info", "Job started.")

    languages = list(job.languages.filter(is_active=True))

    language_distributions = list(
        job.language_distributions
        .filter(language__is_active=True, percentage__gt=0)
        .select_related("language")
    )

    topics = list(job.topics.filter(is_active=True))

    topic_distributions = list(
        job.topic_distributions
        .filter(topic__is_active=True, percentage__gt=0)
        .select_related("topic")
    )

    audiences = list(job.audiences.filter(is_active=True))

    audience_distributions = list(
        job.audience_distributions
        .filter(audience__is_active=True, percentage__gt=0)
        .select_related("audience")
    )

    goals = list(job.goals.filter(is_active=True))

    goal_distributions = list(
        job.goal_distributions
        .filter(goal__is_active=True, percentage__gt=0)
        .select_related("goal")
    )

    rules = list(job.rules.filter(is_active=True))

    if not job.prompt_template or not job.prompt_template.is_active:
        fail_job(job, "No active prompt template selected.")
        return

    if not languages and not language_distributions:
        fail_job(job, "No active languages selected.")
        return

    if not topics and not topic_distributions:
        fail_job(job, "No active topics selected.")
        return

    if not audiences and not audience_distributions:
        fail_job(job, "No active audiences selected.")
        return

    if not goals and not goal_distributions:
        fail_job(job, "No active goals selected.")
        return

    skipped_count = 0
    last_error = ""

    for i in range(job.count):
        job.refresh_from_db()

        if job.should_stop:
            stop_job(job)
            return

        job.current_step = i + 1
        job.save(update_fields=["current_step"])

        if language_distributions:
            selected_language = weighted_choice(
                language_distributions,
                "language",
            )
        else:
            selected_language = random.choice(languages)

        if topic_distributions:
            selected_topic = weighted_choice(
                topic_distributions,
                "topic",
            )
        else:
            selected_topic = random.choice(topics)

        if audience_distributions:
            selected_audience = weighted_choice(
                audience_distributions,
                "audience",
            )
        else:
            selected_audience = random.choice(audiences)

        if goal_distributions:
            selected_goal = weighted_choice(
                goal_distributions,
                "goal",
            )
        else:
            selected_goal = random.choice(goals)

        rules_text = build_rules_text(rules)

        try:
            system_prompt = render_template(
                job.prompt_template.system_prompt,
                selected_language,
                selected_topic,
                selected_audience,
                selected_goal,
                rules_text,
            )

            user_prompt = render_template(
                job.prompt_template.user_prompt_template,
                selected_language,
                selected_topic,
                selected_audience,
                selected_goal,
                rules_text,
            )

            title, content_text, error = generate_content(
                system_prompt,
                user_prompt,
            )

            job.refresh_from_db()

            if job.should_stop:
                stop_job(job)
                return

            if error:
                skipped_count += 1
                last_error = f"Item {i + 1}: {error}"

                job.skipped_count = skipped_count
                job.error_message = (
                    f"Skipped items: {skipped_count}. "
                    f"Last error: {last_error}"
                )
                job.save(update_fields=["skipped_count", "error_message"])

                add_job_log(job, "warning", last_error)

                print("Skipped:", last_error)
                continue

            if is_duplicate_title(title):
                skipped_count += 1
                last_error = f"Item {i + 1}: Duplicate title: {title}"

                job.skipped_count = skipped_count
                job.error_message = (
                    f"Skipped items: {skipped_count}. "
                    f"Last error: {last_error}"
                )
                job.save(update_fields=["skipped_count", "error_message"])

                add_job_log(job, "warning", last_error)

                print("Skipped duplicate:", last_error)
                continue

            content = Content.objects.create(
                title=title or (
                    f"{selected_topic.name} - "
                    f"{selected_goal.name} - "
                    f"{selected_language.name}"
                ),
                language=selected_language,
                topic=selected_topic,
                audience=selected_audience,
                goal=selected_goal,
                prompt_template=job.prompt_template,
                prompt=user_prompt,
                generated_content=content_text,
                status="generated",
            )

            content.rules.set(rules)

            job.generated_count += 1
            job.error_message = (
                f"Skipped items: {skipped_count}. "
                f"Last error: {last_error}"
                if skipped_count
                else ""
            )
            job.save(update_fields=["generated_count", "error_message"])

            add_job_log(
                job,
                "success",
                f"Content #{content.id} generated.",
            )

            if job.delay_seconds:
                time.sleep(job.delay_seconds)

        except Exception as e:
            job.refresh_from_db()

            if job.should_stop:
                stop_job(job)
                return

            skipped_count += 1
            last_error = f"Item {i + 1}: {str(e)}"

            job.skipped_count = skipped_count
            job.error_message = (
                f"Skipped items: {skipped_count}. "
                f"Last error: {last_error}"
            )
            job.save(update_fields=["skipped_count", "error_message"])

            add_job_log(job, "error", last_error)

            print("Skipped with exception:", last_error)
            continue

    job.refresh_from_db()

    if job.should_stop:
        stop_job(job)
        return

    job.status = "completed"
    job.error_message = (
        f"Completed with skipped items: {skipped_count}. "
        f"Last error: {last_error}"
        if skipped_count
        else ""
    )
    job.should_stop = False
    job.save(update_fields=["status", "error_message", "should_stop"])

    add_job_log(job, "success", "Job completed.")