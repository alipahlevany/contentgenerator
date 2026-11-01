from contents.models import DatasetPerformance, GenerationPattern


def get_weight(obj):
    weight = getattr(obj, "weight", 1) or 1

    try:
        weight = int(weight)
    except (TypeError, ValueError):
        weight = 1

    return max(weight, 1)


def get_item_type(item):
    model_name = item.__class__.__name__.lower()

    if model_name in ["topic", "audience", "goal"]:
        return model_name

    return None


def get_dataset_performance(item):
    item_type = get_item_type(item)

    if not item_type:
        return None

    return DatasetPerformance.objects.filter(
        item_type=item_type,
        item_id=item.id,
    ).first()


def calculate_item_score(item):
    performance = get_dataset_performance(item)
    return item_score_from_quality(
        item, performance.quality_score if performance else None,
    )


def item_score_from_quality(item, quality_score):
    base_weight = get_weight(item)
    if quality_score is None:
        return base_weight
    quality_multiplier = max(quality_score, 1) / 100
    return max(base_weight * quality_multiplier, 0.1)


def calculate_pattern_score(language, topic, audience, goal, prompt_template):
    pattern = GenerationPattern.objects.filter(
        language=language,
        topic=topic,
        audience=audience,
        goal=goal,
        prompt_template=prompt_template,
    ).first()

    if not pattern:
        return 1

    return pattern_score_from_quality(pattern.quality_score, pattern.confidence)


def pattern_score_from_quality(quality_score, confidence):
    return max(max(quality_score, 1) / 100 * max(confidence, 1) / 100, 0.1)


def calculate_generation_score(
    language,
    topic,
    audience,
    goal,
    prompt_template,
):
    topic_score = calculate_item_score(topic)
    audience_score = calculate_item_score(audience)
    goal_score = calculate_item_score(goal)
    pattern_score = calculate_pattern_score(
        language=language,
        topic=topic,
        audience=audience,
        goal=goal,
        prompt_template=prompt_template,
    )

    return max(
        topic_score * audience_score * goal_score * pattern_score,
        0.1,
    )