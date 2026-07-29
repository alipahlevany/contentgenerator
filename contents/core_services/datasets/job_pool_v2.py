from contents.models import GenerationType, GenerationTypeDataset

from .registry import DatasetRegistryError, get_dataset_config


class JobPoolError(Exception):
    """Raised when a generation job cannot build its dataset pool."""


def _active_items(queryset):
    return list(
        queryset
        .filter(is_active=True)
        .order_by("id")
    )


def _all_active_items(config):
    return _active_items(config.model.objects.all())


def _selected_active_items(job, config):
    relation = getattr(job, config.relation_name, None)

    if relation is None:
        return []

    return _active_items(relation.all())


def _legacy_fallback_items(job, config):
    field_name = config.legacy_fallback_field

    if not field_name:
        return []

    item = getattr(job, field_name, None)

    if item is None:
        return []

    if not getattr(item, "is_active", False):
        return []

    return [item]


def _should_use_all(job, config):
    if not config.use_all_field:
        return False

    return bool(
        getattr(job, config.use_all_field, False)
    )


def _load_dataset_items(job, config, is_required):
    """
    Load the actual allowed items for one dataset.

    Rules:
    - use_all_* = True: all active items.
    - Explicit active M2M selections: selected items only.
    - Legacy fallback field: use it when active.
    - Empty required dataset: fall back to all active items.
    - Empty optional dataset: return an empty list.
    """
    if _should_use_all(job, config):
        items = _all_active_items(config)
    else:
        items = _selected_active_items(job, config)

        if not items:
            items = _legacy_fallback_items(job, config)

        if not items and is_required:
            items = _all_active_items(config)

    if is_required and not items:
        raise JobPoolError(
            f'Required dataset "{config.model.__name__}" has no active items.'
        )

    return items


def get_job_generation_pool_v2(job):
    """
    Build a dynamic dataset pool for a generation job.

    Example result:

        {
            "language": {
                "model": Language,
                "required": True,
                "weight": 100,
                "items": [...],
            }
        }
    """
    try:
        generation_type = GenerationType.objects.get(
            key=job.generation_type,
            is_active=True,
        )
    except GenerationType.DoesNotExist as exc:
        raise JobPoolError(
            f"Unknown or inactive generation type: {job.generation_type}"
        ) from exc

    dataset_relations = (
        GenerationTypeDataset.objects
        .filter(
            generation_type=generation_type,
            is_active=True,
            dataset_category__is_active=True,
        )
        .select_related("dataset_category")
        .order_by("selection_order", "id")
    )

    result = {}

    for relation in dataset_relations:
        key = relation.dataset_category.key

        try:
            config = get_dataset_config(key)
        except DatasetRegistryError as exc:
            raise JobPoolError(
                f'Dataset category "{key}" is active but not registered.'
            ) from exc

        items = _load_dataset_items(
            job=job,
            config=config,
            is_required=relation.is_required,
        )

        result[key] = {
            "model": config.model,
            "required": relation.is_required,
            "weight": relation.weight,
            "selection_order": relation.selection_order,
            "items": items,
        }

    return result
