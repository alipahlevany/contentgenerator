from django.contrib import admin
from django.utils.html import format_html

from contents.models import ContentExport


@admin.register(ContentExport)
class ContentExportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "content_link",
        "client",
        "status_badge",
        "short_content_hash",
        "remote_id",
        "exported_at",
        "created_at",
    )

    list_filter = (
        "status",
        "client",
        "exported_at",
        "created_at",
    )

    search_fields = (
        "content__title",
        "client__name",
        "client__code",
        "content_hash",
        "remote_id",
        "error_message",
    )

    readonly_fields = (
        "content",
        "client",
        "content_hash",
        "status",
        "exported_at",
        "remote_id",
        "error_message",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Export",
            {
                "fields": (
                    "content",
                    "client",
                    "status",
                ),
            },
        ),
        (
            "Version",
            {
                "fields": (
                    "content_hash",
                    "remote_id",
                ),
            },
        ),
        (
            "Result",
            {
                "fields": (
                    "exported_at",
                    "error_message",
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
        "-created_at",
    )

    date_hierarchy = "created_at"

    list_select_related = (
        "content",
        "client",
    )

    actions = (
        "mark_as_pending",
        "mark_as_failed",
    )

    @admin.display(
        description="Content",
        ordering="content__title",
    )
    def content_link(self, obj):
        title = obj.content.title

        if len(title) > 60:
            title = f"{title[:57]}..."

        return format_html(
            "<strong>#{} — {}</strong>",
            obj.content_id,
            title,
        )

    @admin.display(
        description="Status",
        ordering="status",
    )
    def status_badge(self, obj):
        colors = {
            "success": "#198754",
            "failed": "#dc3545",
            "pending": "#fd7e14",
        }

        color = colors.get(
            obj.status,
            "#6c757d",
        )

        return format_html(
            (
                '<span style="display:inline-block;'
                'padding:3px 8px;border-radius:10px;'
                'background:{};color:#fff;font-weight:600;">'
                "{}</span>"
            ),
            color,
            obj.get_status_display(),
        )

    @admin.display(
        description="Content Hash",
        ordering="content_hash",
    )
    def short_content_hash(self, obj):
        if not obj.content_hash:
            return "-"

        return format_html(
            "<code>{}</code>",
            obj.content_hash[:16],
        )

    @admin.action(
        description="Mark selected exports as pending",
    )
    def mark_as_pending(self, request, queryset):
        updated = queryset.update(
            status="pending",
            exported_at=None,
            error_message="",
        )

        self.message_user(
            request,
            f"{updated} export(s) marked as pending.",
        )

    @admin.action(
        description="Mark selected exports as failed",
    )
    def mark_as_failed(self, request, queryset):
        updated = queryset.update(
            status="failed",
        )

        self.message_user(
            request,
            f"{updated} export(s) marked as failed.",
        )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return True
