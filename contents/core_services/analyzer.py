from contents.models import DatasetPerformance, GenerationPattern


def get_dataset_health():
    performances = DatasetPerformance.objects.all()

    total_items = performances.count()

    if total_items == 0:
        return {
            "total_items": 0,
            "average_quality": 100,
            "weak_items": 0,
            "strong_items": 0,
        }

    scores = list(performances.values_list("quality_score", flat=True))

    average_quality = round(sum(scores) / len(scores), 2)

    return {
        "total_items": total_items,
        "average_quality": average_quality,
        "weak_items": performances.filter(quality_score__lte=40).count(),
        "strong_items": performances.filter(quality_score__gte=90).count(),
    }


def get_worst_dataset_items(limit=10):
    return DatasetPerformance.objects.order_by("quality_score", "-updated_at")[:limit]


def get_best_dataset_items(limit=10):
    return DatasetPerformance.objects.order_by("-quality_score", "-updated_at")[:limit]


def get_worst_generation_patterns(limit=10):
    return GenerationPattern.objects.order_by("quality_score", "-confidence")[:limit]


def get_best_generation_patterns(limit=10):
    return GenerationPattern.objects.order_by("-quality_score", "-confidence")[:limit]