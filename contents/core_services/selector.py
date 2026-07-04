import random


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

    weights = [get_weight(item) for item in items]

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