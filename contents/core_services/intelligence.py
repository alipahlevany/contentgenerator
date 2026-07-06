from django.db.models import F
from django.utils import timezone

from contents.models import (
    DatasetEvent,
    DatasetPerformance,
    GenerationPattern,
)


def calculate_quality_score(
    success_count,
    skip_count,
    duplicate_count,
    blocked_count,
    error_count,
):
    total = success_count + skip_count + duplicate_count + blocked_count + error_count

    if total <= 0:
        return 100

    penalty = (
        skip_count * 1
        + duplicate_count * 2
        + blocked_count * 3
        + error_count * 2
    )

    score = 100 - ((penalty / total) * 100)

    return max(0, min(100, round(score, 2)))


def calculate_confidence(total_events):
    if total_events <= 0:
        return 0

    if total_events >= 100:
        return 100

    return round(total_events, 2)


def get_or_create_dataset_performance(item_type, item_id):
    obj, _ = DatasetPerformance.objects.get_or_create(
        item_type=item_type,
        item_id=item_id,
    )

    return obj


def update_dataset_performance(item_type, item_id, event_type):
    performance = get_or_create_dataset_performance(
        item_type=item_type,
        item_id=item_id,
    )

    if event_type == "success":
        performance.success_count = F("success_count") + 1
    elif event_type == "duplicate":
        performance.duplicate_count = F("duplicate_count") + 1
        performance.skip_count = F("skip_count") + 1
    elif event_type == "blocked":
        performance.blocked_count = F("blocked_count") + 1
        performance.skip_count = F("skip_count") + 1
    elif event_type == "error":
        performance.error_count = F("error_count") + 1
        performance.skip_count = F("skip_count") + 1
    else:
        performance.skip_count = F("skip_count") + 1

    performance.last_used_at = timezone.now()
    performance.save()

    performance.refresh_from_db()

    performance.quality_score = calculate_quality_score(
        success_count=performance.success_count,
        skip_count=performance.skip_count,
        duplicate_count=performance.duplicate_count,
        blocked_count=performance.blocked_count,
        error_count=performance.error_count,
    )
    performance.save(update_fields=["quality_score"])

    return performance


def get_or_create_generation_pattern(
    language,
    topic,
    audience,
    goal,
    prompt_template,
):
    pattern, _ = GenerationPattern.objects.get_or_create(
        language=language,
        topic=topic,
        audience=audience,
        goal=goal,
        prompt_template=prompt_template,
    )

    return pattern


def update_generation_pattern(
    language,
    topic,
    audience,
    goal,
    prompt_template,
    event_type,
):
    pattern = get_or_create_generation_pattern(
        language=language,
        topic=topic,
        audience=audience,
        goal=goal,
        prompt_template=prompt_template,
    )

    if event_type == "success":
        pattern.success_count = F("success_count") + 1
    elif event_type == "duplicate":
        pattern.duplicate_count = F("duplicate_count") + 1
        pattern.skip_count = F("skip_count") + 1
    elif event_type == "blocked":
        pattern.blocked_count = F("blocked_count") + 1
        pattern.skip_count = F("skip_count") + 1
    elif event_type == "error":
        pattern.error_count = F("error_count") + 1
        pattern.skip_count = F("skip_count") + 1
    else:
        pattern.skip_count = F("skip_count") + 1

    pattern.last_used_at = timezone.now()
    pattern.save()

    pattern.refresh_from_db()

    total = (
        pattern.success_count
        + pattern.skip_count
        + pattern.duplicate_count
        + pattern.blocked_count
        + pattern.error_count
    )

    pattern.quality_score = calculate_quality_score(
        success_count=pattern.success_count,
        skip_count=pattern.skip_count,
        duplicate_count=pattern.duplicate_count,
        blocked_count=pattern.blocked_count,
        error_count=pattern.error_count,
    )

    pattern.confidence = calculate_confidence(total)

    pattern.save(
        update_fields=[
            "quality_score",
            "confidence",
        ]
    )

    return pattern


def create_dataset_event(
    item_type,
    item_id,
    event_type,
    job=None,
    content=None,
    message="",
):
    return DatasetEvent.objects.create(
        item_type=item_type,
        item_id=item_id,
        event_type=event_type,
        job=job,
        content=content,
        message=message,
    )


def record_item_event(
    item_type,
    item,
    event_type,
    job=None,
    content=None,
    message="",
):
    if not item:
        return None

    create_dataset_event(
        item_type=item_type,
        item_id=item.id,
        event_type=event_type,
        job=job,
        content=content,
        message=message,
    )

    return update_dataset_performance(
        item_type=item_type,
        item_id=item.id,
        event_type=event_type,
    )


def record_generation_event(
    event_type,
    job,
    language,
    topic,
    audience,
    goal,
    prompt_template,
    content=None,
    message="",
):
    record_item_event(
        item_type="topic",
        item=topic,
        event_type=event_type,
        job=job,
        content=content,
        message=message,
    )

    record_item_event(
        item_type="audience",
        item=audience,
        event_type=event_type,
        job=job,
        content=content,
        message=message,
    )

    record_item_event(
        item_type="goal",
        item=goal,
        event_type=event_type,
        job=job,
        content=content,
        message=message,
    )

    return update_generation_pattern(
        language=language,
        topic=topic,
        audience=audience,
        goal=goal,
        prompt_template=prompt_template,
        event_type=event_type,
    )