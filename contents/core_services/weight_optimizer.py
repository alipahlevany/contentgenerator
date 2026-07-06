from contents.models import Audience, DatasetPerformance, Goal, Topic


MODEL_MAP = {
    "topic": Topic,
    "audience": Audience,
    "goal": Goal,
}


MIN_EVENTS_FOR_WEIGHT_CHANGE = 20
MIN_WEIGHT = 1
MAX_WEIGHT = 20


def get_model_for_item_type(item_type):
    return MODEL_MAP.get(item_type)


def calculate_new_weight(current_weight, quality_score):
    if quality_score >= 90:
        return min(current_weight + 1, MAX_WEIGHT)

    if quality_score <= 40:
        return max(current_weight - 1, MIN_WEIGHT)

    return current_weight


def optimize_dataset_weights(limit=100):
    updated_count = 0

    performances = (
        DatasetPerformance.objects
        .filter(success_count__gt=0)
        .order_by("-updated_at")[:limit]
    )

    for performance in performances:
        total_events = (
            performance.success_count
            + performance.skip_count
            + performance.duplicate_count
            + performance.blocked_count
            + performance.error_count
        )

        if total_events < MIN_EVENTS_FOR_WEIGHT_CHANGE:
            continue

        model = get_model_for_item_type(performance.item_type)

        if not model:
            continue

        item = model.objects.filter(id=performance.item_id).first()

        if not item:
            continue

        new_weight = calculate_new_weight(
            current_weight=item.weight,
            quality_score=performance.quality_score,
        )

        if new_weight == item.weight:
            continue

        item.weight = new_weight
        item.save(update_fields=["weight"])

        updated_count += 1

    return updated_count