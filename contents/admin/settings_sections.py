from django.contrib import admin, messages
from django.db import transaction
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from contents.models import (
    GreetingGenerationSettings,
    ReplyGenerationSettings,
    SharedGenerationSettings,
    StandardGenerationSettings,
)
from contents.tasks import (
    run_daily_generation_task,
    run_daily_greeting_generation_task,
    run_daily_reply_generation_task,
)

from .settings_forms import (
    GreetingGenerationSettingsForm,
    ReplyGenerationSettingsForm,
    SharedGenerationSettingsForm,
    StandardGenerationSettingsForm,
)


class BaseSectionSettingsAdmin(admin.ModelAdmin):
    change_form_template = (
        "admin/settings/change_form.html"
    )

    list_display = (
        "id",
        "section_status",
        "updated_display",
    )

    list_display_links = ("id",)

    theme_key = "shared"
    section_icon = "⚙️"
    section_title = "Generation Settings"
    section_description = ""
    run_task = None
    run_label = None
    enabled_field = None
    last_run_field = None

    class Media:
        css = {
            "all": (
                "admin/content_generator_admin.css",
            )
        }

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .order_by("-id")
        )

    def section_status(self, obj):
        if self.enabled_field is None:
            enabled = getattr(
                obj,
                "is_active",
                True,
            )
        else:
            enabled = getattr(
                obj,
                self.enabled_field,
                False,
            )

        if enabled:
            return format_html(
                '<span class="cg-badge cg-badge-on">'
                "● Enabled"
                "</span>"
            )

        return format_html(
            '<span class="cg-badge cg-badge-off">'
            "● Disabled"
            "</span>"
        )

    section_status.short_description = "Status"

    def updated_display(self, obj):
        value = getattr(obj, "updated_at", None)

        if value:
            return timezone.localtime(value).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        return "-"

    updated_display.short_description = "Updated"

    def get_urls(self):
        urls = super().get_urls()

        if self.run_task is None:
            return urls

        opts = self.model._meta

        custom = [
            path(
                "run-now/",
                self.admin_site.admin_view(
                    self.run_now_view
                ),
                name=(
                    f"{opts.app_label}_"
                    f"{opts.model_name}_run_now"
                ),
            ),
        ]

        return custom + urls

    def run_now_view(self, request):
        if self.run_task is None:
            self.message_user(
                request,
                "No generation task is configured.",
                messages.ERROR,
            )

            return self._get_changelist_redirect()

        transaction.on_commit(
            lambda: self.run_task.delay(
                force=True
            )
        )

        self.message_user(
            request,
            (
                f"{self.run_label} was queued "
                "successfully."
            ),
            messages.SUCCESS,
        )

        return self._get_changelist_redirect()

    def _get_changelist_redirect(self):
        from django.shortcuts import redirect

        opts = self.model._meta

        return redirect(
            reverse(
                (
                    f"admin:{opts.app_label}_"
                    f"{opts.model_name}_changelist"
                )
            )
        )

    def render_change_form(
        self,
        request,
        context,
        *args,
        **kwargs,
    ):
        context.update(
            {
                "cg_theme": self.theme_key,
                "cg_icon": self.section_icon,
                "cg_title": self.section_title,
                "cg_description": (
                    self.section_description
                ),
                "cg_run_label": self.run_label,
                "cg_run_url": (
                    self._get_run_url()
                    if self.run_task
                    else None
                ),
            }
        )

        return super().render_change_form(
            request,
            context,
            *args,
            **kwargs,
        )

    def _get_run_url(self):
        opts = self.model._meta

        return reverse(
            (
                f"admin:{opts.app_label}_"
                f"{opts.model_name}_run_now"
            )
        )


@admin.register(StandardGenerationSettings)
class StandardGenerationSettingsAdmin(
    BaseSectionSettingsAdmin
):
    form = StandardGenerationSettingsForm

    theme_key = "standard"
    section_icon = "📝"
    section_title = "Standard Generation"
    section_description = (
        "Configure normal AI content generation, "
        "content length and its automatic daily schedule."
    )

    run_task = run_daily_generation_task
    run_label = "Run Standard Generation Now"

    enabled_field = (
        "auto_daily_generation_enabled"
    )

    readonly_fields = (
        "last_daily_generation_date",
    )

    fieldsets = (
        (
            "📝 Standard Content",
            {
                "fields": (
                    (
                        "min_words",
                        "max_words",
                    ),
                    "default_generation_job",
                ),
            },
        ),
        (
            "⏰ Automatic Daily Standard Generation",
            {
                "fields": (
                    "auto_daily_generation_enabled",
                    "daily_generation_count",
                    "daily_generation_time",
                    "daily_generation_delay_seconds",
                    "last_daily_generation_date",
                ),
            },
        ),
    )


@admin.register(ReplyGenerationSettings)
class ReplyGenerationSettingsAdmin(
    BaseSectionSettingsAdmin
):
    form = ReplyGenerationSettingsForm

    theme_key = "reply"
    section_icon = "✉️"
    section_title = "Email Reply Generation"
    section_description = (
        "Configure automatic generation of natural "
        "email reply content."
    )

    run_task = run_daily_reply_generation_task
    run_label = "Run Email Reply Generation Now"

    enabled_field = (
        "auto_daily_reply_generation_enabled"
    )

    readonly_fields = (
        "last_daily_reply_generation_date",
    )

    fieldsets = (
        (
            "✉️ Automatic Daily Email Replies",
            {
                "fields": (
                    "auto_daily_reply_generation_enabled",
                    "daily_reply_generation_count",
                    "daily_reply_generation_time",
                    "daily_reply_generation_delay_seconds",
                    "last_daily_reply_generation_date",
                ),
            },
        ),
    )


@admin.register(GreetingGenerationSettings)
class GreetingGenerationSettingsAdmin(
    BaseSectionSettingsAdmin
):
    form = GreetingGenerationSettingsForm

    theme_key = "greeting"
    section_icon = "👋"
    section_title = "Greeting Generation"
    section_description = (
        "Configure language-based greeting generation "
        "and its independent automatic daily schedule."
    )

    run_task = run_daily_greeting_generation_task
    run_label = "Run Greeting Generation Now"

    enabled_field = (
        "auto_daily_greeting_generation_enabled"
    )

    readonly_fields = (
        "last_daily_greeting_generation_date",
    )

    fieldsets = (
        (
            "👋 Automatic Daily Greetings",
            {
                "fields": (
                    "auto_daily_greeting_generation_enabled",
                    "daily_greeting_generation_count",
                    "daily_greeting_generation_time",
                    "daily_greeting_generation_delay_seconds",
                    "last_daily_greeting_generation_date",
                ),
            },
        ),
    )


@admin.register(SharedGenerationSettings)
class SharedGenerationSettingsAdmin(
    BaseSectionSettingsAdmin
):
    form = SharedGenerationSettingsForm

    theme_key = "shared"
    section_icon = "⚙️"
    section_title = "Shared Generation Settings"
    section_description = (
        "Settings shared by the generation system, "
        "including AI model, limits and dataset refill."
    )

    fieldsets = (
        (
            "🤖 AI Runtime",
            {
                "fields": (
                    "model_name",
                    "max_output_tokens",
                    "temperature",
                ),
            },
        ),
        (
            "🛡️ Generation Safety Limits",
            {
                "fields": (
                    "generation_attempt_multiplier",
                    "generation_minimum_attempts",
                    "generation_max_runtime_seconds",
                ),
            },
        ),
        (
            "🧠 Dataset Intelligence & Refill",
            {
                "fields": (
                    "auto_refill_enabled",
                    "auto_refill_skip_threshold",
                    "auto_refill_item_count",
                ),
            },
        ),
        (
            "⚙️ System",
            {
                "fields": (
                    "is_active",
                ),
            },
        ),
    )
