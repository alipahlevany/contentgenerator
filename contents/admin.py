import secrets

from django import forms
from django.contrib import admin, messages
from django.core.cache import cache
from django.db.models.functions import Lower
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from .models import (
    AppSettings,
    Audience,
    BlockedKeyword,
    Content,
    ContentRule,
    GenerationJob,
    GenerationJobLog,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)
from .tasks import run_daily_generation_task, run_generation_job_task


class TxtImportForm(forms.Form):
    txt_file = forms.FileField(
        label="TXT file",
        help_text="Upload a .txt file. Each line will be imported as one item.",
    )

    is_active = forms.BooleanField(
        label="Set imported items as active",
        required=False,
        initial=True,
    )


class NameTxtImportAdminMixin:
    import_field_name = "name"
    change_list_template = "admin/contents/import_change_list.html"

    def get_cache_keys_to_delete(self):
        return []

    def clear_related_cache(self):
        for cache_key in self.get_cache_keys_to_delete():
            cache.delete(cache_key)

    def get_urls(self):
        urls = super().get_urls()

        app_label = self.model._meta.app_label
        model_name = self.model._meta.model_name

        custom_urls = [
            path(
                "import-txt/",
                self.admin_site.admin_view(self.import_txt_view),
                name=f"{app_label}_{model_name}_import_txt",
            ),
        ]

        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}

        app_label = self.model._meta.app_label
        model_name = self.model._meta.model_name

        extra_context["import_txt_url"] = reverse(
            f"admin:{app_label}_{model_name}_import_txt"
        )

        return super().changelist_view(
            request,
            extra_context=extra_context,
        )

    def get_import_object_kwargs(self, value, is_active):
        return {
            self.import_field_name: value,
            "weight": 1,
            "is_active": is_active,
        }

    def import_txt_view(self, request):
        if not self.has_add_permission(request):
            self.message_user(
                request,
                "You do not have permission to import items.",
                level=messages.ERROR,
            )
            return redirect("..")

        form = TxtImportForm(
            request.POST or None,
            request.FILES or None,
        )

        if request.method == "POST" and form.is_valid():
            txt_file = form.cleaned_data["txt_file"]
            is_active = form.cleaned_data["is_active"]

            file_bytes = txt_file.read()

            try:
                raw_text = file_bytes.decode("utf-8-sig")
            except UnicodeDecodeError:
                raw_text = file_bytes.decode("latin-1")

            lines = [
                line.strip()
                for line in raw_text.splitlines()
                if line.strip()
            ]

            existing_values = set(
                self.model.objects
                .annotate(lower_value=Lower(self.import_field_name))
                .values_list("lower_value", flat=True)
            )

            new_objects = []
            seen_in_file = set()
            skipped_duplicates = 0

            for value in lines:
                normalized_value = value.casefold()

                if (
                    normalized_value in existing_values
                    or normalized_value in seen_in_file
                ):
                    skipped_duplicates += 1
                    continue

                new_objects.append(
                    self.model(
                        **self.get_import_object_kwargs(
                            value=value,
                            is_active=is_active,
                        )
                    )
                )

                seen_in_file.add(normalized_value)

            if new_objects:
                self.model.objects.bulk_create(new_objects)
                self.clear_related_cache()

            self.message_user(
                request,
                (
                    f"Import completed. "
                    f"Created: {len(new_objects)}. "
                    f"Skipped duplicates: {skipped_duplicates}."
                ),
                level=messages.SUCCESS,
            )

            return redirect("..")

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": f"Import {self.model._meta.verbose_name_plural} from TXT",
            "form": form,
        }

        return render(
            request,
            "admin/contents/import_txt_form.html",
            context,
        )


class ActiveStatusAdminMixin:
    actions = [
        "activate_selected_items",
        "deactivate_selected_items",
    ]

    @admin.action(description="Activate selected items")
    def activate_selected_items(self, request, queryset):
        updated_count = queryset.update(is_active=True)

        if hasattr(self, "clear_related_cache"):
            self.clear_related_cache()

        self.message_user(
            request,
            f"{updated_count} item(s) activated successfully.",
            level=messages.SUCCESS,
        )

    @admin.action(description="Deactivate selected items")
    def deactivate_selected_items(self, request, queryset):
        updated_count = queryset.update(is_active=False)

        if hasattr(self, "clear_related_cache"):
            self.clear_related_cache()

        self.message_user(
            request,
            f"{updated_count} item(s) deactivated successfully.",
            level=messages.SUCCESS,
        )


@admin.register(Topic)
class TopicAdmin(
    ActiveStatusAdminMixin,
    NameTxtImportAdminMixin,
    admin.ModelAdmin,
):
    list_display = ("id", "name", "weight", "is_active", "created_at")
    list_display_links = ("id", "name")
    list_editable = ("weight", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("-weight", "-id")


@admin.register(Audience)
class AudienceAdmin(
    ActiveStatusAdminMixin,
    NameTxtImportAdminMixin,
    admin.ModelAdmin,
):
    list_display = ("id", "name", "weight", "is_active", "created_at")
    list_display_links = ("id", "name")
    list_editable = ("weight", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("-weight", "-id")


@admin.register(Goal)
class GoalAdmin(
    ActiveStatusAdminMixin,
    NameTxtImportAdminMixin,
    admin.ModelAdmin,
):
    list_display = ("id", "name", "weight", "is_active", "created_at")
    list_display_links = ("id", "name")
    list_editable = ("weight", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("-weight", "-id")


@admin.register(Language)
class LanguageAdmin(
    ActiveStatusAdminMixin,
    admin.ModelAdmin,
):
    list_display = ("id", "name", "code", "weight", "is_active", "created_at")
    list_display_links = ("id", "name")
    list_editable = ("weight", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    ordering = ("-weight", "name")


@admin.register(BlockedKeyword)
class BlockedKeywordAdmin(
    ActiveStatusAdminMixin,
    NameTxtImportAdminMixin,
    admin.ModelAdmin,
):
    import_field_name = "keyword"

    list_display = ("id", "keyword", "is_active", "created_at")
    list_display_links = ("id", "keyword")
    list_editable = ("is_active",)
    list_filter = ("is_active",)
    search_fields = ("keyword",)
    ordering = ("-id",)

    def get_import_object_kwargs(self, value, is_active):
        return {
            "keyword": value,
            "is_active": is_active,
        }

    def get_cache_keys_to_delete(self):
        return ["active_blocked_keywords"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        self.clear_related_cache()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        self.clear_related_cache()

    def delete_queryset(self, request, queryset):
        super().delete_queryset(request, queryset)
        self.clear_related_cache()


@admin.register(ContentRule)
class ContentRuleAdmin(
    ActiveStatusAdminMixin,
    NameTxtImportAdminMixin,
    admin.ModelAdmin,
):
    list_display = ("id", "name", "weight", "is_active", "created_at")
    list_display_links = ("id", "name")
    list_editable = ("weight", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "prompt_text")
    ordering = ("-weight", "-id")

    def get_import_object_kwargs(self, value, is_active):
        return {
            "name": value,
            "prompt_text": value,
            "weight": 1,
            "is_active": is_active,
        }


@admin.register(PromptTemplate)
class PromptTemplateAdmin(
    ActiveStatusAdminMixin,
    admin.ModelAdmin,
):
    list_display = ("id", "name", "weight", "is_active", "created_at")
    list_display_links = ("id", "name")
    list_editable = ("weight", "is_active")
    list_filter = ("is_active", "created_at")
    search_fields = (
        "name",
        "system_prompt",
        "user_prompt_template",
    )
    ordering = ("-weight", "-id")

    fieldsets = (
        (
            "Template Info",
            {
                "fields": (
                    "name",
                    "weight",
                    "is_active",
                )
            },
        ),
        (
            "System Prompt",
            {
                "fields": (
                    "system_prompt",
                )
            },
        ),
        (
            "User Prompt Template",
            {
                "fields": (
                    "user_prompt_template",
                )
            },
        ),
    )


class AppSettingsForm(forms.ModelForm):
    daily_generation_time = forms.TimeField(
        label="Daily generation time",
        required=True,
        input_formats=["%H:%M"],
        widget=forms.TimeInput(
            format="%H:%M",
            attrs={
                "type": "time",
                "style": "width: 160px;",
            },
        ),
        help_text="Server time. Example: 02:00",
    )

    class Meta:
        model = AppSettings
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["auto_daily_generation_enabled"].label = (
            "Enable daily generation"
        )
        self.fields["daily_generation_count"].label = "Contents per day"
        self.fields["daily_generation_delay_seconds"].label = (
            "Delay between contents"
        )

        self.fields["daily_generation_count"].widget.attrs.update(
            {
                "style": "width: 120px;",
            }
        )

        self.fields["daily_generation_delay_seconds"].widget.attrs.update(
            {
                "style": "width: 120px;",
            }
        )

        if self.instance and self.instance.pk:
            hour = str(self.instance.daily_generation_hour).zfill(2)
            minute = str(self.instance.daily_generation_minute).zfill(2)
            self.initial["daily_generation_time"] = f"{hour}:{minute}"
        else:
            self.initial["daily_generation_time"] = "02:00"

    def save(self, commit=True):
        instance = super().save(commit=False)

        daily_generation_time = self.cleaned_data.get(
            "daily_generation_time"
        )

        if daily_generation_time:
            instance.daily_generation_hour = daily_generation_time.hour
            instance.daily_generation_minute = daily_generation_time.minute

        if commit:
            instance.save()
            self.save_m2m()

        return instance


@admin.register(AppSettings)
class AppSettingsAdmin(admin.ModelAdmin):
    form = AppSettingsForm

    actions = [
        "regenerate_api_token",
        "disable_external_api_access",
        "run_daily_generation_now",
    ]

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
                "description": (
                    "Settings used when the system generates content with OpenAI."
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
                "description": (
                    "Turn this on to let the system create a new Generation Job "
                    "automatically every day."
                ),
            },
        ),
        (
            "3. External API",
            {
                "fields": (
                    "external_api_access",
                ),
                "description": (
                    "External systems use this key to access the API. "
                    "Use the actions in the App Settings list to regenerate or disable it."
                ),
            },
        ),
        (
            "4. Status",
            {
                "fields": (
                    "is_active",
                    "last_daily_generation_date",
                ),
                "description": (
                    "Keep only one App Settings record active."
                ),
            },
        ),
    )

    @admin.action(description="Regenerate API Token")
    def regenerate_api_token(self, request, queryset):
        for obj in queryset:
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
            "API token regenerated successfully.",
            level=messages.SUCCESS,
        )

    @admin.action(description="Disable External API Access")
    def disable_external_api_access(self, request, queryset):
        for obj in queryset:
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
            "External API access disabled successfully.",
            level=messages.SUCCESS,
        )

    @admin.action(description="Run Daily Generation Now")
    def run_daily_generation_now(self, request, queryset):
        run_daily_generation_task.delay(force=True)

        self.message_user(
            request,
            "Daily generation task started.",
            level=messages.SUCCESS,
        )

    def save_model(self, request, obj, form, change):
        if obj.auto_generate_api_key and not obj.api_secret_key:
            obj.api_secret_key = secrets.token_urlsafe(48)

        super().save_model(request, obj, form, change)

        cache.delete("active_app_settings")

    def word_range(self, obj):
        return f"{obj.min_words} - {obj.max_words}"

    word_range.short_description = "Words"

    def daily_generation_time_display(self, obj):
        hour = str(obj.daily_generation_hour).zfill(2)
        minute = str(obj.daily_generation_minute).zfill(2)

        return f"{hour}:{minute}"

    daily_generation_time_display.short_description = "Daily Time"

    def external_api_status(self, obj):
        if obj and obj.api_secret_key:
            return "Enabled"

        return "Disabled"

    external_api_status.short_description = "External API"

    def external_api_access(self, obj):
        if not obj:
            return "-"

        if not obj.api_secret_key:
            return format_html(
                """
                <div style="
                    max-width:760px;
                    padding:12px 14px;
                    background:#fff8e1;
                    border:1px solid #f0d98c;
                    border-radius:6px;
                    color:#6b5200;
                    line-height:1.6;
                ">
                    <strong>External API is disabled.</strong><br>
                    No external system can use the API until a new token is generated.
                </div>
                """
            )

        return format_html(
            """
            <div style="
                display:flex;
                flex-direction:column;
                gap:8px;
                max-width:760px;
            ">
                <code style="
                    display:block;
                    padding:10px 12px;
                    background:#f6f8fa;
                    border:1px solid #d0d7de;
                    border-radius:6px;
                    font-size:13px;
                    line-height:1.6;
                    user-select:all;
                    word-break:break-all;
                ">{}</code>

                <div style="
                    color:#666;
                    font-size:13px;
                    line-height:1.5;
                ">
                    Select and copy this key. External systems must send it with their API requests.
                    If the key is leaked, go back to the App Settings list and run
                    <strong>Regenerate API Token</strong>.
                </div>
            </div>
            """,
            obj.api_secret_key,
        )

    external_api_access.short_description = "External API Key"


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

    list_display_links = ("id", "title")

    search_fields = (
        "title",
        "prompt",
        "generated_content",
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

    filter_horizontal = ("rules",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(GenerationJob)
class GenerationJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "count",
        "delay_seconds",
        "pool_mode_display",
        "generated_count",
        "skipped_count",
        "progress_display",
        "status",
        "short_error_message",
        "created_at",
        "job_actions",
    )

    list_display_links = ("id",)

    list_filter = (
        "status",
        "created_at",
    )

    search_fields = (
        "=id",
        "error_message",
    )

    readonly_fields = (
        "pool_mode_display",
        "generated_count",
        "skipped_count",
        "current_step",
        "progress_display",
        "status",
        "error_message",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "1. Job Settings",
            {
                "fields": (
                    "count",
                    "delay_seconds",
                )
            },
        ),
        (
            "2. Selection Source",
            {
                "fields": (
                    "pool_mode_display",
                ),
                "description": (
                    "This job automatically uses all active Languages, Topics, "
                    "Audiences, Goals, Prompt Templates, and Content Rules based "
                    "on their weight."
                ),
            },
        ),
        (
            "3. Progress / Result",
            {
                "fields": (
                    "status",
                    "generated_count",
                    "skipped_count",
                    "current_step",
                    "progress_display",
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

    def progress_display(self, obj):
        if not obj.count:
            return "0%"

        percent = int((obj.generated_count / obj.count) * 100)

        return f"{percent}% ({obj.generated_count}/{obj.count})"

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
        job.save(
            update_fields=[
                "should_stop",
                "status",
                "error_message",
            ]
        )

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

    list_display_links = ("id", "job")

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