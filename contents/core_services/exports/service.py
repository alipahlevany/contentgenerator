from dataclasses import dataclass
from typing import Any, List

from django.db import IntegrityError, transaction
from django.utils import timezone

from contents.core_services.client_limits import (
    lock_client_limit,
    remaining_daily_export_quota,
)
from contents.models import Content, ContentExport

from .query import build_export_queryset


@dataclass
class ExportResult:
    requested: int
    exported_contents: List[Any]
    remaining: int
    quota_exceeded: bool = False


def _mark_export_success(export):
    export.status = "success"
    export.exported_at = timezone.now()
    export.error_message = ""

    export.save(
        update_fields=[
            "status",
            "exported_at",
            "error_message",
            "updated_at",
        ]
    )


def _record_successful_export(
    *,
    content,
    client,
):
    export = (
        ContentExport.objects
        .filter(
            content=content,
            client=client,
            content_hash=content.content_hash,
        )
        .first()
    )

    if export is not None:
        if export.status == "success":
            return False

        _mark_export_success(export)
        return True

    try:
        with transaction.atomic():
            ContentExport.objects.create(
                content=content,
                client=client,
                content_hash=content.content_hash,
                status="success",
                exported_at=timezone.now(),
            )

        return True

    except IntegrityError:
        # Another concurrent request may have created the row.
        export = (
            ContentExport.objects
            .filter(
                content=content,
                client=client,
                content_hash=content.content_hash,
            )
            .first()
        )

        if export is None:
            raise

        if export.status == "success":
            return False

        _mark_export_success(export)
        return True


def export_contents_for_client(
    *,
    validated_data,
    client,
    content_type,
) -> ExportResult:
    requested_count = validated_data["count"]
    exported_contents = []

    with transaction.atomic():
        lock_client_limit(
            client.pk,
            "export",
        )

        remaining_quota = (
            remaining_daily_export_quota(client)
        )

        if remaining_quota == 0:
            return ExportResult(
                requested=requested_count,
                exported_contents=[],
                remaining=0,
                quota_exceeded=True,
            )

        effective_count = (
            requested_count
            if remaining_quota is None
            else min(
                requested_count,
                remaining_quota,
            )
        )

        candidate_ids = list(
            build_export_queryset(
                validated_data=validated_data,
                client=client,
                content_type=content_type,
            )
            .values_list(
                "id",
                flat=True,
            )[:effective_count]
        )

        candidates = list(
            Content.objects
            .filter(id__in=candidate_ids)
            .select_for_update(of=("self",))
            .select_related(
                "language",
                "topic",
                "audience",
                "goal",
                "prompt_template",
            )
            .prefetch_related("rules")
            .order_by("id")
        )

        for content in candidates:
            recorded = _record_successful_export(
                content=content,
                client=client,
            )

            if recorded:
                exported_contents.append(content)

        remaining = (
            build_export_queryset(
                validated_data=validated_data,
                client=client,
                content_type=content_type,
            )
            .count()
        )

    return ExportResult(
        requested=requested_count,
        exported_contents=exported_contents,
        remaining=remaining,
    )
