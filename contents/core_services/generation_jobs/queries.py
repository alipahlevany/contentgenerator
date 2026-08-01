from dataclasses import dataclass
from typing import Any, Optional

from django.db.models import Prefetch

from contents.core_services.pagination import (
    InvalidCursor,
    cursor_mode_requested,
    paginate_queryset,
)
from contents.models import (
    Audience,
    ContentRule,
    GenerationJob,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)


@dataclass
class GenerationJobListResult:
    jobs: Any
    next_cursor: Optional[str]
    cursor_mode: bool
    error: Optional[str] = None


def get_generation_jobs_for_client(
    *,
    client,
    request,
) -> GenerationJobListResult:
    queryset = (
        GenerationJob.objects
        .filter(external_client=client)
        .prefetch_related(
            Prefetch(
                "languages",
                queryset=(
                    Language.objects
                    .filter(is_active=True)
                    .order_by("id")
                ),
                to_attr="active_languages",
            ),
            Prefetch(
                "topics",
                queryset=(
                    Topic.objects
                    .filter(is_active=True)
                    .order_by("id")
                ),
                to_attr="active_topics",
            ),
            Prefetch(
                "audiences",
                queryset=(
                    Audience.objects
                    .filter(is_active=True)
                    .order_by("id")
                ),
                to_attr="active_audiences",
            ),
            Prefetch(
                "goals",
                queryset=(
                    Goal.objects
                    .filter(is_active=True)
                    .order_by("id")
                ),
                to_attr="active_goals",
            ),
            Prefetch(
                "rules",
                queryset=(
                    ContentRule.objects
                    .filter(is_active=True)
                    .order_by("id")
                ),
                to_attr="active_rules",
            ),
            Prefetch(
                "prompt_templates",
                queryset=(
                    PromptTemplate.objects
                    .filter(is_active=True)
                    .order_by("id")
                ),
                to_attr="active_prompt_templates",
            ),
        )
        .order_by("-created_at", "-id")
    )

    cursor_mode = cursor_mode_requested(request)

    if cursor_mode:
        try:
            jobs, next_cursor = paginate_queryset(
                queryset,
                request,
            )
        except InvalidCursor as exc:
            return GenerationJobListResult(
                jobs=[],
                next_cursor=None,
                cursor_mode=True,
                error=str(exc),
            )
    else:
        jobs = queryset[:100]
        next_cursor = None

    return GenerationJobListResult(
        jobs=jobs,
        next_cursor=next_cursor,
        cursor_mode=cursor_mode,
    )
