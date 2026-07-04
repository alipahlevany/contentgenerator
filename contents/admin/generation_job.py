from django.contrib import admin, messages
from django.shortcuts import redirect
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

    def has_add_permission(self, request, obj=None):
        return False


class GenerationJobAdmin(admin.ModelAdmin):
    inlines = (GenerationJobLogInline,)

    list_display = (
        "id",
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
    list_filter = ("status", "created_at")
    search_fields = ("=id", "error_message")
    ordering = ("-created_at",)

    readonly_fields = (
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
        ("1. Job Settings", {"fields": ("count", "delay_seconds")}),
        ("2. Selection Source", {"fields": ("pool_mode_display",)}),
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

    def pool_mode_display(self, obj=None):
        return (
            "Global weighted pool: all active Languages, Topics, Audiences, "
            "Goals, Prompt Templates, and Content Rules."
        )

    pool_mode_display.short_description = "Selection Mode"

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

    def generated_badge(self, obj):
        return self.number_badge(obj.generated_count, "#e8f5e9", "#198754")

    generated_badge.short_description = "Generated"

    def skipped_badge(self, obj):
        return self.number_badge(obj.skipped_count, "#fff3cd", "#946200")

    skipped_badge.short_description = "Skipped"

    def remaining_badge(self, obj):
        remaining = max(obj.count - obj.generated_count, 0)
        return self.number_badge(remaining, "#e7f1ff", "#0d6efd")

    remaining_badge.short_description = "Remaining"

    def remaining_display(self, obj):
        return max(obj.count - obj.generated_count, 0)

    remaining_display.short_description = "Remaining"

    def number_badge(self, value, background, color):
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
        percent = min(percent, 100)

        return format_html(
            """
            <div style="min-width:220px;">
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
                        background:#198754;
                        border-radius:999px;
                    "></div>
                </div>
                <div style="font-size:12px;color:#555;font-weight:700;">
                    {}% — {}/{}
                </div>
            </div>
            """,
            percent,
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

        return format_html(
            """
            <div style="display:flex;gap:6px;white-space:nowrap;">
                <a href="{}" style="
                    background:#198754;
                    color:white;
                    padding:7px 12px;
                    border-radius:7px;
                    text-decoration:none;
                    font-weight:800;
                ">▶ Start</a>

                <a href="{}" style="
                    background:#dc3545;
                    color:white;
                    padding:7px 12px;
                    border-radius:7px;
                    text-decoration:none;
                    font-weight:800;
                ">■ Stop</a>
            </div>
            """,
            start_url,
            stop_url,
        )

    job_actions.short_description = "Actions"

    def start_job(self, request, job_id):
        job = GenerationJob.objects.get(id=job_id)

        if job.status == "running":
            self.message_user(
                request,
                f"Job #{job.id} is already running.",
                messages.WARNING,
            )
            return redirect("admin:contents_generationjob_changelist")

        job.status = "pending"
        job.should_stop = False
        job.error_message = ""
        job.generated_count = 0
        job.skipped_count = 0
        job.current_step = 0
        job.save(
            update_fields=[
                "status",
                "should_stop",
                "error_message",
                "generated_count",
                "skipped_count",
                "current_step",
            ]
        )

        run_generation_job_task.delay(job.id)

        self.message_user(
            request,
            f"Job #{job.id} started successfully.",
            messages.SUCCESS,
        )

        return redirect("admin:contents_generationjob_changelist")

    def stop_job(self, request, job_id):
        job = GenerationJob.objects.get(id=job_id)

        if job.status != "running":
            self.message_user(
                request,
                f"Job #{job.id} is not running.",
                messages.INFO,
            )
            return redirect("admin:contents_generationjob_changelist")

        job.should_stop = True
        job.status = "stopped"
        job.error_message = "Job stopped by admin."
        job.save(update_fields=["should_stop", "status", "error_message"])

        self.message_user(
            request,
            f"Job #{job.id} stopped.",
            messages.SUCCESS,
        )

        return redirect("admin:contents_generationjob_changelist")