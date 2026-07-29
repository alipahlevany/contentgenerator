from pathlib import Path

path = Path("contents/core_services/datasets/job_pool_v2.py")

path.write_text(
'''from contents.models import GenerationType, GenerationTypeDataset

from .registry import (
    get_dataset_model,
    DatasetRegistryError,
)


class JobPoolError(Exception):
    """Raised when a generation job cannot build its dataset pool."""


def get_job_generation_pool_v2(job):
    """
    Build a dynamic dataset pool for a generation job.

    Returns:

        {
            "language": {
                "model": Language,
                "required": True,
                "weight": 100,
            },
            ...
        }

    NOTE:
    This is the first V2 implementation.
    Dataset loading will be added in the next step.
    """

    try:
        generation_type = GenerationType.objects.get(
            key=job.generation_type,
            is_active=True,
        )
    except GenerationType.DoesNotExist as exc:
        raise JobPoolError(
            f"Unknown generation type: {job.generation_type}"
        ) from exc

    datasets = (
        GenerationTypeDataset.objects
        .filter(
            generation_type=generation_type,
            is_active=True,
        )
        .select_related("dataset_category")
        .order_by("selection_order", "id")
    )

    result = {}

    for dataset in datasets:

        key = dataset.dataset_category.key

        try:
            model = get_dataset_model(key)
        except DatasetRegistryError:
            continue

        result[key] = {
            "model": model,
            "required": dataset.is_required,
            "weight": dataset.weight,
        }

    return result
''',
encoding="utf-8")

print("OK: job_pool_v2 created.")
