from pathlib import Path

base = Path("contents/core_services/generators")
base.mkdir(parents=True, exist_ok=True)

registry_file = base / "registry.py"

content = '''"""
Generator registry.

This module maps generation type keys to generator classes.

Keeping this registry separate from factory.py makes it easy
to register new generation types without changing the factory.
"""

from .standard import StandardGenerator
from .email_reply import EmailReplyGenerator


GENERATOR_REGISTRY = {
    "standard": StandardGenerator,
    "email_reply": EmailReplyGenerator,
}


def get_generator_class(generation_type):
    try:
        return GENERATOR_REGISTRY[generation_type]
    except KeyError:
        supported = ", ".join(sorted(GENERATOR_REGISTRY.keys()))
        raise ValueError(
            f"Unknown generation type '{generation_type}'. "
            f"Supported types: {supported}"
        )
'''

registry_file.write_text(content, encoding="utf-8")

print(f"OK: {registry_file} created.")
