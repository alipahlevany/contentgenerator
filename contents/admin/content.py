from django.contrib import admin

from contents.models import Content


class ContentAdmin(admin.ModelAdmin):
    list_display = (
        "id", "title", "language", "topic", "audience",
        "goal", "prompt_template", "status", "created_at",
    )
    list_display_links = ("id", "title")
    search_fields = ("title", "prompt", "generated_content", "content_hash")
    list_filter = (
        "status", "language", "topic", "audience",
        "goal", "prompt_template", "created_at",
    )
    filter_horizontal = ("rules",)
    readonly_fields = ("content_hash", "created_at", "updated_at")

    fieldsets = (
        ("Generated Output", {"fields": ("title", "generated_content", "content_hash")}),
        ("Content Settings", {
            "fields": (
                ("language", "topic"),
                ("audience", "goal"),
                "prompt_template",
                "rules",
                "status",
            )
        }),
        ("Prompt", {"fields": ("prompt",)}),
        ("Dates", {"fields": ("created_at", "updated_at")}),
    )