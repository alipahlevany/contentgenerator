from pathlib import Path

models_path = Path("contents/models.py")
models_code = models_path.read_text(encoding="utf-8")

model_name = "class GenerationFingerprint(models.Model):"

if model_name in models_code:
    raise SystemExit(
        "SKIP: GenerationFingerprint already exists."
    )

model_code = r'''


class GenerationFingerprint(models.Model):
    STATUS_RESERVED = "reserved"
    STATUS_GENERATED = "generated"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = (
        (STATUS_RESERVED, "Reserved"),
        (STATUS_GENERATED, "Generated"),
        (STATUS_FAILED, "Failed"),
    )

    fingerprint = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
    )

    generation_type = models.ForeignKey(
        "GenerationType",
        on_delete=models.CASCADE,
        related_name="generation_fingerprints",
    )

    job = models.ForeignKey(
        "GenerationJob",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="generation_fingerprints",
    )

    content = models.ForeignKey(
        "Content",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="generation_fingerprints",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_RESERVED,
        db_index=True,
    )

    attempt_count = models.PositiveIntegerField(
        default=1,
    )

    reserved_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
    )

    generated_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    failed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    last_error = models.TextField(
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ("-updated_at",)
        indexes = [
            models.Index(
                fields=["generation_type", "status"],
                name="genfp_type_status_idx",
            ),
            models.Index(
                fields=["status", "reserved_at"],
                name="genfp_status_reserved_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.generation_type_id}:"
            f"{self.fingerprint[:12]}:"
            f"{self.status}"
        )
'''

models_path.write_text(
    models_code.rstrip() + model_code + "\n",
    encoding="utf-8",
)

print("OK: GenerationFingerprint model added.")
