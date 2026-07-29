from pathlib import Path

package_dir = Path("contents/core_services/datasets")
package_dir.mkdir(parents=True, exist_ok=True)

init_path = package_dir / "__init__.py"
registry_path = package_dir / "registry.py"

init_path.write_text(
'''from .registry import (
    DatasetRegistryError,
    get_dataset_model,
    is_registered_dataset,
    registered_dataset_keys,
)

__all__ = [
    "DatasetRegistryError",
    "get_dataset_model",
    "is_registered_dataset",
    "registered_dataset_keys",
]
''',
    encoding="utf-8",
)

registry_path.write_text(
'''from contents.models import (
    Audience,
    ContentRule,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)


class DatasetRegistryError(LookupError):
    """Raised when a dataset category has no registered model."""


DATASET_MODEL_REGISTRY = {
    "language": Language,
    "topic": Topic,
    "audience": Audience,
    "goal": Goal,
    "prompt_template": PromptTemplate,
    "content_rule": ContentRule,
}


def get_dataset_model(dataset_key):
    """
    Return the Django model registered for a dataset category key.
    """
    normalized_key = str(dataset_key).strip().lower()

    try:
        return DATASET_MODEL_REGISTRY[normalized_key]
    except KeyError as exc:
        raise DatasetRegistryError(
            f"No dataset model registered for: {normalized_key}"
        ) from exc


def is_registered_dataset(dataset_key):
    """
    Return True when a dataset category has a registered model.
    """
    normalized_key = str(dataset_key).strip().lower()
    return normalized_key in DATASET_MODEL_REGISTRY


def registered_dataset_keys():
    """
    Return all registered dataset category keys.
    """
    return tuple(DATASET_MODEL_REGISTRY.keys())
''',
    encoding="utf-8",
)

print("OK: Dataset model registry created.")
