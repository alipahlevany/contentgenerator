from pathlib import Path

models_path = Path("contents/models.py")

if not models_path.exists():
    raise SystemExit("ERROR: contents/models.py not found.")

content = models_path.read_text(encoding="utf-8")

if "class GenerationType(models.Model):" in content:
    raise SystemExit("GenerationType already exists. Nothing changed.")

model_code = r'''

class GenerationType(models.Model):
    """
    Defines a type of AI generation such as Standard, Reply, or Greeting.

    This model is additive and is not connected to the current generation
    pipeline yet, so existing Standard and Email Reply jobs remain unchanged.
    """

    key = models.SlugField(
        max_length=50,
        unique=True,
        help_text="Unique identifier, for example: standard, reply, greeting.",
    )

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    description = models.TextField(
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Generation Type"
        verbose_name_plural = "Generation Types"

    def __str__(self):
        return self.name
'''

updated_content = content.rstrip() + model_code + "\n"
models_path.write_text(updated_content, encoding="utf-8")

print("OK: GenerationType added to contents/models.py")
