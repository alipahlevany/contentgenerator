from django.contrib import admin
from django.utils.html import format_html

from django.db.models import Count, Q

from contents.models import ContentExport, ReplyContentExport


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
        labels = {
            "success": "Returned by API (receipt unconfirmed)",
            "failed": "Failed",
            "pending": "Pending — not confirmed sent",
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
            labels.get(obj.status, obj.get_status_display()),
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


@admin.register(ReplyContentExport)
class ReplyContentExportAdmin(ContentExportAdmin):
    change_list_template = "admin/contents/reply_export/history_change_list.html"
    list_display = (
        "reply_reference",
        "client",
        "status_badge",
        "result_details",
        "short_content_hash",
        "remote_id",
        "exported_at",
        "created_at",
    )
    list_filter = ("client", "status", "exported_at", "created_at")
    search_fields = ContentExportAdmin.search_fields

    def get_queryset(self, request):
        return super().get_queryset(request).filter(content__content_type="email_reply")

    @admin.display(description="Reply reference", ordering="content_id")
    def reply_reference(self, obj):
        return format_html("<strong>Reply #{} — {}</strong>", obj.content_id, obj.content.title)

    @admin.display(description="Result")
    def result_details(self, obj):
        if obj.status == "failed":
            message = (obj.error_message or "No error details were recorded.").strip()
            if len(message) > 140:
                message = f"{message[:137]}..."
            return format_html('<span style="color:#ba2121">{}</span>', message)
        if obj.status == "pending":
            return "No successful delivery confirmation recorded."
        return "Included in a successful API response; client-side receipt or storage is not confirmed."

    def changelist_view(self, request, extra_context=None):
        # These totals are based on the full reply export history, independent
        # of pagination. Distinct reply IDs avoid counting a re-exported
        # changed version as another reply.
        rows = self.get_queryset(request).values("client_id", "client__name").annotate(
            total_records=Count("id"),
            successful_records=Count("id", filter=Q(status="success")),
            successful_replies=Count("content_id", filter=Q(status="success"), distinct=True),
            failed_records=Count("id", filter=Q(status="failed")),
            failed_replies=Count("content_id", filter=Q(status="failed"), distinct=True),
            pending_records=Count("id", filter=Q(status="pending")),
            pending_replies=Count("content_id", filter=Q(status="pending"), distinct=True),
        ).order_by("client__name")
        history = self.get_queryset(request)
        extra_context = {
            **(extra_context or {}),
            "reply_export_totals": rows,
            "reply_export_record_count": history.count(),
            "successful_reply_records": history.filter(status="success").count(),
            "successful_unique_replies": history.filter(status="success").values("content_id").distinct().count(),
            "failed_reply_records": history.filter(status="failed").count(),
            "failed_unique_replies": history.filter(status="failed").values("content_id").distinct().count(),
            "pending_reply_records": history.filter(status="pending").count(),
            "pending_unique_replies": history.filter(status="pending").values("content_id").distinct().count(),
        }
        return super().changelist_view(request, extra_context=extra_context)
