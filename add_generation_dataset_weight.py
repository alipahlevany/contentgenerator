from pathlib import Path

path = Path("contents/models.py")

text = path.read_text(encoding="utf-8")

if "Relative weight used when this dataset participates in generation." in text:
    print("weight field already exists.")
    raise SystemExit(0)

target = """    selection_order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Lower values are selected first.",
    )

    is_active = models.BooleanField(
"""

replacement = """    selection_order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Lower values are selected first.",
    )

    weight = models.PositiveSmallIntegerField(
        default=100,
        help_text="Relative weight used when this dataset participates in generation.",
    )

    is_active = models.BooleanField(
"""

if target not in text:
    raise SystemExit("Target block not found.")

text = text.replace(target, replacement)

path.write_text(text, encoding="utf-8")

print("OK: weight field added.")
