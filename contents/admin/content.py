import csv
import hashlib
import json

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django.db import transaction
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html

from contents.models import Content, EmailReply, Greeting, ExternalClient
from contents.core_services.exports.service import export_contents_for_client


class BaseContentAdmin(admin.ModelAdmin):
    content_type_value = None

    list_display = (
        "id",
        "title",
        "source_job",
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
        "generation_job",
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
                    "generation_job",
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
        queryset = super().get_queryset(request).select_related(
            "generation_job",
        )

        if self.content_type_value is None:
            return queryset

        return queryset.filter(
            content_type=self.content_type_value,
        )

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    @admin.display(description="Source job", ordering="generation_job_id")
    def source_job(self, obj):
        if not obj.generation_job_id:
            return "—"

        url = reverse(
            "admin:contents_generationjob_change",
            args=(obj.generation_job_id,),
        )
        return format_html(
            '<a href="{}">Job #{}</a>',
            url,
            obj.generation_job_id,
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


class ExportDestinationChoice(forms.ModelChoiceField):
    def to_python(self, value):
        return None if value == "__new__" else super().to_python(value)


class ReplyExportActionForm(forms.Form):
    export_client = ExportDestinationChoice(
        queryset=ExternalClient.objects.filter(is_active=True).order_by("name"),
        required=False, label="Who or what is this export for?",
        empty_label="Choose an existing destination…",
    )
    export_destination = forms.CharField(required=False, max_length=100, label="New destination name", help_text="For example: November campaign or Customer A")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["export_client"]
        field.choices = [*field.choices, ("__new__", "Create new destination…")]

    def clean(self):
        data = super().clean()
        if self.data.get("export_client") == "__new__" and not data.get("export_destination", "").strip():
            self.add_error("export_destination", "Enter a name for the new destination.")
        return data


class EmailReplyAdmin(BaseContentAdmin):
    content_type_value = "email_reply"
    actions = ("download_replies_csv", "download_replies_json")

    list_display = (
        "id",
        "title",
        "source_job",
        "language",
        "topic",
        "audience",
        "goal",
        "status",
        "created_at",
    )

    def _download_for_client(self, request, queryset, renderer):
        form = ReplyExportActionForm(request.POST or None)
        client = None
        supplied = request.POST.get("export_client") or request.POST.get("export_destination")
        if supplied and form.is_valid():
            client = form.cleaned_data["export_client"]
            name = " ".join(form.cleaned_data["export_destination"].split())
            if client and name:
                form.add_error(None, "Choose an existing destination or enter a new name, not both.")
            elif name:
                client = ExternalClient.objects.filter(name__iexact=name).first()
                if client is None:
                    if not request.user.has_perm("contents.add_externalclient"):
                        form.add_error("export_destination", "You need permission to create a client destination.")
                    else:
                        client, _ = ExternalClient.objects.get_or_create(
                            name=name, defaults={
                                "code": "export-" + hashlib.sha256(name.encode()).hexdigest()[:24],
                                "receives_standard_content": False,
                                "receives_email_replies": False, "receives_greetings": False,
                                "notes": "Created as a named destination for manual exports.",
                            },
                        )
                if client and not client.is_active:
                    form.add_error("export_destination", "This destination is inactive. Ask an administrator to review it.")
        if not supplied or not form.is_valid() or client is None:
            return TemplateResponse(request, "admin/contents/emailreply/export_destination.html", {
                **self.admin_site.each_context(request), "title": "Where is this export going?",
                "opts": self.model._meta, "form": form,
                "selected_ids": request.POST.getlist("_selected_action"),
                "select_across": request.POST.get("select_across", "0"),
                "action": request.POST.get("action"), "selected_count": queryset.count(),
            })
        # Build the file inside the transaction so serialization errors cannot
        # mark contents as exported when no response was produced.
        with transaction.atomic():
            result = export_contents_for_client(
                validated_data={"count": min(queryset.count(), 10000)},
                client=client, content_type="email_reply", selected_queryset=queryset,
            )
            if not result.exported_contents:
                self.message_user(request, "No new replies for this client, or the daily export quota has been reached.", messages.WARNING)
                return None
            response = renderer(result.exported_contents)
            response["X-Exported-Count"] = str(len(result.exported_contents))
            response["Cache-Control"] = "private, no-store"
            return response

    @staticmethod
    def _export_rows(queryset):
        replies = queryset if isinstance(queryset, list) else queryset.select_related("language").order_by("id").iterator()
        for reply in replies:
            yield {
                "id": reply.id,
                "title": reply.title,
                "language": reply.language.code if reply.language else "",
                "body": reply.generated_content,
                "status": reply.status,
                "source_job_id": reply.generation_job_id or "",
                "created_at": reply.created_at.isoformat(),
            }

    @admin.action(description="Download selected replies as CSV")
    def download_replies_csv(self, request, queryset):
        return self._download_for_client(request, queryset, self._csv_response)

    def _csv_response(self, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="email_replies.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        fields = ("id", "title", "language", "body", "status", "source_job_id", "created_at")
        writer.writerow(fields)
        for row in self._export_rows(queryset):
            # Keep spreadsheet software from evaluating model output as a formula.
            writer.writerow(
                "'" + str(row[field]) if str(row[field]).lstrip().startswith(("=", "+", "-", "@"))
                else row[field]
                for field in fields
            )
        return response

    @admin.action(description="Download selected replies as JSON")
    def download_replies_json(self, request, queryset):
        return self._download_for_client(request, queryset, self._json_response)

    def _json_response(self, queryset):
        response = HttpResponse(
            json.dumps(list(self._export_rows(queryset)), ensure_ascii=False, indent=2),
            content_type="application/json; charset=utf-8",
        )
        response["Content-Disposition"] = 'attachment; filename="email_replies.json"'
        return response



class GreetingAdmin(BaseContentAdmin):
    content_type_value = "greeting"

    list_display = (
        "id",
        "title",
        "source_job",
        "language",
        "status",
        "created_at",
    )

    list_filter = (
        "status",
        "language",
        "created_at",
    )

    filter_horizontal = ()

    fieldsets = (
        (
            "👋 Greeting",
            {
                "fields": (
                    "title",
                    "generated_content",
                    "content_hash",
                ),
            },
        ),
        (
            "🌐 Language",
            {
                "fields": (
                    "language",
                    "status",
                    "generation_job",
                ),
            },
        ),
        (
            "Prompt",
            {
                "fields": (
                    "prompt",
                ),
            },
        ),
        (
            "Dates",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )
