from django.contrib import admin

from contents.models import Content, EmailReply


class BaseContentAdmin(admin.ModelAdmin):
    content_type_value = None

    list_display = (
        "id",
        "title",
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
        queryset = super().get_queryset(request)

        if self.content_type_value is None:
            return queryset

        return queryset.filter(
            content_type=self.content_type_value,
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
        "language",
        "topic",
        "audience",
        "goal",
        "status",
        "created_at",
    )
