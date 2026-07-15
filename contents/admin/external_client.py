from django.contrib import admin
from django.utils.html import format_html

from contents.models import ExternalClient


@admin.register(ExternalClient)
class ExternalClientAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "masked_api_key",
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
        "api_key",
        "callback_url",
        "notes",
    )

    readonly_fields = (
        "api_key",
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
                    "api_key",
                    "callback_url",
                ),
                "description": (
                    "The API key is generated automatically when the "
                    "client is created."
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
        description="API Key",
    )
    def masked_api_key(self, obj):
        if not obj.api_key:
            return "-"

        visible = obj.api_key[-8:]

        return format_html(
            "<code>••••••••{}</code>",
            visible,
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
