from django.contrib import admin

from contents.models import ContentDelivery


@admin.register(ContentDelivery)
class ContentDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "client",
        "content",
        "purpose",
        "status",
        "attempt_count",
        "last_attempt_at",
        "delivered_at",
    )
    list_filter = (
        "status",
        "purpose",
        "client",
        "created_at",
    )
    search_fields = (
        "client__name",
        "client__code",
        "content__title",
        "destination_url",
        "last_error",
    )
    list_select_related = ("client", "content")
    ordering = ("-created_at",)
    readonly_fields = (
        "client",
        "content",
        "content_hash",
        "destination_url",
        "purpose",
        "status",
        "attempt_count",
        "last_error",
        "last_attempt_at",
        "delivered_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

