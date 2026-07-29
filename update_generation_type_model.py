from pathlib import Path

models_path = Path("contents/models.py")

if not models_path.exists():
    raise SystemExit("ERROR: contents/models.py not found.")

content = models_path.read_text(encoding="utf-8")

old_block = '''    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )
'''

new_block = '''    uses_language = models.BooleanField(
        default=True,
        help_text="Whether this generation type uses the Language dataset.",
    )

    uses_topic = models.BooleanField(
        default=False,
        help_text="Whether this generation type uses the Topic dataset.",
    )

    uses_audience = models.BooleanField(
        default=False,
        help_text="Whether this generation type uses the Audience dataset.",
    )

    uses_goal = models.BooleanField(
        default=False,
        help_text="Whether this generation type uses the Goal dataset.",
    )

    uses_prompt_template = models.BooleanField(
        default=False,
        help_text="Whether this generation type uses the legacy PromptTemplate model.",
    )

    uses_content_rules = models.BooleanField(
        default=False,
        help_text="Whether this generation type uses ContentRule records.",
    )

    supports_delivery = models.BooleanField(
        default=False,
        help_text="Whether generated content may be delivered to an external client.",
    )

    allowed_placeholders = models.JSONField(
        default=list,
        blank=True,
        help_text='Allowed placeholders, for example: ["[[email]]", "[[name]]"].',
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )
'''

if "uses_language = models.BooleanField(" in content:
    raise SystemExit("GenerationType is already updated. Nothing changed.")

if old_block not in content:
    raise SystemExit(
        "ERROR: Expected GenerationType block was not found. Nothing changed."
    )

# فقط آخرین occurrence را تغییر می‌دهیم تا is_active مدل‌های قبلی دست نخورد.
before, separator, after = content.rpartition(old_block)

if not separator:
    raise SystemExit("ERROR: Could not locate target block.")

updated = before + new_block + after
models_path.write_text(updated, encoding="utf-8")

print("OK: GenerationType configuration fields added.")
