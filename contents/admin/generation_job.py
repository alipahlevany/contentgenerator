from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html

from contents.models import GenerationJob, GenerationJobLog
from contents.tasks import run_generation_job_task


class GenerationJobLogInline(admin.TabularInline):
    model = GenerationJobLog
    extra = 0
    can_delete = False
    readonly_fields = ("level", "message", "created_at")
    fields = ("level", "message", "created_at")
    ordering = ("-created_at",)
    max_num = 20
    verbose_name_plural = "Latest job logs"

    def has_add_permission(self, request, obj=None):
        return False


class GenerationJobAdmin(admin.ModelAdmin):
    inlines = (GenerationJobLogInline,)

    list_display = (
        "id",
        "generation_type_badge",
        "status_badge",
        "count",
        "generated_badge",
        "skipped_badge",
        "remaining_badge",
        "progress_bar",
        "delay_seconds",
        "created_at",
        "job_actions",
    )

    list_display_links = ("id",)
    list_filter = ("generation_type", "status", "created_at")
    search_fields = ("=id", "error_message")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 50
    save_on_top = True

    readonly_fields = (
        "job_type_help",
        "status_badge",
        "pool_mode_display",
        "generated_count",
        "skipped_count",
        "remaining_display",
        "current_step",
        "progress_bar",
        "error_message",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "1. Job Settings",
            {
                "fields": (
                    "generation_type",
                    "job_type_help",
                    "count",
                    "delay_seconds",
                )
            },
        ),
        (
            "2. Selection Source",
            {"fields": ("pool_mode_display",)},
        ),
        (
            "3. Progress / Result",
            {
                "fields": (
                    "status_badge",
                    "generated_count",
                    "skipped_count",
                    "remaining_display",
                    "current_step",
                    "progress_bar",
                    "error_message",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return self.fieldsets[:2]
        return self.fieldsets

    def get_readonly_fields(self, request, obj=None):
        fields = list(self.readonly_fields)

        if obj and obj.status != "pending":
            fields.extend(
                (
                    "generation_type",
                    "count",
                    "delay_seconds",
                )
            )

        return tuple(dict.fromkeys(fields))

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status in ("pending", "running"):
            return False
        return super().has_delete_permission(request, obj)

    def job_type_help(self, obj=None):
        if obj and obj.generation_type == "email_reply":
            text = "This job generates natural email reply content."
            background = "#f3e8ff"
            color = "#6f42c1"
        else:
            text = "This job generates standard content from the weighted pool."
            background = "#e7f1ff"
            color = "#084298"

        return format_html(
            """
            <div style="
                padding:10px 13px;
                border-radius:9px;
                background:{};
                color:{};
                font-weight:700;
                line-height:1.6;
            ">{}</div>
            """,
            background,
            color,
            text,
        )

    job_type_help.short_description = "Job Type Description"

    def pool_mode_display(self, obj=None):
        return format_html(
            """
            <div style="
                padding:12px 14px;
                border:1px solid #dee2e6;
                border-radius:10px;
                background:#f8f9fa;
                line-height:1.65;
            ">
                <strong>Global weighted pool</strong><br>
                All active Languages, Topics, Audiences, Goals,
                Prompt Templates, and Content Rules are selected using
                their configured weights.
            </div>
            """
        )

    pool_mode_display.short_description = "Selection Mode"

    def generation_type_badge(self, obj):
        if obj.generation_type == "email_reply":
            background = "#f3e8ff"
            color = "#6f42c1"
        else:
            background = "#dbeafe"
            color = "#1d4ed8"

        return format_html(
            """
            <span style="
                display:inline-block;
                padding:5px 10px;
                border-radius:999px;
                background:{};
                color:{};
                font-weight:800;
                font-size:11px;
                white-space:nowrap;
            ">{}</span>
            """,
            background,
            color,
            obj.get_generation_type_display(),
        )

    generation_type_badge.short_description = "Type"
    generation_type_badge.admin_order_field = "generation_type"

    def status_badge(self, obj):
        colors = {
            "pending": "#6c757d",
            "running": "#0d6efd",
            "completed": "#198754",
            "failed": "#dc3545",
            "stopped": "#fd7e14",
        }

        return format_html(
            """
            <span style="
                display:inline-block;
                padding:6px 12px;
                border-radius:999px;
                background:{};
                color:white;
                font-weight:800;
                font-size:12px;
                min-width:90px;
                text-align:center;
                text-transform:capitalize;
            ">{}</span>
            """,
            colors.get(obj.status, "#6c757d"),
            obj.status,
        )

    status_badge.short_description = "Status"
    status_badge.admin_order_field = "status"

    def generated_badge(self, obj):
        return self.number_badge(obj.generated_count, "#e8f5e9", "#198754")

    generated_badge.short_description = "Generated"
    generated_badge.admin_order_field = "generated_count"

    def skipped_badge(self, obj):
        return self.number_badge(obj.skipped_count, "#fff3cd", "#946200")

    skipped_badge.short_description = "Skipped"
    skipped_badge.admin_order_field = "skipped_count"

    def remaining_badge(self, obj):
        return self.number_badge(self._remaining(obj), "#e7f1ff", "#0d6efd")

    remaining_badge.short_description = "Remaining"

    def remaining_display(self, obj):
        return self._remaining(obj)

    remaining_display.short_description = "Remaining"

    @staticmethod
    def _remaining(obj):
        return max(obj.count - obj.generated_count, 0)

    @staticmethod
    def number_badge(value, background, color):
        return format_html(
            """
            <span style="
                display:inline-block;
                padding:5px 10px;
                border-radius:8px;
                background:{};
                color:{};
                font-weight:800;
                min-width:34px;
                text-align:center;
            ">{}</span>
            """,
            background,
            color,
            value,
        )

    def progress_bar(self, obj):
        percent = 0 if not obj.count else int((obj.generated_count / obj.count) * 100)
        percent = max(0, min(percent, 100))

        bar_color = {
            "completed": "#198754",
            "running": "#0d6efd",
            "failed": "#dc3545",
            "stopped": "#fd7e14",
        }.get(obj.status, "#6c757d")

        return format_html(
            """
            <div style="min-width:220px;max-width:420px;">
                <div style="
                    width:100%;
                    height:12px;
                    background:#e9ecef;
                    border-radius:999px;
                    overflow:hidden;
                    margin-bottom:6px;
                ">
                    <div style="
                        width:{}%;
                        height:100%;
                        background:{};
                        border-radius:999px;
                    "></div>
                </div>
                <div style="
                    display:flex;
                    justify-content:space-between;
                    gap:10px;
                    font-size:12px;
                    color:#555;
                    font-weight:700;
                ">
                    <span>{}%</span>
                    <span>{}/{}</span>
                </div>
            </div>
            """,
            percent,
            bar_color,
            percent,
            obj.generated_count,
            obj.count,
        )

    progress_bar.short_description = "Progress"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:job_id>/start/",
                self.admin_site.admin_view(self.start_job),
                name="contents_generationjob_start",
            ),
            path(
                "<int:job_id>/stop/",
                self.admin_site.admin_view(self.stop_job),
                name="contents_generationjob_stop",
            ),
        ]
        return custom_urls + urls

    def job_actions(self, obj):
        start_url = reverse("admin:contents_generationjob_start", args=[obj.id])
        stop_url = reverse("admin:contents_generationjob_stop", args=[obj.id])

        if obj.status == "running":
            return format_html(
                """
                <a href="{}" style="
                    display:inline-block;
                    background:#dc3545;
                    color:white;
                    padding:7px 12px;
                    border-radius:7px;
                    text-decoration:none;
                    font-weight:800;
                    white-space:nowrap;
                ">■ Stop</a>
                """,
                stop_url,
            )

        if obj.generated_count >= obj.count or obj.status == "completed":
            return format_html(
                """
                <span style="
                    display:inline-block;
                    padding:7px 10px;
                    border-radius:7px;
                    background:#d1e7dd;
                    color:#0f5132;
                    font-weight:800;
                    white-space:nowrap;
                ">✓ Complete</span>
                """
            )

        label = "▶ Resume" if obj.status in ("stopped", "failed") or obj.generated_count else "▶ Start"

        return format_html(
            """
            <a href="{}" style="
                display:inline-block;
                background:#198754;
                color:white;
                padding:7px 12px;
                border-radius:7px;
                text-decoration:none;
                font-weight:800;
                white-space:nowrap;
            ">{}</a>
            """,
            start_url,
            label,
        )

    job_actions.short_description = "Action"

    def start_job(self, request, job_id):
        job = get_object_or_404(GenerationJob, id=job_id)

        if job.status == "running":
            self.message_user(
                request,
                f"Job #{job.id} is already running.",
                messages.WARNING,
            )
            return redirect("admin:contents_generationjob_changelist")

        if job.generated_count >= job.count:
            if job.status != "completed":
                job.status = "completed"
                job.should_stop = False
                job.save(update_fields=["status", "should_stop", "updated_at"])

            self.message_user(
                request,
                f"Job #{job.id} is already completed ({job.generated_count}/{job.count}).",
                messages.INFO,
            )
            return redirect("admin:contents_generationjob_changelist")

        job.status = "pending"
        job.should_stop = False
        job.error_message = ""
        job.save(
            update_fields=[
                "status",
                "should_stop",
                "error_message",
                "updated_at",
            ]
        )

        run_generation_job_task.delay(job.id)

        action_text = (
            "resumed"
            if job.generated_count > 0 or job.skipped_count > 0 or job.current_step > 0
            else "started"
        )

        self.message_user(
            request,
            f"Job #{job.id} {action_text} successfully.",
            messages.SUCCESS,
        )
        return redirect("admin:contents_generationjob_changelist")

    def stop_job(self, request, job_id):
        job = get_object_or_404(GenerationJob, id=job_id)

        if job.status not in ("running", "pending"):
            self.message_user(
                request,
                f"Job #{job.id} is not running.",
                messages.INFO,
            )
            return redirect("admin:contents_generationjob_changelist")

        job.should_stop = True
        job.status = "stopped"
        job.error_message = "Job stopped by admin."
        job.save(
            update_fields=[
                "should_stop",
                "status",
                "error_message",
                "updated_at",
            ]
        )

        self.message_user(
            request,
            f"Job #{job.id} stopped.",
            messages.SUCCESS,
        )
        return redirect("admin:contents_generationjob_changelist")
