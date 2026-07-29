from pathlib import Path

models_path = Path("contents/models.py")

if not models_path.exists():
    raise SystemExit("ERROR: contents/models.py not found.")

content = models_path.read_text(encoding="utf-8")

start_marker = "class GenerationType(models.Model):"

if start_marker not in content:
    raise SystemExit("ERROR: GenerationType model not found.")

if "class DatasetCategory(models.Model):" in content:
    raise SystemExit(
        "DatasetCategory already exists. Nothing changed."
    )

before, _, generation_block = content.partition(start_marker)

# چون GenerationType آخر فایل است، کل بخش انتهایی را با نسخه نهایی جایگزین می‌کنیم.
new_models = r'''class GenerationType(models.Model):
    """
    Defines a configurable AI generation type.

    Existing Standard and Email Reply generation flows are not connected
    to this model yet.
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


class DatasetCategory(models.Model):
    """
    Defines a configurable dataset category such as Language, Topic,
    Audience, Goal, Tone, or Persona.
    """

    key = models.SlugField(
        max_length=50,
        unique=True,
        help_text="Unique identifier, for example: language, topic, tone.",
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
        verbose_name = "Dataset Category"
        verbose_name_plural = "Dataset Categories"

    def __str__(self):
        return self.name


class GenerationTypeDataset(models.Model):
    """
    Connects a GenerationType to the dataset categories it uses.
    """

    generation_type = models.ForeignKey(
        GenerationType,
        on_delete=models.CASCADE,
        related_name="dataset_links",
    )

    dataset_category = models.ForeignKey(
        DatasetCategory,
        on_delete=models.CASCADE,
        related_name="generation_type_links",
    )

    is_required = models.BooleanField(
        default=True,
    )

    selection_order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Lower values are selected first.",
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
        ordering = [
            "generation_type",
            "selection_order",
            "dataset_category",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "generation_type",
                    "dataset_category",
                ],
                name="unique_generation_type_dataset",
            ),
        ]
        verbose_name = "Generation Type Dataset"
        verbose_name_plural = "Generation Type Datasets"

    def __str__(self):
        return (
            f"{self.generation_type.name} → "
            f"{self.dataset_category.name}"
        )
'''

models_path.write_text(
    before.rstrip() + "\n\n\n" + new_models + "\n",
    encoding="utf-8",
)

print("OK: Generation V2 models rebuilt successfully.")
