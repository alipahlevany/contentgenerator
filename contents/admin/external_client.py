from django.contrib import admin
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
                    "recovered. Use the controlled rotation method to "
                    "issue a replacement key."
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

    @admin.display(
        description="API Key Identifier",
    )
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

    @admin.action(
        description="Activate selected clients",
    )
    def activate_clients(self, request, queryset):
        updated = queryset.update(is_active=True)

        self.message_user(
            request,
            f"{updated} client(s) activated.",
        )

    @admin.action(
        description="Deactivate selected clients",
    )
    def deactivate_clients(self, request, queryset):
        updated = queryset.update(is_active=False)

        self.message_user(
            request,
            f"{updated} client(s) deactivated.",
        )
