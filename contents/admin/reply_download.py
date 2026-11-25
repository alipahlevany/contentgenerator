import csv
import hashlib
import json

from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django import forms
from django.db import transaction
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import reverse

from contents.core_services.exports.service import export_contents_for_client
from contents.models import ExternalClient


class ExportDestinationChoice(forms.ModelChoiceField):
    def to_python(self, value):
        return None if value == "__new__" else super().to_python(value)


class ReplyExportActionForm(ActionForm):
    export_client = ExportDestinationChoice(
        queryset=ExternalClient.objects.filter(is_active=True).order_by("name"),
        required=False,
        label="Export destination",
        empty_label="Choose an existing destination…",
    )
    export_destination = forms.CharField(
        required=False,
        max_length=100,
        label="New destination name",
        help_text="For example: November campaign or Customer A",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["export_client"]
        field.choices = [*field.choices, ("__new__", "Create new destination…")]

    def clean(self):
        data = super().clean()
        if (
            self.data.get("export_client") == "__new__"
            and not data.get("export_destination", "").strip()
        ):
            self.add_error("export_destination", "Enter a name for the new destination.")
        return data


class ReplyDownloadActionsMixin:
    action_form = ReplyExportActionForm

    def _download_for_client(self, request, queryset, renderer):
        form = self.action_form(request.POST or None)
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
                            name=name,
                            defaults={
                                "code": "export-" + hashlib.sha256(name.encode()).hexdigest()[:24],
                                "receives_standard_content": False,
                                "receives_email_replies": False,
                                "receives_greetings": False,
                                "notes": "Created as a named destination for manual exports.",
                            },
                        )
                if client and not client.is_active:
                    form.add_error("export_destination", "This destination is inactive. Ask an administrator to review it.")

        if not supplied or not form.is_valid() or client is None:
            return TemplateResponse(
                request,
                "admin/contents/emailreply/export_destination.html",
                {
                    **self.admin_site.each_context(request),
                    "title": "Download selected replies",
                    "opts": self.model._meta,
                    "form": form,
                    "cancel_url": reverse("admin:contents_emailreply_changelist"),
                    "selected_ids": request.POST.getlist("_selected_action"),
                    "select_across": request.POST.get("select_across", "0"),
                    "action": request.POST.get("action"),
                    "selected_count": queryset.count(),
                },
            )

        with transaction.atomic():
            result = export_contents_for_client(
                validated_data={"count": min(queryset.count(), 10000)},
                client=client,
                content_type="email_reply",
                selected_queryset=queryset,
                export_method="manual_download",
            )
            if not result.exported_contents:
                message = (
                    "Daily export limit reached for this destination."
                    if result.quota_exceeded
                    else "No new replies to export for this destination."
                )
                self.message_user(request, message, messages.INFO, extra_tags="reply-export-result")
                return None
            response = renderer(result.exported_contents)
            response["X-Exported-Count"] = str(len(result.exported_contents))
            response["Cache-Control"] = "private, no-store"
            return response

    @staticmethod
    def _export_rows(queryset):
        replies = (
            queryset
            if isinstance(queryset, list)
            else queryset.select_related("language").order_by("id").iterator()
        )
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

    @admin.action(description="Download selected replies (CSV file)")
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
            writer.writerow(
                "'" + str(row[field])
                if str(row[field]).lstrip().startswith(("=", "+", "-", "@"))
                else row[field]
                for field in fields
            )
        return response

    @admin.action(description="Download selected replies (JSON file)")
    def download_replies_json(self, request, queryset):
        return self._download_for_client(request, queryset, self._json_response)

    def _json_response(self, queryset):
        response = HttpResponse(
            json.dumps(list(self._export_rows(queryset)), ensure_ascii=False, indent=2),
            content_type="application/json; charset=utf-8",
        )
        response["Content-Disposition"] = 'attachment; filename="email_replies.json"'
        return response
