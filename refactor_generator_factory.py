from pathlib import Path

factory = Path("contents/core_services/generators/factory.py")

text = '''from .registry import get_generator_class


def get_generator(generation_type):
    """
    Return an initialized generator instance.
    """
    generator_class = get_generator_class(generation_type)
    return generator_class()
'''

factory.write_text(text, encoding="utf-8")

print("OK: factory.py updated.")
