from .tasks import run_generation_job_task
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import redirect
from django.contrib import admin, messages

from .models import (
    AppSettings,
    Audience,
    BlockedKeyword,
    Content,
    ContentRule,
    GenerationJob,
    GenerationJobAudienceDistribution,
    GenerationJobLanguageDistribution,
    GenerationJobLog,
    GenerationJobTopicDistribution,
    Goal,
    Language,
    PromptTemplate,
    Topic,
    GenerationJobGoalDistribution,
)
from .tasks import run_generation_job_task


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Audience)
class AudienceAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    ordering = ("name",)


@admin.register(BlockedKeyword)
class BlockedKeywordAdmin(admin.ModelAdmin):
    list_display = ("id", "keyword", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("keyword",)


@admin.register(ContentRule)
class ContentRuleAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "prompt_text")


@admin.register(AppSettings)
class AppSettingsAdmin(admin.ModelAdmin):

    actions = [
        "generate_new_api_token",
        "clear_api_token",
    ]

    list_display = (
        "id",
        "model_name",
        "max_output_tokens",
        "temperature",
        "has_api_key",
        "auto_generate_api_key",
        "is_active",
    )

    @admin.action(description="Generate New API Token")
    def generate_new_api_token(self, request, queryset):
        import secrets

        for obj in queryset:
            obj.api_secret_key = secrets.token_urlsafe(48)
            obj.save(update_fields=["api_secret_key"])

        self.message_user(
            request,
            "API token regenerated successfully."
        )

    @admin.action(description="Clear API Token")
    def clear_api_token(self, request, queryset):
        for obj in queryset:
            obj.api_secret_key = ""
            obj.save(update_fields=["api_secret_key"])

        self.message_user(
            request,
            "API token cleared successfully."
        )

    def has_api_key(self, obj):
        return bool(obj.api_secret_key)

    has_api_key.boolean = True
    has_api_key.short_description = "API Key"

    fieldsets = (
        (
            "OpenAI Settings",
            {
                "fields": (
                    "model_name",
                    "max_output_tokens",
                    "temperature",
                )
            },
        ),
(
    "API Settings",
    {
        "fields": (
            "api_secret_key",
            "auto_generate_api_key",
            "default_generation_job",
        )
    },
),
        (
            "Status",
            {
                "fields": (
                    "is_active",
                )
            },
        ),
    )
@admin.register(Content)
class ContentAdmin(admin.ModelAdmin):
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

    search_fields = ("title", "prompt", "generated_content")

    list_filter = (
        "status",
        "language",
        "topic",
        "audience",
        "goal",
        "prompt_template",
        "created_at",
    )

    fieldsets = (
        (
            "Generated Output",
            {
                "fields": (
                    "title",
                    "generated_content",
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
                "fields": ("prompt",)
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

    filter_horizontal = ("rules",)
    readonly_fields = ("created_at", "updated_at")


class GenerationJobLanguageDistributionInline(admin.TabularInline):
    model = GenerationJobLanguageDistribution
    extra = 1
    fields = ("language", "percentage")


class GenerationJobTopicDistributionInline(admin.TabularInline):
    model = GenerationJobTopicDistribution
    extra = 1
    fields = ("topic", "percentage")


class GenerationJobAudienceDistributionInline(admin.TabularInline):
    model = GenerationJobAudienceDistribution
    extra = 1
    fields = ("audience", "percentage")
class GenerationJobGoalDistributionInline(admin.TabularInline):
    model = GenerationJobGoalDistribution
    extra = 1
    fields = ("goal", "percentage")    

class GenerationJobGoalDistributionInline(admin.TabularInline):
    model = GenerationJobGoalDistribution
    extra = 1
    fields = ("goal", "percentage")

class GenerationJobLogInline(admin.TabularInline):
    model = GenerationJobLog
    extra = 0
    readonly_fields = ("level", "message", "created_at")
    fields = ("level", "message", "created_at")
    can_delete = False
    max_num = 0

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(GenerationJob)
class GenerationJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "count",
        "delay_seconds",
        "prompt_template",
        "generated_count",
        "skipped_count",
        "progress_display",
        "status",
        "short_error_message",
        "created_at",
        "job_actions",
    )

    list_filter = (
        "status",
        "languages",
        "topics",
        "audiences",
        "goals",
        "prompt_template",
        "created_at",
    )

    readonly_fields = (
        "generated_count",
        "skipped_count",
        "current_step",
        "progress_display",
        "status",
        "error_message",
        "created_at",
        "updated_at",
    )

    filter_horizontal = (
        "languages",
        "topics",
        "audiences",
        "goals",
        "rules",
    )

    inlines = (
        GenerationJobLanguageDistributionInline,
        GenerationJobTopicDistributionInline,
        GenerationJobAudienceDistributionInline,
        GenerationJobGoalDistributionInline,
        
    )

    def progress_display(self, obj):
        if not obj.count:
            return "0%"

        percent = int((obj.current_step / obj.count) * 100)
        return f"{percent}% ({obj.current_step}/{obj.count})"

    progress_display.short_description = "Progress"

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
        start_url = reverse(
            "admin:contents_generationjob_start",
            args=[obj.id],
        )

        stop_url = reverse(
            "admin:contents_generationjob_stop",
            args=[obj.id],
        )

        return format_html(
            """
            <div style="display:flex;gap:6px;white-space:nowrap;">
                <a href="{}" style="
                    background:#198754;
                    color:white;
                    padding:6px 12px;
                    border-radius:4px;
                    text-decoration:none;
                    font-weight:600;
                    min-width:65px;
                    text-align:center;
                ">▶ Start</a>

                <a href="{}" style="
                    background:#dc3545;
                    color:white;
                    padding:6px 12px;
                    border-radius:4px;
                    text-decoration:none;
                    font-weight:600;
                    min-width:65px;
                    text-align:center;
                ">■ Stop</a>
            </div>
            """,
            start_url,
            stop_url,
        )

    job_actions.short_description = "Action"

    def short_error_message(self, obj):
        if not obj.error_message:
            return "-"

        if len(obj.error_message) > 50:
            return obj.error_message[:50] + "..."

        return obj.error_message

    short_error_message.short_description = "Error"

    def start_job(self, request, job_id):
        job = GenerationJob.objects.get(id=job_id)

        if job.status == "running":
            self.message_user(
                request,
                f"Job #{job.id} is already running.",
                level=messages.WARNING,
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
            level=messages.SUCCESS,
        )

        return redirect("admin:contents_generationjob_changelist")

    def stop_job(self, request, job_id):
        job = GenerationJob.objects.get(id=job_id)

        if job.status != "running":
            self.message_user(
                request,
                f"Job #{job.id} is not running.",
                level=messages.INFO,
            )
            return redirect("admin:contents_generationjob_changelist")

        job.should_stop = True
        job.status = "stopped"
        job.error_message = "Job stopped by admin."
        job.save(update_fields=["should_stop", "status", "error_message"])

        self.message_user(
            request,
            f"Job #{job.id} stopped.",
            level=messages.SUCCESS,
        )

        return redirect("admin:contents_generationjob_changelist")


@admin.register(GenerationJobLog)
class GenerationJobLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "job",
        "level",
        "message",
        "created_at",
    )

    list_filter = (
        "level",
        "created_at",
    )

    search_fields = (
        "message",
    )

    ordering = (
        "-created_at",
    )

    readonly_fields = (
        "job",
        "level",
        "message",
        "created_at",
    )