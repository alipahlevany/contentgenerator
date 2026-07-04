from django.contrib import messages
from django.core.cache import cache
from django.db.models.functions import Lower
from django.shortcuts import redirect, render
from django.urls import path, reverse

from .forms import TxtImportForm


class NameTxtImportAdminMixin:
    import_field_name = "name"
    change_list_template = "admin/contents/import_change_list.html"

    def get_cache_keys_to_delete(self):
        return []

    def clear_related_cache(self):
        for cache_key in self.get_cache_keys_to_delete():
            cache.delete(cache_key)

    def get_urls(self):
        urls = super().get_urls()

        app_label = self.model._meta.app_label
        model_name = self.model._meta.model_name

        custom_urls = [
            path(
                "import-txt/",
                self.admin_site.admin_view(self.import_txt_view),
                name=f"{app_label}_{model_name}_import_txt",
            ),
        ]

        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}

        app_label = self.model._meta.app_label
        model_name = self.model._meta.model_name

        extra_context["import_txt_url"] = reverse(
            f"admin:{app_label}_{model_name}_import_txt"
        )

        return super().changelist_view(request, extra_context=extra_context)

    def get_import_object_kwargs(self, value, is_active):
        return {
            self.import_field_name: value,
            "weight": 1,
            "is_active": is_active,
        }

    def import_txt_view(self, request):
        if not self.has_add_permission(request):
            self.message_user(
                request,
                "You do not have permission to import items.",
                level=messages.ERROR,
            )
            return redirect("..")

        form = TxtImportForm(request.POST or None, request.FILES or None)

        if request.method == "POST" and form.is_valid():
            txt_file = form.cleaned_data["txt_file"]
            is_active = form.cleaned_data["is_active"]

            file_bytes = txt_file.read()

            try:
                raw_text = file_bytes.decode("utf-8-sig")
            except UnicodeDecodeError:
                raw_text = file_bytes.decode("latin-1")

            lines = [
                line.strip()
                for line in raw_text.splitlines()
                if line.strip()
            ]

            existing_values = set(
                self.model.objects
                .annotate(lower_value=Lower(self.import_field_name))
                .values_list("lower_value", flat=True)
            )

            new_objects = []
            seen_in_file = set()
            skipped_duplicates = 0

            for value in lines:
                normalized_value = value.casefold()

                if (
                    normalized_value in existing_values
                    or normalized_value in seen_in_file
                ):
                    skipped_duplicates += 1
                    continue

                new_objects.append(
                    self.model(
                        **self.get_import_object_kwargs(
                            value=value,
                            is_active=is_active,
                        )
                    )
                )

                seen_in_file.add(normalized_value)

            if new_objects:
                self.model.objects.bulk_create(new_objects)
                self.clear_related_cache()

            self.message_user(
                request,
                (
                    f"Import completed. "
                    f"Created: {len(new_objects)}. "
                    f"Skipped duplicates: {skipped_duplicates}."
                ),
                level=messages.SUCCESS,
            )

            return redirect("..")

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": f"Import {self.model._meta.verbose_name_plural} from TXT",
            "form": form,
        }

        return render(
            request,
            "admin/contents/import_txt_form.html",
            context,
        )


class ActiveStatusAdminMixin:
    actions = [
        "activate_selected_items",
        "deactivate_selected_items",
    ]

    def activate_selected_items(self, request, queryset):
        updated_count = queryset.update(is_active=True)

        if hasattr(self, "clear_related_cache"):
            self.clear_related_cache()

        self.message_user(
            request,
            f"{updated_count} item(s) activated successfully.",
            level=messages.SUCCESS,
        )

    activate_selected_items.short_description = "Activate selected items"

    def deactivate_selected_items(self, request, queryset):
        updated_count = queryset.update(is_active=False)

        if hasattr(self, "clear_related_cache"):
            self.clear_related_cache()

        self.message_user(
            request,
            f"{updated_count} item(s) deactivated successfully.",
            level=messages.SUCCESS,
        )

    deactivate_selected_items.short_description = "Deactivate selected items"