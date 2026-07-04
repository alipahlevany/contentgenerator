from django.contrib import admin

from contents.models import GenerationJobLog


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