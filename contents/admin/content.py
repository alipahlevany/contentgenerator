from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from contents.models import Content, EmailReply, Greeting


class BaseContentAdmin(admin.ModelAdmin):
    content_type_value = None

    list_display = (
        "id",
        "title",
        "source_job",
        "language",
        "topic",
        "audience",
        "goal",
        "prompt_template",
        "status",
        "created_at",
    )
    list_display_links = ("id", "title")

    search_fields = (
        "title",
        "prompt",
        "generated_content",
        "content_hash",
    )

    list_filter = (
        "status",
        "language",
        "topic",
        "audience",
        "goal",
        "prompt_template",
        "created_at",
    )

    filter_horizontal = ("rules",)

    readonly_fields = (
        "content_hash",
        "generation_job",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Generated Output",
            {
                "fields": (
                    "title",
                    "generated_content",
                    "content_hash",
                )
            },
        ),
        (
            "Content Settings",
            {
                "fields": (
                    ("language", "topic"),
                    ("audience", "goal"),
                    "prompt_template",
                    "rules",
                    "status",
                    "generation_job",
                )
            },
        ),
        (
            "Prompt",
            {
                "fields": (
                    "prompt",
                )
            },
        ),
        (
            "Dates",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related(
            "generation_job",
        )

        if self.content_type_value is None:
            return queryset

        return queryset.filter(
            content_type=self.content_type_value,
        )

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    @admin.display(description="Source job", ordering="generation_job_id")
    def source_job(self, obj):
        if not obj.generation_job_id:
            return "—"

        url = reverse(
            "admin:contents_generationjob_change",
            args=(obj.generation_job_id,),
        )
        return format_html(
            '<a href="{}">Job #{}</a>',
            url,
            obj.generation_job_id,
        )

    def save_model(self, request, obj, form, change):
        if self.content_type_value is not None:
            obj.content_type = self.content_type_value

        super().save_model(
            request,
            obj,
            form,
            change,
        )


class ContentAdmin(BaseContentAdmin):
    content_type_value = "standard"


class EmailReplyAdmin(BaseContentAdmin):
    content_type_value = "email_reply"

    list_display = (
        "id",
        "title",
        "source_job",
        "language",
        "topic",
        "audience",
        "goal",
        "status",
        "created_at",
    )



class GreetingAdmin(BaseContentAdmin):
    content_type_value = "greeting"

    list_display = (
        "id",
        "title",
        "source_job",
        "language",
        "status",
        "created_at",
    )

    list_filter = (
        "status",
        "language",
        "created_at",
    )

    filter_horizontal = ()

    fieldsets = (
        (
            "👋 Greeting",
            {
                "fields": (
                    "title",
                    "generated_content",
                    "content_hash",
                ),
            },
        ),
        (
            "🌐 Language",
            {
                "fields": (
                    "language",
                    "status",
                    "generation_job",
                ),
            },
        ),
        (
            "Prompt",
            {
                "fields": (
                    "prompt",
                ),
            },
        ),
        (
            "Dates",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )
