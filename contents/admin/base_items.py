from django.contrib import admin

from contents.models import (
    Audience,
    BlockedKeyword,
    ContentRule,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)

from .mixins import ActiveStatusAdminMixin, NameTxtImportAdminMixin


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