from pathlib import Path

pipeline_dir = Path("contents/core_services/pipeline")
validator_path = pipeline_dir / "validator.py"

validator_code = '''from dataclasses import dataclass
from typing import Optional


@dataclass
class ValidationResult:
    ok: bool
    event_type: Optional[str] = None
    message: Optional[str] = None
    failure_kind: Optional[str] = None


def validate_generated_text(generated_text):
    """
    Validate raw OpenAI output before extraction.
    """
    if not generated_text or not generated_text.strip():
        return ValidationResult(
            ok=False,
            event_type="error",
            message="OpenAI returned empty content.",
            failure_kind="empty",
        )

    return ValidationResult(ok=True)


def validate_content_body(content_body):
    """
    Validate extracted content body.
    """
    if not content_body or not content_body.strip():
        return ValidationResult(
            ok=False,
            event_type="blocked",
            message="Content body became empty after cleanup.",
            failure_kind="empty",
        )

    return ValidationResult(ok=True)


def validate_final_blocked_keyword(
    has_blocked_keyword,
    blocked_keyword,
):
    """
    Validate final extracted output for blocked keywords.
    """
    if has_blocked_keyword:
        return ValidationResult(
            ok=False,
            event_type="blocked",
            message=(
                "Blocked keyword found after final extraction: "
                f"{blocked_keyword}"
            ),
            failure_kind="failed",
        )

    return ValidationResult(ok=True)
'''

validator_path.write_text(
    validator_code,
    encoding="utf-8",
)

print("OK: validator.py created.")
