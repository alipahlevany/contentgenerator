from dataclasses import dataclass
from typing import Optional, Type

from django.db import models

from contents.models import (
    Audience,
    ContentRule,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)


class DatasetRegistryError(LookupError):
    """Raised when a dataset category has no registered configuration."""


@dataclass(frozen=True)
class DatasetConfig:
    model: Type[models.Model]
    relation_name: str
    use_all_field: Optional[str]
    legacy_fallback_field: Optional[str] = None


DATASET_REGISTRY = {
    "language": DatasetConfig(
        model=Language,
        relation_name="languages",
        use_all_field="use_all_languages",
    ),
    "topic": DatasetConfig(
        model=Topic,
        relation_name="topics",
        use_all_field="use_all_topics",
    ),
    "audience": DatasetConfig(
        model=Audience,
        relation_name="audiences",
        use_all_field="use_all_audiences",
    ),
    "goal": DatasetConfig(
        model=Goal,
        relation_name="goals",
        use_all_field="use_all_goals",
    ),
    "prompt_template": DatasetConfig(
        model=PromptTemplate,
        relation_name="prompt_templates",
        use_all_field="use_all_prompt_templates",
        legacy_fallback_field="prompt_template",
    ),
    "content_rule": DatasetConfig(
        model=ContentRule,
        relation_name="rules",
        use_all_field="use_all_rules",
    ),
}


def normalize_dataset_key(dataset_key):
    return str(dataset_key).strip().lower()


def get_dataset_config(dataset_key):
    """
    Return the registered configuration for a dataset category.
    """
    normalized_key = normalize_dataset_key(dataset_key)

    try:
        return DATASET_REGISTRY[normalized_key]
    except KeyError as exc:
        raise DatasetRegistryError(
            f"No dataset configuration registered for: {normalized_key}"
        ) from exc


def get_dataset_model(dataset_key):
    """
    Return the Django model registered for a dataset category.
    """
    return get_dataset_config(dataset_key).model


def is_registered_dataset(dataset_key):
    """
    Return True when a dataset category is registered.
    """
    normalized_key = normalize_dataset_key(dataset_key)
    return normalized_key in DATASET_REGISTRY


def registered_dataset_keys():
    """
    Return all registered dataset category keys.
    """
    return tuple(DATASET_REGISTRY.keys())
