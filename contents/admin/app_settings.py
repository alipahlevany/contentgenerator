import secrets

from django.contrib import admin, messages
from django.core.cache import cache
from django.utils.html import format_html

from contents.admin.forms import AppSettingsForm
from contents.models import AppSettings
from contents.tasks import run_daily_generation_task


class AppSettingsAdmin(admin.ModelAdmin):
    form = AppSettingsForm

    actions = (
        "regenerate_api_token",
        "disable_external_api_access",
        "run_daily_generation_now",
    )

    list_display = (
        "id",
        "model_name",
        "word_range",
        "max_output_tokens",
        "temperature",
        "auto_daily_generation_enabled",
        "daily_generation_count",
        "daily_generation_time_display",
        "external_api_status",
        "is_active",
    )

    list_display_links = ("id", "model_name")

    list_editable = (
        "auto_daily_generation_enabled",
        "daily_generation_count",
        "is_active",
    )

    list_filter = (
        "is_active",
        "auto_daily_generation_enabled",
    )

    readonly_fields = (
        "external_api_access",
        "last_daily_generation_date",
    )

    fieldsets = (
        (
            "1. OpenAI Generation",
            {
                "fields": (
                    "model_name",
                    ("min_words", "max_words"),
                    "max_output_tokens",
                    "temperature",
                ),
            },
        ),
        (
            "2. Automatic Daily Content",
            {
                "fields": (
                    "auto_daily_generation_enabled",
                    "daily_generation_count",
                    "daily_generation_time",
                    "daily_generation_delay_seconds",
                ),
            },
        ),
        (
            "3. External API",
            {
                "fields": ("external_api_access",),
            },
        ),
        (
            "4. Status",
            {
                "fields": (
                    "is_active",
                    "last_daily_generation_date",
                ),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if obj.auto_generate_api_key and not obj.api_secret_key:
            obj.api_secret_key = secrets.token_urlsafe(48)

        super().save_model(request, obj, form, change)
        cache.delete("active_app_settings")

    @admin.action(description="Regenerate API Token")
    def regenerate_api_token(self, request, queryset):
        for obj in queryset:
            obj.api_secret_key = secrets.token_urlsafe(48)
            obj.auto_generate_api_key = True
            obj.save(update_fields=["api_secret_key", "auto_generate_api_key"])

        cache.delete("active_app_settings")
        self.message_user(request, "API token regenerated successfully.", messages.SUCCESS)

    @admin.action(description="Disable External API Access")
    def disable_external_api_access(self, request, queryset):
        for obj in queryset:
            obj.api_secret_key = ""
            obj.auto_generate_api_key = False
            obj.save(update_fields=["api_secret_key", "auto_generate_api_key"])

        cache.delete("active_app_settings")
        self.message_user(request, "External API access disabled successfully.", messages.SUCCESS)

    @admin.action(description="Run Daily Generation Now")
    def run_daily_generation_now(self, request, queryset):
        run_daily_generation_task.delay(force=True)
        self.message_user(request, "Daily generation task started.", messages.SUCCESS)

    def word_range(self, obj):
        return f"{obj.min_words} - {obj.max_words}"

    word_range.short_description = "Words"

    def daily_generation_time_display(self, obj):
        return f"{str(obj.daily_generation_hour).zfill(2)}:{str(obj.daily_generation_minute).zfill(2)}"

    daily_generation_time_display.short_description = "Daily Time"

    def external_api_status(self, obj):
        return "Enabled" if obj.api_secret_key else "Disabled"

    external_api_status.short_description = "External API"

    def external_api_access(self, obj):
        if not obj or not obj.api_secret_key:
            return format_html(
                """
                <div style="padding:12px;background:#fff8e1;border:1px solid #f0d98c;border-radius:6px;color:#6b5200;">
                    <strong>External API is disabled.</strong>
                </div>
                """
            )

        return format_html(
            """
            <code style="
                display:block;
                padding:10px 12px;
                background:#f6f8fa;
                border:1px solid #d0d7de;
                border-radius:6px;
                user-select:all;
                word-break:break-all;
            ">{}</code>
            """,
            obj.api_secret_key,
        )

    external_api_access.short_description = "External API Key"