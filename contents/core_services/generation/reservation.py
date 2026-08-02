from dataclasses import dataclass
from typing import Any, Dict, Optional

from contents.core_services.dataset_resolver import DatasetResolver
from contents.models import GenerationType
from contents.core_services.generation.fingerprint import (
    make_generation_fingerprint,
    reserve_fingerprint,
)

DEFAULT_MAX_RESERVATION_ATTEMPTS = 20


@dataclass
class GenerationContextReservation:
    acquired: bool
    context: Optional[Dict[str, Any]]
    fingerprint: Optional[str]
    record: Any = None
    reason: Optional[str] = None
    attempts: int = 0


def _obj(value):
    if value is None:
        return None

    return {
        "model": value._meta.label_lower,
        "pk": value.pk,
    }


def build_context_fingerprint_payload(
    context: Dict[str, Any],
) -> Dict[str, Any]:
    selected_rules = context.get("selected_rules") or []

    return {
        "language": _obj(context.get("language")),
        "topic": _obj(context.get("topic")),
        "audience": _obj(context.get("audience")),
        "goal": _obj(context.get("goal")),
        "prompt_template": _obj(
            context.get("prompt_template")
        ),
        "rules": sorted(
            rule.pk
            for rule in selected_rules
            if getattr(rule, "pk", None) is not None
        ),
    }


def _get_generation_type_key(job) -> str:
    generation_type = job.generation_type

    if hasattr(generation_type, "key"):
        return str(generation_type.key)

    if hasattr(generation_type, "slug"):
        return str(generation_type.slug)

    return str(generation_type)


def _get_generation_type_instance(job):
    generation_type = job.generation_type

    if isinstance(generation_type, GenerationType):
        return generation_type

    generation_type_key = _get_generation_type_key(job)

    return GenerationType.objects.get(
        key=generation_type_key,
        is_active=True,
    )


def reserve_generation_context(
    *,
    job,
    generator,
    random_module,
    max_attempts: int = DEFAULT_MAX_RESERVATION_ATTEMPTS,
) -> GenerationContextReservation:
    """
    Resolve dataset combinations until a free fingerprint
    is reserved or the maximum attempt count is reached.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1.")

    last_reason = None

    for attempt in range(1, max_attempts + 1):
        context = DatasetResolver.resolve(
            job=job,
            generator=generator,
            random_module=random_module,
        )

        payload = build_context_fingerprint_payload(
            context
        )

        fingerprint = make_generation_fingerprint(
            generation_type_key=(
                _get_generation_type_key(job)
            ),
            components=payload,
        )

        reservation = reserve_fingerprint(
            fingerprint=fingerprint,
            generation_type=(
                _get_generation_type_instance(job)
            ),
            job=job,
        )

        last_reason = reservation.reason

        if reservation.acquired:
            return GenerationContextReservation(
                acquired=True,
                context=context,
                fingerprint=fingerprint,
                record=reservation.record,
                reason=reservation.reason,
                attempts=attempt,
            )

    return GenerationContextReservation(
        acquired=False,
        context=None,
        fingerprint=None,
        record=None,
        reason=(
            last_reason
            or "no_available_context"
        ),
        attempts=max_attempts,
    )
