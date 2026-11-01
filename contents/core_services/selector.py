import random

from django.db.models import Q

from contents.models import DatasetPerformance, GenerationPattern

from contents.core_services.scoring import (
    calculate_item_score,
    get_weight,
    item_score_from_quality,
    pattern_score_from_quality,
)


def weighted_choice(items):
    items = list(items)

    if not items:
        return None

    weights = [get_weight(item) for item in items]

    return random.choices(items, weights=weights, k=1)[0]


def intelligent_choice(items):
    items = list(items)

    if not items:
        return None

    weights = [calculate_item_score(item) for item in items]

    return random.choices(items, weights=weights, k=1)[0]


def intelligent_generation_choice(
    languages,
    topics,
    audiences,
    goals,
    prompt_templates,
    sample_size=25,
):
    # Load each item's quality once, rather than once per item per candidate.
    pools = [list(items) for items in
             (languages, topics, audiences, goals, prompt_templates)]
    quality_filter = Q()
    for item_type, items in zip(("topic", "audience", "goal"), pools[1:4]):
        if items:
            quality_filter |= Q(item_type=item_type, item_id__in=[i.pk for i in items])
    qualities = {}
    if quality_filter:
        qualities = {
            (item_type, item_id): quality
            for item_type, item_id, quality in DatasetPerformance.objects.filter(
                quality_filter,
            ).values_list("item_type", "item_id", "quality_score")
        }
    weights = []
    for item_type, items in zip((None, "topic", "audience", "goal", None), pools):
        weights.append([
            item_score_from_quality(item, qualities.get((item_type, item.pk)))
            for item in items
        ])
    score_maps = [dict(zip((item.pk for item in items), scores))
                  for items, scores in zip(pools, weights)]

    candidates = []
    for _ in range(sample_size):
        candidates.append(tuple(
            random.choices(items, weights=scores, k=1)[0] if items else None
            for items, scores in zip(pools, weights)
        ))

    fields = ("language_id", "topic_id", "audience_id", "goal_id", "prompt_template_id")
    keys = [tuple(item.pk if item else None for item in candidate) for candidate in candidates]
    pattern_filter = Q()
    for key in set(keys):
        pattern_filter |= Q(**dict(zip(fields, key)))
    pattern_scores = {}
    if pattern_filter:
        for row in GenerationPattern.objects.filter(pattern_filter).order_by("pk").values_list(
            *fields, "quality_score", "confidence",
        ):
            # Match the original .first() behavior if old data contains duplicates.
            pattern_scores.setdefault(tuple(row[:5]), pattern_score_from_quality(*row[5:]))

    candidate_weights = []
    for key in keys:
        score = pattern_scores.get(key, 1)
        for index in (1, 2, 3):
            score *= score_maps[index].get(key[index], 1)
        candidate_weights.append(max(score, 0.1))
    return random.choices(candidates, weights=candidate_weights, k=1)[0]


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