from django.contrib import admin
from django.contrib.auth.hashers import make_password
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html

from contents.models import ExternalClient


@admin.register(ExternalClient)
class ExternalClientAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "api_key_identifier",
        "callback_url",
        "is_active",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "is_active",
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