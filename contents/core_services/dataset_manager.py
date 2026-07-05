from django.core.cache import cache

from contents.core_services.ai import generate_content
from contents.core_services.logger import log_job
from contents.models import Audience, Goal, Topic


REFILL_LOCK_TIMEOUT = 60 * 10


def parse_seed_lines(text):
    lines = []

    for line in (text or "").splitlines():
        line = line.strip()
        line = line.lstrip("-•0123456789. ").strip()

        if line:
            lines.append(line[:255])

    return list(dict.fromkeys(lines))


def create_missing_seed_items(model, names):
    created_count = 0

    existing_names = {
        name.casefold()
        for name in model.objects.values_list("name", flat=True)
    }

    for name in names:
        normalized_name = name.casefold()

        if normalized_name in existing_names:
            continue

        model.objects.create(
            name=name,
            weight=1,
            is_active=True,
        )

        existing_names.add(normalized_name)
        created_count += 1

    return created_count


def generate_seed_items(model_name, count):
    system_prompt = (
        "You are a professional SEO content strategist. "
        "Generate clean and useful seed items for an AI content generation system. "
        "Return only one item per line. No numbering. No explanations."
    )

    user_prompt = (
        f"Generate {count} unique {model_name} ideas for content generation. "
        "They should be broad enough for many articles, but specific enough "
        "to reduce duplicate content."
    )

    text = generate_content(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_retries=3,
    )

    return parse_seed_lines(text)


def should_run_dataset_refill(job, app_settings):
    if not getattr(app_settings, "auto_refill_enabled", False):
        return False

    threshold = getattr(app_settings, "auto_refill_skip_threshold", 50)

    if job.skipped_count <= 0:
        return False

    if job.skipped_count % threshold != 0:
        return False

    lock_key = f"dataset_refill_lock_job_{job.id}_{job.skipped_count}"

    if cache.get(lock_key):
        return False

    cache.set(lock_key, True, REFILL_LOCK_TIMEOUT)

    return True


def run_dataset_refill(job, app_settings):
    if not should_run_dataset_refill(job, app_settings):
        return False

    item_count = getattr(app_settings, "auto_refill_item_count", 100)

    log_job(
        job,
        "warning",
        f"Dataset manager triggered at skipped count {job.skipped_count}.",
    )

    topic_names = generate_seed_items("topic", item_count)
    audience_names = generate_seed_items("audience", item_count)
    goal_names = generate_seed_items("goal", item_count)

    created_topics = create_missing_seed_items(Topic, topic_names)
    created_audiences = create_missing_seed_items(Audience, audience_names)
    created_goals = create_missing_seed_items(Goal, goal_names)

    log_job(
        job,
        "success",
        (
            "Dataset refill completed. "
            f"Topics: {created_topics}, "
            f"Audiences: {created_audiences}, "
            f"Goals: {created_goals}."
        ),
    )

    return True