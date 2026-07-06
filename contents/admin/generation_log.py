from django.contrib import admin

from contents.models import (
    DatasetEvent,
    DatasetPerformance,
    GenerationJobLog,
    GenerationPattern,
)


class GenerationJobLogAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "level", "message", "created_at")
    list_display_links = ("id", "job")
    list_filter = ("level", "created_at")
    search_fields = ("message",)
    ordering = ("-created_at",)

    readonly_fields = (
        "job",
        "level",
        "message",
        "created_at",
    )


class DatasetEventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "item_type",
        "item_id",
        "event_type",
        "job",
        "content",
        "created_at",
    )

    list_filter = (
        "item_type",
        "event_type",
        "created_at",
    )

    search_fields = (
        "message",
    )

    ordering = ("-created_at",)

    readonly_fields = (
        "item_type",
        "item_id",
        "event_type",
        "job",
        "content",
        "message",
        "created_at",
    )


class DatasetPerformanceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "item_type",
        "item_id",
        "quality_score",
        "success_count",
        "skip_count",
        "duplicate_count",
        "blocked_count",
        "error_count",
        "last_used_at",
    )

    list_filter = (
        "item_type",
        "quality_score",
        "updated_at",
    )

    search_fields = (
        "item_id",
    )

    ordering = ("-quality_score", "-updated_at")

    readonly_fields = (
        "item_type",
        "item_id",
        "success_count",
        "skip_count",
        "duplicate_count",
        "blocked_count",
        "error_count",
        "quality_score",
        "last_used_at",
        "updated_at",
    )


class GenerationPatternAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "language",
        "topic",
        "audience",
        "goal",
        "prompt_template",
        "quality_score",
        "confidence",
        "success_count",
        "skip_count",
        "duplicate_count",
        "blocked_count",
        "error_count",
        "last_used_at",
    )

    list_filter = (
        "language",
        "topic",
        "audience",
        "goal",
        "prompt_template",
        "quality_score",
        "confidence",
        "updated_at",
    )

    search_fields = (
        "topic__name",
        "audience__name",
        "goal__name",
        "prompt_template__name",
        "language__name",
    )

    ordering = ("-quality_score", "-confidence", "-updated_at")

    readonly_fields = (
        "language",
        "topic",
        "audience",
        "goal",
        "prompt_template",
        "success_count",
        "skip_count",
        "duplicate_count",
        "blocked_count",
        "error_count",
        "quality_score",
        "confidence",
        "last_used_at",
        "updated_at",
    )