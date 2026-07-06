import secrets

from django.contrib import admin, messages
from django.core.cache import cache
from django.shortcuts import redirect
from django.urls import NoReverseMatch, path, reverse
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
        "tokens_badge",
        "daily_badge",
        "api_badge",
        "schedule_badge",
        "status_badge",
    )

    list_display_links = ("id", "model_name")
    list_filter = ("is_active", "auto_daily_generation_enabled")

    readonly_fields = (
        "api_control_panel",
        "status_panel",
        "last_daily_generation_date",
    )

    fieldsets = (
        (
            "⚙️ AI Configuration",
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
            "🧠 Content Intelligence",
            {
                "fields": (
                    "auto_refill_enabled",
                    "auto_refill_skip_threshold",
                    "auto_refill_item_count",
                ),
            },
        ),
        (
            "🤖 Automatic Daily Generation",
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
        (
            "🔑 External API",
            {
                "fields": ("api_control_panel",),
            },
        ),
        (
            "📌 Status",
            {
                "fields": (
                    "status_panel",
                    "is_active",
                ),
            },
        ),
    )

    def get_urls(self):
        urls = super().get_urls()

        custom_urls = [
            path(
                "<int:object_id>/regenerate-api-key/",
                self.admin_site.admin_view(self.regenerate_single_api_key),
                name="contents_appsettings_regenerate_api_key",
            ),
            path(
                "<int:object_id>/disable-api/",
                self.admin_site.admin_view(self.disable_single_api),
                name="contents_appsettings_disable_api",
            ),
        ]

        return custom_urls + urls

    def get_swagger_url(self):
        possible_names = [
            "schema-swagger-ui",
            "swagger-ui",
            "swagger",
            "drf-spectacular:swagger-ui",
        ]

        for name in possible_names:
            try:
                return reverse(name)
            except NoReverseMatch:
                continue

        return "/api/schema/swagger-ui/"

    def regenerate_single_api_key(self, request, object_id):
        obj = AppSettings.objects.get(id=object_id)
        obj.api_secret_key = secrets.token_urlsafe(48)
        obj.auto_generate_api_key = True
        obj.save(update_fields=["api_secret_key", "auto_generate_api_key"])

        cache.delete("active_app_settings")
        self.message_user(request, "API key regenerated successfully.", messages.SUCCESS)

        return redirect("admin:contents_appsettings_change", object_id)

    def disable_single_api(self, request, object_id):
        obj = AppSettings.objects.get(id=object_id)
        obj.api_secret_key = ""
        obj.auto_generate_api_key = False
        obj.save(update_fields=["api_secret_key", "auto_generate_api_key"])

        cache.delete("active_app_settings")
        self.message_user(request, "External API disabled successfully.", messages.SUCCESS)

        return redirect("admin:contents_appsettings_change", object_id)

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

    def badge(self, text, bg, color):
        return format_html(
            '<span style="background:{};color:{};padding:5px 10px;border-radius:999px;font-weight:800;white-space:nowrap;">{}</span>',
            bg,
            color,
            text,
        )

    def tokens_badge(self, obj):
        return format_html(
            "{} {}",
            self.badge(f"{obj.max_output_tokens} tokens", "#e0f2fe", "#075985"),
            self.badge(f"temp {obj.temperature}", "#fef3c7", "#92400e"),
        )

    tokens_badge.short_description = "AI Settings"

    def daily_badge(self, obj):
        if obj.auto_daily_generation_enabled:
            return self.badge("Enabled", "#dcfce7", "#166534")

        return self.badge("Disabled", "#fee2e2", "#991b1b")

    daily_badge.short_description = "Daily"

    def api_badge(self, obj):
        if obj.api_secret_key:
            return self.badge("Enabled", "#dcfce7", "#166534")

        return self.badge("Disabled", "#fee2e2", "#991b1b")

    api_badge.short_description = "API"

    def schedule_badge(self, obj):
        hour = str(obj.daily_generation_hour).zfill(2)
        minute = str(obj.daily_generation_minute).zfill(2)

        return self.badge(
            f"{obj.daily_generation_count}/day • {hour}:{minute}",
            "#eef2ff",
            "#3730a3",
        )

    schedule_badge.short_description = "Schedule"

    def status_badge(self, obj):
        if obj.is_active:
            return self.badge("Active", "#dcfce7", "#166534")

        return self.badge("Inactive", "#fee2e2", "#991b1b")

    status_badge.short_description = "Status"

    def api_control_panel(self, obj):
        if not obj or not obj.pk:
            return "Save this settings record first."

        regenerate_url = reverse(
            "admin:contents_appsettings_regenerate_api_key",
            args=[obj.id],
        )

        disable_url = reverse(
            "admin:contents_appsettings_disable_api",
            args=[obj.id],
        )

        swagger_url = self.get_swagger_url()

        if not obj.api_secret_key:
            return format_html(
                """
                <div style="max-width:860px;padding:18px;border:1px solid #fed7aa;background:linear-gradient(135deg,#fff7ed,#fffbeb);border-radius:16px;color:#9a3412;">
                    <h3 style="margin:0 0 8px;">External API is disabled</h3>
                    <p style="margin:0 0 16px;">Generate an API key to allow external systems to access the API.</p>
                    <a href="{}" style="background:#2563eb;color:white;padding:10px 16px;border-radius:10px;text-decoration:none;font-weight:800;">
                        Generate API Key
                    </a>
                </div>
                """,
                regenerate_url,
            )

        return format_html(
            """
            <div style="max-width:920px;padding:20px;border:1px solid #dbeafe;background:linear-gradient(135deg,#f8fafc,#eff6ff);border-radius:16px;">
                <div style="display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:14px;">
                    <div>
                        <h3 style="margin:0 0 4px;color:#111827;">External API Access</h3>
                        <p style="margin:0;color:#64748b;">Use this key for authenticated API requests.</p>
                    </div>
                    <span style="background:#dcfce7;color:#166534;padding:6px 12px;border-radius:999px;font-weight:800;">Enabled</span>
                </div>

                <code style="
                    display:block;
                    padding:14px;
                    background:#ffffff;
                    border:1px solid #cbd5e1;
                    border-radius:12px;
                    user-select:all;
                    word-break:break-all;
                    font-size:13px;
                    color:#334155;
                    margin-bottom:14px;
                ">{}</code>

                <div style="display:flex;gap:10px;flex-wrap:wrap;">
                    <a href="{}" style="background:#2563eb;color:white;padding:10px 16px;border-radius:10px;text-decoration:none;font-weight:800;">
                        Regenerate Key
                    </a>
                    <a href="{}" style="background:#dc2626;color:white;padding:10px 16px;border-radius:10px;text-decoration:none;font-weight:800;">
                        Disable API
                    </a>
                    <a href="{}" target="_blank" style="background:#0f172a;color:white;padding:10px 16px;border-radius:10px;text-decoration:none;font-weight:800;">
                        Open Swagger
                    </a>
                </div>
            </div>
            """,
            obj.api_secret_key,
            regenerate_url,
            disable_url,
            swagger_url,
        )

    api_control_panel.short_description = "API Control Panel"

    def status_panel(self, obj):
        if obj and obj.is_active:
            return format_html(
                """
                <div style="max-width:860px;padding:18px;border:1px solid #bbf7d0;background:linear-gradient(135deg,#ecfdf5,#f0fdf4);border-radius:16px;">
                    <h3 style="margin:0 0 6px;color:#166534;">System Settings Active</h3>
                    <p style="margin:0;color:#15803d;">This record is currently used by generation, API, daily tasks, and intelligence engine.</p>
                </div>
                """
            )

        return format_html(
            """
            <div style="max-width:860px;padding:18px;border:1px solid #fecaca;background:linear-gradient(135deg,#fff1f2,#fff7f7);border-radius:16px;">
                <h3 style="margin:0 0 6px;color:#991b1b;">System Settings Inactive</h3>
                <p style="margin:0;color:#b91c1c;">This settings record is not active.</p>
            </div>
            """
        )

    status_panel.short_description = "System Status"