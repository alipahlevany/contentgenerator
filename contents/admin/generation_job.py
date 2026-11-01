from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils import timezone
from django.db.models import Subquery

from contents.models import GenerationJob, GenerationJobLog
from contents.tasks import queue_generation_job


class GenerationJobLogInline(admin.TabularInline):
    model = GenerationJobLog
    extra = 0
    can_delete = False
    readonly_fields = ("level", "message", "created_at")
    fields = ("level", "message", "created_at")
    ordering = ("-created_at",)
    max_num = 20
    verbose_name_plural = "Latest job logs"

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        match = getattr(request, "resolver_match", None)
        object_id = match.kwargs.get("object_id") if match else None
        if not object_id or not str(object_id).isdigit():
            return queryset.none()
        # max_num limits added forms, not existing rows. Restrict the query
        # itself so a long-running job does not render thousands of forms.
        latest_ids = queryset.filter(job_id=object_id).order_by(
            "-created_at", "-pk"
        ).values("pk")[:20]
        return queryset.filter(pk__in=Subquery(latest_ids))

    def has_add_permission(self, request, obj=None):
        return False


class GenerationJobAdmin(admin.ModelAdmin):
    change_list_template = "admin/contents/generationjob/change_list.html"

    delete_confirmation_template = (
        "admin/contents/generationjob/delete_confirmation.html"
    )
    inlines = (GenerationJobLogInline,)

    list_display = (
        "id",
        "generation_type_badge",
        "status_badge",
        "target_count",
        "generated_badge",
        "skipped_badge",
        "remaining_badge",
        "progress_bar",
        "delay_display",
        "created_display",
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

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def job_type_help(self, obj=None):
        descriptions = {
            "greeting": "Short, natural greetings selected from your active languages.",
            "email_reply": "Natural email replies selected from your active languages.",
        }
        text = descriptions.get(
            getattr(obj, "generation_type", ""),
            "Standard content generated from your global weighted pool.",
        )
        return format_html('<div class="cg-job-note">{}</div>', text)

    job_type_help.short_description = "Job Type Description"

    def pool_mode_display(self, obj=None):
        if obj and obj.generation_type in ("greeting", "email_reply"):
            title = "Active language pool"
            detail = "This generation type uses your active languages."
        else:
            title = "Global weighted pool"
            detail = (
                "Active languages, topics, audiences, goals, prompt templates, "
                "and content rules are selected using their configured weights."
            )
        return format_html(
            '<div class="cg-job-note"><strong>{}</strong><br>{}</div>',
            title, detail,
        )

    pool_mode_display.short_description = "Selection Mode"

    def generation_type_badge(self, obj):
        return format_html(
            '<span class="cg-job-type cg-job-type--{}">{}</span>',
            obj.generation_type, obj.get_generation_type_display(),
        )

    generation_type_badge.short_description = "Type"
    generation_type_badge.admin_order_field = "generation_type"

    def status_badge(self, obj):
        return format_html(
            '<span class="cg-job-status cg-job-status--{}">'
            '<i aria-hidden="true"></i>{}</span>',
            obj.status, obj.get_status_display(),
        )

    status_badge.short_description = "Status"
    status_badge.admin_order_field = "status"

    @admin.display(description="Target", ordering="count")
    def target_count(self, obj):
        return f"{obj.count:,}"

    @admin.display(description="Delay", ordering="delay_seconds")
    def delay_display(self, obj):
        return f"{obj.delay_seconds:g} s"

    @admin.display(description="Created", ordering="created_at")
    def created_display(self, obj):
        created = timezone.localtime(obj.created_at)
        return format_html(
            '<span class="cg-job-date">{}<small>{}</small></span>',
            created.strftime("%b %d, %Y"), created.strftime("%H:%M %Z"),
        )

    def generated_badge(self, obj):
        return self.number_badge(obj.generated_count, "saved")

    generated_badge.short_description = "Generated"
    generated_badge.admin_order_field = "generated_count"

    def skipped_badge(self, obj):
        return self.number_badge(obj.skipped_count, "warning" if obj.skipped_count else "muted")

    skipped_badge.short_description = "Skipped"
    skipped_badge.admin_order_field = "skipped_count"

    def remaining_badge(self, obj):
        return self.number_badge(self._remaining(obj), "muted")

    remaining_badge.short_description = "Remaining"

    def remaining_display(self, obj):
        return self._remaining(obj)

    remaining_display.short_description = "Remaining"

    @staticmethod
    def _remaining(obj):
        return max(obj.count - obj.generated_count, 0)

    @staticmethod
    def number_badge(value, tone):
        return format_html(
            '<span class="cg-job-number cg-job-number--{}">{}</span>',
            tone, f"{value:,}",
        )

    def progress_bar(self, obj):
        percent = 0 if not obj.count else int((obj.generated_count / obj.count) * 100)
        percent = max(0, min(percent, 100))
        return format_html(
            '<div class="cg-job-progress cg-job-progress--{}">'
            '<div class="cg-job-progress__meta"><strong>{}%</strong>'
            '<span>{} / {}</span></div>'
            '<div class="cg-job-progress__track" role="progressbar" '
            'aria-label="Generation progress" aria-valuemin="0" '
            'aria-valuemax="100" aria-valuenow="{}">'
            '<span style="width:{}%"></span></div></div>',
            obj.status, percent, f"{obj.generated_count:,}", f"{obj.count:,}",
            percent, percent,
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
            return format_html('<a class="cg-job-action cg-job-action--stop" href="{}">Stop</a>', stop_url)

        if obj.generated_count >= obj.count or obj.status == "completed":
            detail_url = reverse("admin:contents_generationjob_change", args=[obj.id])
            return format_html('<a class="cg-job-action cg-job-action--view" href="{}">View run</a>', detail_url)

        label = "Resume" if obj.status in ("stopped", "failed") or obj.generated_count else "Start"
        return format_html('<a class="cg-job-action" href="{}">{}</a>', start_url, label)

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

        queue_generation_job(job.id, job.generation_type)

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
