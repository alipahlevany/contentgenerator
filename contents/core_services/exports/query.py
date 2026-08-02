from django.db.models import Exists, OuterRef

from contents.models import Content, ContentExport


FILTER_MAP = {
    "languages": "language_id__in",
    "topics": "topic_id__in",
    "audiences": "audience_id__in",
    "goals": "goal_id__in",
    "prompt_templates": "prompt_template_id__in",
}


def build_export_queryset(
    *,
    validated_data,
    client,
    content_type,
):
    """
    Build the queryset of generated content versions that have not
    already been exported successfully to this client.
    """
    successful_export = (
        ContentExport.objects
        .filter(
            client=client,
            content_id=OuterRef("pk"),
            content_hash=OuterRef("content_hash"),
            status="success",
        )
    )

    queryset = (
        Content.objects
        .filter(
            status="generated",
            content_type=content_type,
        )
        .annotate(
            already_exported=Exists(successful_export)
        )
        .filter(already_exported=False)
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

    for request_field, lookup in FILTER_MAP.items():
        selection = validated_data.get(
            request_field,
            "all",
        )

        if selection != "all":
            queryset = queryset.filter(
                **{
                    lookup: selection,
                }
            )

    rule_selection = validated_data.get(
        "rules",
        "all",
    )

    if (
        rule_selection != "all"
        and rule_selection
    ):
        queryset = queryset.filter(
            rules__id__in=rule_selection,
        ).distinct()

    return queryset
