import secrets
from datetime import timedelta, timezone as datetime_timezone

from django import forms
from django.contrib import admin, messages
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import redirect
from django.urls import NoReverseMatch, path, reverse
from django.utils import timezone
from django.utils.html import format_html

from contents.admin.forms import AppSettingsForm
from contents.models import AppSettings, GenerationJob
from contents.tasks import run_daily_generation_task


class AppSettingsAdminForm(AppSettingsForm):
    """
    Extended admin-only form.

    The immediate-generation checkbox is not stored in the database.
    It acts as a one-time command when the settings form is saved.
    """

    run_daily_generation_immediately = forms.BooleanField(
        required=False,
        label="Run Daily Generation Immediately",
        help_text=(
            "Check this option and save the settings to start the daily "
            "generation task immediately. This option is one-time only "
            "and will automatically be cleared after saving."
        ),
    )


class AppSettingsAdmin(admin.ModelAdmin):
    form = AppSettingsAdminForm

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

    list_display_links = (
        "id",
        "model_name",
    )

    list_filter = (
        "is_active",
        "auto_daily_generation_enabled",
    )

    readonly_fields = (
        "daily_generation_status_panel",
        "api_control_panel",
        "status_panel",
        "current_utc_time",
        "next_daily_generation_utc",
        "time_until_next_daily_generation",
        "last_daily_generation_date",
    )

    fieldsets = (
        (
            "⚙️ AI Configuration",
            {
                "fields": (
                    "model_name",
                    (
                        "min_words",
                        "max_words",
                    ),
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
                    "daily_generation_status_panel",
                    "auto_daily_generation_enabled",
                    "daily_generation_count",
                    "daily_generation_time",
                    "daily_generation_delay_seconds",
                    "run_daily_generation_immediately",
                    "current_utc_time",
                    "next_daily_generation_utc",
                    "time_until_next_daily_generation",
                    "last_daily_generation_date",
                ),
                "description": (
                    "All automatic generation times are based on UTC. "
                    "Celery Beat checks the configured execution time "
                    "every minute."
                ),
            },
        ),
        (
            "🔑 External API",
            {
                "fields": (
                    "api_control_panel",
                ),
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
                self.admin_site.admin_view(
                    self.regenerate_single_api_key
                ),
                name="contents_appsettings_regenerate_api_key",
            ),
            path(
                "<int:object_id>/disable-api/",
                self.admin_site.admin_view(
                    self.disable_single_api
                ),
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

    def regenerate_single_api_key(
        self,
        request,
        object_id,
    ):
        obj = AppSettings.objects.get(
            id=object_id
        )

        obj.api_secret_key = secrets.token_urlsafe(48)
        obj.auto_generate_api_key = True

        obj.save(
            update_fields=[
                "api_secret_key",
                "auto_generate_api_key",
            ]
        )

        cache.delete("active_app_settings")

        self.message_user(
            request,
            "API key regenerated successfully.",
            messages.SUCCESS,
        )

        return redirect(
            "admin:contents_appsettings_change",
            object_id,
        )

    def disable_single_api(
        self,
        request,
        object_id,
    ):
        obj = AppSettings.objects.get(
            id=object_id
        )

        obj.api_secret_key = ""
        obj.auto_generate_api_key = False

        obj.save(
            update_fields=[
                "api_secret_key",
                "auto_generate_api_key",
            ]
        )

        cache.delete("active_app_settings")

        self.message_user(
            request,
            "External API disabled successfully.",
            messages.SUCCESS,
        )

        return redirect(
            "admin:contents_appsettings_change",
            object_id,
        )

    def save_model(
        self,
        request,
        obj,
        form,
        change,
    ):
        should_run_immediately = bool(
            form.cleaned_data.get(
                "run_daily_generation_immediately",
                False,
            )
        )

        if (
            obj.auto_generate_api_key
            and not obj.api_secret_key
        ):
            obj.api_secret_key = secrets.token_urlsafe(48)

        super().save_model(
            request,
            obj,
            form,
            change,
        )

        cache.delete("active_app_settings")

        if should_run_immediately:
            transaction.on_commit(
                lambda: run_daily_generation_task.delay(
                    force=True
                )
            )

            self.message_user(
                request,
                (
                    "Settings saved successfully. "
                    "The daily generation task was queued "
                    "for immediate execution."
                ),
                messages.SUCCESS,
            )

    @admin.action(
        description="Regenerate API Token"
    )
    def regenerate_api_token(
        self,
        request,
        queryset,
    ):
        updated_count = 0

        for obj in queryset:
            obj.api_secret_key = secrets.token_urlsafe(48)
            obj.auto_generate_api_key = True

            obj.save(
                update_fields=[
                    "api_secret_key",
                    "auto_generate_api_key",
                ]
            )

            updated_count += 1

        cache.delete("active_app_settings")

        self.message_user(
            request,
            (
                f"API token regenerated successfully for "
                f"{updated_count} settings record(s)."
            ),
            messages.SUCCESS,
        )

    @admin.action(
        description="Disable External API Access"
    )
    def disable_external_api_access(
        self,
        request,
        queryset,
    ):
        updated_count = 0

        for obj in queryset:
            obj.api_secret_key = ""
            obj.auto_generate_api_key = False

            obj.save(
                update_fields=[
                    "api_secret_key",
                    "auto_generate_api_key",
                ]
            )

            updated_count += 1

        cache.delete("active_app_settings")

        self.message_user(
            request,
            (
                f"External API access disabled for "
                f"{updated_count} settings record(s)."
            ),
            messages.SUCCESS,
        )

    @admin.action(
        description="Run Daily Generation Now"
    )
    def run_daily_generation_now(
        self,
        request,
        queryset,
    ):
        selected_settings = (
            queryset
            .filter(is_active=True)
            .order_by("-id")
            .first()
        )

        if not selected_settings:
            self.message_user(
                request,
                (
                    "Select an active settings record before "
                    "running daily generation."
                ),
                messages.ERROR,
            )
            return

        result = run_daily_generation_task.delay(
            force=True
        )

        self.message_user(
            request,
            (
                "Daily generation task was queued successfully. "
                f"Task ID: {result.id}"
            ),
            messages.SUCCESS,
        )

    def get_current_utc_datetime(self):
        return timezone.now().astimezone(
            datetime_timezone.utc
        )

    def get_next_daily_generation_datetime(
        self,
        obj,
    ):
        if not obj:
            return None

        if not obj.auto_daily_generation_enabled:
            return None

        now = self.get_current_utc_datetime()
        today = now.date()

        target = now.replace(
            hour=obj.daily_generation_hour,
            minute=obj.daily_generation_minute,
            second=0,
            microsecond=0,
        )

        if obj.last_daily_generation_date == today:
            return target + timedelta(days=1)

        if now < target:
            return target

        return now

    def get_latest_generation_job(self):
        return (
            GenerationJob.objects
            .order_by("-id")
            .first()
        )

    def get_active_generation_job(self):
        return (
            GenerationJob.objects
            .filter(
                status__in=[
                    "pending",
                    "running",
                ]
            )
            .order_by("-id")
            .first()
        )

    def get_time_remaining_text(
        self,
        obj,
    ):
        if not obj:
            return "-"

        if not obj.auto_daily_generation_enabled:
            return "Disabled"

        now = self.get_current_utc_datetime()

        next_run = (
            self.get_next_daily_generation_datetime(
                obj
            )
        )

        if not next_run:
            return "-"

        if next_run <= now:
            return "Due now"

        total_seconds = max(
            0,
            int(
                (
                    next_run - now
                ).total_seconds()
            ),
        )

        days, remainder = divmod(
            total_seconds,
            86400,
        )

        hours, remainder = divmod(
            remainder,
            3600,
        )

        minutes, seconds = divmod(
            remainder,
            60,
        )

        parts = []

        if days:
            parts.append(
                f"{days} day"
                f"{'s' if days != 1 else ''}"
            )

        if hours:
            parts.append(
                f"{hours} hour"
                f"{'s' if hours != 1 else ''}"
            )

        if minutes:
            parts.append(
                f"{minutes} minute"
                f"{'s' if minutes != 1 else ''}"
            )

        if not parts:
            parts.append(
                f"{seconds} second"
                f"{'s' if seconds != 1 else ''}"
            )

        return " ".join(parts)

    def current_utc_time(
        self,
        obj,
    ):
        now = self.get_current_utc_datetime()

        return format_html(
            """
            <div style="
                display:inline-flex;
                align-items:center;
                gap:8px;
                padding:10px 14px;
                border:1px solid #bae6fd;
                background:linear-gradient(
                    135deg,
                    #f0f9ff,
                    #e0f2fe
                );
                color:#075985;
                border-radius:12px;
                font-weight:800;
            ">
                <span>🕓</span>
                <span>{}</span>
            </div>
            """,
            now.strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            ),
        )

    current_utc_time.short_description = (
        "Current UTC Time"
    )

    def next_daily_generation_utc(
        self,
        obj,
    ):
        if not obj:
            return "-"

        if not obj.auto_daily_generation_enabled:
            return self.badge(
                "Automatic generation is disabled",
                "#fee2e2",
                "#991b1b",
            )

        now = self.get_current_utc_datetime()

        next_run = (
            self.get_next_daily_generation_datetime(
                obj
            )
        )

        if not next_run:
            return "-"

        if next_run <= now:
            return self.badge(
                "Due now — scheduler checks every minute",
                "#fef3c7",
                "#92400e",
            )

        return format_html(
            """
            <div style="
                display:inline-flex;
                align-items:center;
                gap:8px;
                padding:10px 14px;
                border:1px solid #c7d2fe;
                background:linear-gradient(
                    135deg,
                    #eef2ff,
                    #e0e7ff
                );
                color:#3730a3;
                border-radius:12px;
                font-weight:800;
            ">
                <span>📅</span>
                <span>{}</span>
            </div>
            """,
            next_run.strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            ),
        )

    next_daily_generation_utc.short_description = (
        "Next Daily Generation (UTC)"
    )

    def time_until_next_daily_generation(
        self,
        obj,
    ):
        if not obj:
            return "-"

        if not obj.auto_daily_generation_enabled:
            return self.badge(
                "Disabled",
                "#fee2e2",
                "#991b1b",
            )

        now = self.get_current_utc_datetime()

        next_run = (
            self.get_next_daily_generation_datetime(
                obj
            )
        )

        if not next_run or next_run <= now:
            return self.badge(
                "Due now",
                "#fef3c7",
                "#92400e",
            )

        remaining_text = (
            self.get_time_remaining_text(
                obj
            )
        )

        return self.badge(
            remaining_text,
            "#dcfce7",
            "#166534",
        )

    time_until_next_daily_generation.short_description = (
        "Time Until Next Run"
    )

    def daily_generation_status_panel(
        self,
        obj,
    ):
        if not obj or not obj.pk:
            return "Save this settings record first."

        now = self.get_current_utc_datetime()

        next_run = (
            self.get_next_daily_generation_datetime(
                obj
            )
        )

        active_job = self.get_active_generation_job()
        latest_job = self.get_latest_generation_job()

        current_time_text = now.strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )

        if next_run:
            if next_run <= now:
                next_run_text = (
                    "Due now — scheduler checks every minute"
                )
            else:
                next_run_text = next_run.strftime(
                    "%Y-%m-%d %H:%M:%S UTC"
                )
        else:
            next_run_text = "Disabled"

        remaining_text = (
            self.get_time_remaining_text(
                obj
            )
        )

        if obj.last_daily_generation_date:
            last_run_text = str(
                obj.last_daily_generation_date
            )
        else:
            last_run_text = "Never"

        daily_target_text = (
            f"{obj.daily_generation_count} contents"
        )

        if not obj.auto_daily_generation_enabled:
            status_title = "Disabled"
            status_description = (
                "Automatic daily generation is disabled."
            )
            status_bg = "#fee2e2"
            status_border = "#fecaca"
            status_color = "#991b1b"
            status_icon = "🔴"

        elif active_job:
            generated_count = getattr(
                active_job,
                "generated_count",
                0,
            )

            total_count = getattr(
                active_job,
                "count",
                0,
            )

            if active_job.status == "pending":
                status_title = "Pending"
                status_description = (
                    f"Generation Job #{active_job.id} "
                    "is waiting to start."
                )
                status_icon = "🟠"
            else:
                status_title = (
                    f"Running — "
                    f"{generated_count}/{total_count}"
                )
                status_description = (
                    f"Generation Job #{active_job.id} "
                    "is currently running."
                )
                status_icon = "🟡"

            status_bg = "#fefce8"
            status_border = "#fde68a"
            status_color = "#854d0e"

        elif latest_job and latest_job.status == "failed":
            status_title = "Last Job Failed"
            status_description = (
                f"Generation Job #{latest_job.id} failed."
            )
            status_bg = "#fff1f2"
            status_border = "#fecdd3"
            status_color = "#9f1239"
            status_icon = "🔴"

        elif latest_job and latest_job.status == "stopped":
            status_title = "Last Job Stopped"
            status_description = (
                f"Generation Job #{latest_job.id} "
                "was stopped."
            )
            status_bg = "#fff7ed"
            status_border = "#fed7aa"
            status_color = "#9a3412"
            status_icon = "🟠"

        else:
            status_title = "Idle"
            status_description = (
                "No generation job is currently running."
            )
            status_bg = "#ecfdf5"
            status_border = "#bbf7d0"
            status_color = "#166534"
            status_icon = "🟢"

        return format_html(
            """
            <div style="
                max-width:980px;
                border:1px solid {};
                background:linear-gradient(
                    135deg,
                    {},
                    #ffffff
                );
                border-radius:18px;
                padding:22px;
                box-shadow:
                    0 8px 24px rgba(15,23,42,0.06);
            ">
                <div style="
                    display:flex;
                    justify-content:space-between;
                    align-items:flex-start;
                    gap:18px;
                    flex-wrap:wrap;
                    margin-bottom:20px;
                ">
                    <div>
                        <h2 style="
                            margin:0 0 6px;
                            color:#0f172a;
                            font-size:20px;
                        ">
                            Daily Generation Status
                        </h2>

                        <p style="
                            margin:0;
                            color:#64748b;
                        ">
                            Monitor the automatic generation
                            schedule and current progress.
                        </p>
                    </div>

                    <div style="
                        display:inline-flex;
                        align-items:center;
                        gap:8px;
                        background:{};
                        color:{};
                        border:1px solid {};
                        padding:8px 14px;
                        border-radius:999px;
                        font-weight:800;
                    ">
                        <span>{}</span>
                        <span>{}</span>
                    </div>
                </div>

                <div style="
                    display:grid;
                    grid-template-columns:
                        repeat(
                            auto-fit,
                            minmax(210px,1fr)
                        );
                    gap:12px;
                ">
                    <div style="
                        padding:14px;
                        border:1px solid #e2e8f0;
                        border-radius:14px;
                        background:#ffffff;
                    ">
                        <div style="
                            color:#64748b;
                            font-size:12px;
                            font-weight:800;
                            margin-bottom:6px;
                            text-transform:uppercase;
                        ">
                            Current UTC Time
                        </div>

                        <div style="
                            color:#0f172a;
                            font-weight:800;
                        ">
                            {}
                        </div>
                    </div>

                    <div style="
                        padding:14px;
                        border:1px solid #e2e8f0;
                        border-radius:14px;
                        background:#ffffff;
                    ">
                        <div style="
                            color:#64748b;
                            font-size:12px;
                            font-weight:800;
                            margin-bottom:6px;
                            text-transform:uppercase;
                        ">
                            Next Run
                        </div>

                        <div style="
                            color:#0f172a;
                            font-weight:800;
                        ">
                            {}
                        </div>
                    </div>

                    <div style="
                        padding:14px;
                        border:1px solid #e2e8f0;
                        border-radius:14px;
                        background:#ffffff;
                    ">
                        <div style="
                            color:#64748b;
                            font-size:12px;
                            font-weight:800;
                            margin-bottom:6px;
                            text-transform:uppercase;
                        ">
                            Time Remaining
                        </div>

                        <div style="
                            color:#0f172a;
                            font-weight:800;
                        ">
                            {}
                        </div>
                    </div>

                    <div style="
                        padding:14px;
                        border:1px solid #e2e8f0;
                        border-radius:14px;
                        background:#ffffff;
                    ">
                        <div style="
                            color:#64748b;
                            font-size:12px;
                            font-weight:800;
                            margin-bottom:6px;
                            text-transform:uppercase;
                        ">
                            Last Daily Run
                        </div>

                        <div style="
                            color:#0f172a;
                            font-weight:800;
                        ">
                            {}
                        </div>
                    </div>

                    <div style="
                        padding:14px;
                        border:1px solid #e2e8f0;
                        border-radius:14px;
                        background:#ffffff;
                    ">
                        <div style="
                            color:#64748b;
                            font-size:12px;
                            font-weight:800;
                            margin-bottom:6px;
                            text-transform:uppercase;
                        ">
                            Daily Target
                        </div>

                        <div style="
                            color:#0f172a;
                            font-weight:800;
                        ">
                            {}
                        </div>
                    </div>

                    <div style="
                        padding:14px;
                        border:1px solid #e2e8f0;
                        border-radius:14px;
                        background:#ffffff;
                    ">
                        <div style="
                            color:#64748b;
                            font-size:12px;
                            font-weight:800;
                            margin-bottom:6px;
                            text-transform:uppercase;
                        ">
                            Status Details
                        </div>

                        <div style="
                            color:#0f172a;
                            font-weight:700;
                        ">
                            {}
                        </div>
                    </div>
                </div>
            </div>
            """,
            status_border,
            status_bg,
            status_bg,
            status_color,
            status_border,
            status_icon,
            status_title,
            current_time_text,
            next_run_text,
            remaining_text,
            last_run_text,
            daily_target_text,
            status_description,
        )

    daily_generation_status_panel.short_description = (
        "Daily Generation Overview"
    )

    def badge(
        self,
        text,
        bg,
        color,
    ):
        return format_html(
            (
                '<span style="'
                "background:{};"
                "color:{};"
                "padding:5px 10px;"
                "border-radius:999px;"
                "font-weight:800;"
                "white-space:nowrap;"
                '">{}</span>'
            ),
            bg,
            color,
            text,
        )

    def tokens_badge(
        self,
        obj,
    ):
        return format_html(
            "{} {}",
            self.badge(
                f"{obj.max_output_tokens} tokens",
                "#e0f2fe",
                "#075985",
            ),
            self.badge(
                f"temp {obj.temperature}",
                "#fef3c7",
                "#92400e",
            ),
        )

    tokens_badge.short_description = "AI Settings"

    def daily_badge(
        self,
        obj,
    ):
        if obj.auto_daily_generation_enabled:
            return self.badge(
                "Enabled",
                "#dcfce7",
                "#166534",
            )

        return self.badge(
            "Disabled",
            "#fee2e2",
            "#991b1b",
        )

    daily_badge.short_description = "Daily"

    def api_badge(
        self,
        obj,
    ):
        if obj.api_secret_key:
            return self.badge(
                "Enabled",
                "#dcfce7",
                "#166534",
            )

        return self.badge(
            "Disabled",
            "#fee2e2",
            "#991b1b",
        )

    api_badge.short_description = "API"

    def schedule_badge(
        self,
        obj,
    ):
        hour = str(
            obj.daily_generation_hour
        ).zfill(2)

        minute = str(
            obj.daily_generation_minute
        ).zfill(2)

        return self.badge(
            (
                f"{obj.daily_generation_count}/day "
                f"• {hour}:{minute} UTC"
            ),
            "#eef2ff",
            "#3730a3",
        )

    schedule_badge.short_description = "Schedule"

    def status_badge(
        self,
        obj,
    ):
        if obj.is_active:
            return self.badge(
                "Active",
                "#dcfce7",
                "#166534",
            )

        return self.badge(
            "Inactive",
            "#fee2e2",
            "#991b1b",
        )

    status_badge.short_description = "Status"

    def api_control_panel(
        self,
        obj,
    ):
        if not obj or not obj.pk:
            return "Save this settings record first."

        regenerate_url = reverse(
            "admin:contents_appsettings_regenerate_api_key",
            args=[
                obj.id,
            ],
        )

        disable_url = reverse(
            "admin:contents_appsettings_disable_api",
            args=[
                obj.id,
            ],
        )

        swagger_url = self.get_swagger_url()

        if not obj.api_secret_key:
            return format_html(
                """
                <div style="
                    max-width:860px;
                    padding:18px;
                    border:1px solid #fed7aa;
                    background:linear-gradient(
                        135deg,
                        #fff7ed,
                        #fffbeb
                    );
                    border-radius:16px;
                    color:#9a3412;
                ">
                    <h3 style="margin:0 0 8px;">
                        External API is disabled
                    </h3>

                    <p style="margin:0 0 16px;">
                        Generate an API key to allow external
                        systems to access the API.
                    </p>

                    <a
                        href="{}"
                        style="
                            background:#2563eb;
                            color:white;
                            padding:10px 16px;
                            border-radius:10px;
                            text-decoration:none;
                            font-weight:800;
                        "
                    >
                        Generate API Key
                    </a>
                </div>
                """,
                regenerate_url,
            )

        return format_html(
            """
            <div style="
                max-width:920px;
                padding:20px;
                border:1px solid #dbeafe;
                background:linear-gradient(
                    135deg,
                    #f8fafc,
                    #eff6ff
                );
                border-radius:16px;
            ">
                <div style="
                    display:flex;
                    justify-content:space-between;
                    gap:16px;
                    align-items:center;
                    margin-bottom:14px;
                ">
                    <div>
                        <h3 style="
                            margin:0 0 4px;
                            color:#111827;
                        ">
                            External API Access
                        </h3>

                        <p style="
                            margin:0;
                            color:#64748b;
                        ">
                            Use this key for authenticated
                            API requests.
                        </p>
                    </div>

                    <span style="
                        background:#dcfce7;
                        color:#166534;
                        padding:6px 12px;
                        border-radius:999px;
                        font-weight:800;
                    ">
                        Enabled
                    </span>
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

                <div style="
                    display:flex;
                    gap:10px;
                    flex-wrap:wrap;
                ">
                    <a
                        href="{}"
                        style="
                            background:#2563eb;
                            color:white;
                            padding:10px 16px;
                            border-radius:10px;
                            text-decoration:none;
                            font-weight:800;
                        "
                    >
                        Regenerate Key
                    </a>

                    <a
                        href="{}"
                        style="
                            background:#dc2626;
                            color:white;
                            padding:10px 16px;
                            border-radius:10px;
                            text-decoration:none;
                            font-weight:800;
                        "
                    >
                        Disable API
                    </a>

                    <a
                        href="{}"
                        target="_blank"
                        rel="noopener noreferrer"
                        style="
                            background:#0f172a;
                            color:white;
                            padding:10px 16px;
                            border-radius:10px;
                            text-decoration:none;
                            font-weight:800;
                        "
                    >
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

    api_control_panel.short_description = (
        "API Control Panel"
    )

    def status_panel(
        self,
        obj,
    ):
        if obj and obj.is_active:
            return format_html(
                """
                <div style="
                    max-width:860px;
                    padding:18px;
                    border:1px solid #bbf7d0;
                    background:linear-gradient(
                        135deg,
                        #ecfdf5,
                        #f0fdf4
                    );
                    border-radius:16px;
                ">
                    <h3 style="
                        margin:0 0 6px;
                        color:#166534;
                    ">
                        System Settings Active
                    </h3>

                    <p style="
                        margin:0;
                        color:#15803d;
                    ">
                        This record is currently used by
                        generation, API, daily tasks, and
                        the intelligence engine.
                    </p>
                </div>
                """
            )

        return format_html(
            """
            <div style="
                max-width:860px;
                padding:18px;
                border:1px solid #fecaca;
                background:linear-gradient(
                    135deg,
                    #fff1f2,
                    #fff7f7
                );
                border-radius:16px;
            ">
                <h3 style="
                    margin:0 0 6px;
                    color:#991b1b;
                ">
                    System Settings Inactive
                </h3>

                <p style="
                    margin:0;
                    color:#b91c1c;
                ">
                    This settings record is not active.
                </p>
            </div>
            """
        )

    status_panel.short_description = "System Status"