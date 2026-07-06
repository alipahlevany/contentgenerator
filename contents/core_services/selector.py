import random

from contents.core_services.scoring import (
    calculate_generation_score,
    calculate_item_score,
    get_weight,
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
    candidates = []

    for _ in range(sample_size):
        language = weighted_choice(languages)
        topic = intelligent_choice(topics)
        audience = intelligent_choice(audiences)
        goal = intelligent_choice(goals)
        prompt_template = weighted_choice(prompt_templates)

        score = calculate_generation_score(
            language=language,
            topic=topic,
            audience=audience,
            goal=goal,
            prompt_template=prompt_template,
        )

        candidates.append(
            {
                "language": language,
                "topic": topic,
                "audience": audience,
                "goal": goal,
                "prompt_template": prompt_template,
                "score": score,
            }
        )

    weights = [candidate["score"] for candidate in candidates]
    selected = random.choices(candidates, weights=weights, k=1)[0]

    return (
        selected["language"],
        selected["topic"],
        selected["audience"],
        selected["goal"],
        selected["prompt_template"],
    )


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