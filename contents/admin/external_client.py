from django.contrib import admin
from django.contrib.auth.hashers import make_password
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponseNotAllowed
from django.views.decorators.debug import sensitive_post_parameters
from django.utils.html import format_html

from contents.models import ExternalClient


@admin.register(ExternalClient)
class ExternalClientAdmin(admin.ModelAdmin):
    change_form_template = "admin/contents/externalclient/change_form.html"

    def get_urls(self):
        return [path(
            "<int:object_id>/replace-api-key/",
            self.admin_site.admin_view(sensitive_post_parameters()(self.replace_api_key)),
            name="contents_externalclient_replace_api_key",
        )] + super().get_urls()

    def replace_api_key(self, request, object_id):
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        with transaction.atomic():
            client = ExternalClient.objects.select_for_update().filter(pk=object_id).first()
            if client is None:
                raise Http404
            if not self.has_change_permission(request, client):
                raise PermissionDenied
            change_url = reverse("admin:contents_externalclient_change", args=(client.pk,))
            context = {
                **self.admin_site.each_context(request), "opts": self.model._meta,
                "client": client, "client_change_url": change_url,
                "client_list_url": reverse("admin:contents_externalclient_changelist"),
            }
            token_data = {"client": client.pk, "prefix": client.api_key_prefix}
            if request.method == "POST":
                try:
                    confirmed = signing.loads(request.POST.get("confirmation", ""), salt="replace-client-key", max_age=600)
                except signing.BadSignature:
                    raise PermissionDenied("Confirmation expired. Open the confirmation page again.")
                if confirmed != token_data:
                    raise PermissionDenied("This key has already changed. Open the client page again.")
                raw_key = client.rotate_api_key()
                self.log_change(request, client, "Replaced API key.")
                context.update(title="API key replaced", api_key=raw_key, replaced=True)
                response = TemplateResponse(request, "admin/contents/externalclient/api_key_created.html", context)
            else:
                context.update(title="Replace API key", confirmation=signing.dumps(token_data, salt="replace-client-key"))
                response = TemplateResponse(request, "admin/contents/externalclient/replace_api_key.html", context)
            response["Cache-Control"] = "private, no-store"
            response["Referrer-Policy"] = "no-referrer"
            return response

    list_display = (
        "name",
        "code",
        "api_key_identifier",
        "callback_url",
        "receives_standard_content",
        "receives_email_replies",
        "receives_greetings",
        "is_active",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "is_active",
        "receives_standard_content",
        "receives_email_replies",
        "receives_greetings",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "name",
        "code",
        "api_key_prefix",
        "callback_url",
        "notes",
    )

    readonly_fields = (
        "api_key_identifier",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Client Information",
            {
                "fields": (
                    "name",
                    "code",
                    "is_active",
                ),
            },
        ),
        (
            "API Access",
            {
                "fields": (
                    "api_key_identifier",
                    "callback_url",
                    "receives_standard_content",
                    "receives_email_replies",
                    "receives_greetings",
                ),
                "description": (
                    "API key secrets are stored hashed and cannot be "
                    "recovered. Use key rotation to issue a replacement."
                ),
            },
        ),
        (
            "Notes",
            {
                "fields": (
                    "notes",
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
                "classes": (
                    "collapse",
                ),
            },
        ),
    )

    ordering = (
        "name",
    )

    actions = (
        "activate_clients",
        "deactivate_clients",
    )

    def save_model(self, request, obj, form, change):
        request._generated_external_client_api_key = None

        if not change and not obj.api_key_prefix and not obj.api_key_hash:
            prefix, secret, raw_key = obj._new_api_key()

            obj.api_key = None
            obj.api_key_prefix = prefix
            obj.api_key_hash = make_password(secret)

            request._generated_external_client_api_key = raw_key

        super().save_model(request, obj, form, change)

    def response_add(self, request, obj, post_url_continue=None):
        generated_api_key = getattr(
            request,
            "_generated_external_client_api_key",
            None,
        )

        if not generated_api_key:
            return super().response_add(
                request,
                obj,
                post_url_continue,
            )

        context = {
            **self.admin_site.each_context(request),
            "title": "API key generated",
            "client": obj,
            "api_key": generated_api_key,
            "client_list_url": reverse(
                "admin:contents_externalclient_changelist",
            ),
            "client_change_url": reverse(
                "admin:contents_externalclient_change",
                args=(obj.pk,),
            ),
        }

        return TemplateResponse(
            request,
            "admin/contents/externalclient/api_key_created.html",
            context,
        )

    @admin.display(description="API Key Identifier")
    def api_key_identifier(self, obj):
        if obj.api_key_prefix:
            return format_html(
                "<code>cg_{}_••••••••</code>",
                obj.api_key_prefix,
            )

        if not obj.api_key:
            return "-"

        return format_html(
            "<code>legacy_••••••••</code>",
        )

    @admin.action(description="Activate selected clients")
    def activate_clients(self, request, queryset):
        updated = queryset.update(is_active=True)

        self.message_user(
            request,
            f"{updated} client(s) activated.",
        )

    @admin.action(description="Deactivate selected clients")
    def deactivate_clients(self, request, queryset):
        updated = queryset.update(is_active=False)

        self.message_user(
            request,
            f"{updated} client(s) deactivated.",
        )
