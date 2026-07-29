from pathlib import Path

service_path = Path(
    "contents/core_services/generation/fingerprint.py"
)

service_code = '''import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Optional

from django.db import IntegrityError, transaction
from django.utils import timezone

from contents.models import GenerationFingerprint


DEFAULT_RESERVATION_TIMEOUT_MINUTES = 30


@dataclass
class FingerprintReservationResult:
    acquired: bool
    fingerprint: str
    record: Optional[GenerationFingerprint] = None
    reason: Optional[str] = None


def _serialize_component(value: Any) -> Any:
    """
    Convert fingerprint components into stable JSON-compatible values.
    """
    if value is None:
        return None

    if isinstance(value, dict):
        return {
            str(key): _serialize_component(value[key])
            for key in sorted(value.keys(), key=str)
        }

    if isinstance(value, (list, tuple, set)):
        serialized_values = [
            _serialize_component(item)
            for item in value
        ]

        return sorted(
            serialized_values,
            key=lambda item: json.dumps(
                item,
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            ),
        )

    if hasattr(value, "pk"):
        return {
            "model": value._meta.label_lower,
            "pk": value.pk,
        }

    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def make_generation_fingerprint(
    generation_type_key: str,
    components: Dict[str, Any],
    variation_key: Optional[str] = None,
) -> str:
    """
    Build a deterministic SHA-256 fingerprint.

    variation_key must later affect the actual generation prompt as well.
    Otherwise different fingerprints could represent the same OpenAI request.
    """
    payload = {
        "generation_type": str(generation_type_key).strip().lower(),
        "components": _serialize_component(components),
        "variation_key": (
            str(variation_key).strip()
            if variation_key is not None
            else None
        ),
    }

    canonical_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )

    return hashlib.sha256(
        canonical_payload.encode("utf-8")
    ).hexdigest()


def reserve_fingerprint(
    *,
    fingerprint: str,
    generation_type,
    job=None,
    reservation_timeout_minutes: int = (
        DEFAULT_RESERVATION_TIMEOUT_MINUTES
    ),
) -> FingerprintReservationResult:
    """
    Atomically reserve a fingerprint.

    Rules:
    - generated fingerprints cannot be reserved again;
    - active reservations cannot be acquired by another worker;
    - failed fingerprints may be retried;
    - stale reservations may be reclaimed.
    """
    now = timezone.now()
    stale_before = now - timedelta(
        minutes=reservation_timeout_minutes
    )

    try:
        with transaction.atomic():
            try:
                record = (
                    GenerationFingerprint.objects
                    .select_for_update()
                    .get(fingerprint=fingerprint)
                )
            except GenerationFingerprint.DoesNotExist:
                try:
                    record = GenerationFingerprint.objects.create(
                        fingerprint=fingerprint,
                        generation_type=generation_type,
                        job=job,
                        status=(
                            GenerationFingerprint.STATUS_RESERVED
                        ),
                        attempt_count=1,
                        reserved_at=now,
                        generated_at=None,
                        failed_at=None,
                        last_error="",
                    )

                    return FingerprintReservationResult(
                        acquired=True,
                        fingerprint=fingerprint,
                        record=record,
                        reason="created",
                    )
                except IntegrityError:
                    record = (
                        GenerationFingerprint.objects
                        .select_for_update()
                        .get(fingerprint=fingerprint)
                    )

            if (
                record.status
                == GenerationFingerprint.STATUS_GENERATED
            ):
                return FingerprintReservationResult(
                    acquired=False,
                    fingerprint=fingerprint,
                    record=record,
                    reason="already_generated",
                )

            reservation_is_active = (
                record.status
                == GenerationFingerprint.STATUS_RESERVED
                and record.reserved_at is not None
                and record.reserved_at > stale_before
            )

            if reservation_is_active:
                return FingerprintReservationResult(
                    acquired=False,
                    fingerprint=fingerprint,
                    record=record,
                    reason="already_reserved",
                )

            record.generation_type = generation_type
            record.job = job
            record.status = GenerationFingerprint.STATUS_RESERVED
            record.attempt_count += 1
            record.reserved_at = now
            record.generated_at = None
            record.failed_at = None
            record.last_error = ""

            record.save(
                update_fields=[
                    "generation_type",
                    "job",
                    "status",
                    "attempt_count",
                    "reserved_at",
                    "generated_at",
                    "failed_at",
                    "last_error",
                    "updated_at",
                ]
            )

            return FingerprintReservationResult(
                acquired=True,
                fingerprint=fingerprint,
                record=record,
                reason="reclaimed",
            )

    except IntegrityError:
        return FingerprintReservationResult(
            acquired=False,
            fingerprint=fingerprint,
            reason="reservation_conflict",
        )


def complete_fingerprint(
    *,
    fingerprint: str,
    content=None,
) -> bool:
    """
    Mark a reserved fingerprint as successfully generated.
    """
    now = timezone.now()

    with transaction.atomic():
        try:
            record = (
                GenerationFingerprint.objects
                .select_for_update()
                .get(fingerprint=fingerprint)
            )
        except GenerationFingerprint.DoesNotExist:
            return False

        record.status = GenerationFingerprint.STATUS_GENERATED
        record.content = content
        record.generated_at = now
        record.failed_at = None
        record.last_error = ""

        record.save(
            update_fields=[
                "status",
                "content",
                "generated_at",
                "failed_at",
                "last_error",
                "updated_at",
            ]
        )

    return True


def fail_fingerprint(
    *,
    fingerprint: str,
    error_message: str = "",
) -> bool:
    """
    Mark a reservation as failed so that it may be retried later.
    """
    now = timezone.now()

    with transaction.atomic():
        try:
            record = (
                GenerationFingerprint.objects
                .select_for_update()
                .get(fingerprint=fingerprint)
            )
        except GenerationFingerprint.DoesNotExist:
            return False

        if (
            record.status
            == GenerationFingerprint.STATUS_GENERATED
        ):
            return False

        record.status = GenerationFingerprint.STATUS_FAILED
        record.failed_at = now
        record.last_error = str(error_message or "")[:5000]

        record.save(
            update_fields=[
                "status",
                "failed_at",
                "last_error",
                "updated_at",
            ]
        )

    return True
'''

service_path.write_text(
    service_code,
    encoding="utf-8",
)

print("OK: generation fingerprint service created.")
