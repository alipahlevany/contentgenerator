"""Local-only administration and safe previews for generated email templates."""

import hashlib
import re
from datetime import date

from django import forms
from django.conf import settings
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.views.decorators.clickjacking import xframe_options_sameorigin

from contents.core_services.warmup_template_renderer import (
    CONTENT_TOKEN,
    LAYOUT_NAMES,
    UNSUBSCRIBE_TOKEN,
    WarmupTemplateError,
    render_warmup_html,
    validate_warmup_html,
)
from contents.models import WarmupTemplate

from .content import BaseContentAdmin
from .warmup_actions import template_generation_action


# Stable public example; metadata verified at https://picsum.photos/id/1018/info.
SAMPLE_PHOTO = {
    "image_url": "https://picsum.photos/id/1018/1200/800.jpg",
    "photo_page": "https://unsplash.com/photos/Kt5hRENuotI",
    "photographer": "Andrew Ridley",
    "credit_source": "Unsplash via Picsum",
    "alt": "Photo by Andrew Ridley",
}


class WarmupTemplateAdminForm(forms.ModelForm):
    class Meta:
        model = WarmupTemplate
        fields = "__all__"

    def clean_generated_content(self):
        try:
            return validate_warmup_html(self.cleaned_data["generated_content"])
        except WarmupTemplateError as exc:
            raise forms.ValidationError(str(exc)) from exc


@admin.register(WarmupTemplate)
class WarmupTemplateAdmin(BaseContentAdmin):
    content_type_value = "warmup_template"
    form = WarmupTemplateAdminForm
    change_form_template = "admin/contents/warmuptemplate/change_form.html"
    change_list_template = "admin/contents/warmuptemplate/change_list.html"
    list_display = ("id", "title", "preview_link", "status", "created_at")
    list_display_links = ("id", "title")
    list_filter = ("status", "created_at")
    search_fields = ("title", "generated_content", "content_hash")
    filter_horizontal = ()
    readonly_fields = ("content_hash", "created_at", "updated_at")
    fieldsets = (
        ("Generated HTML", {"fields": ("title", "generated_content", "content_hash", "status")}),
        ("Generation", {"fields": ("prompt", "created_at", "updated_at")}),
    )

    class Media:
        css = {"all": (f"{settings.STATIC_URL}admin/warmup_template.css?v=20261117-progress",)}
        js = (f"{settings.STATIC_URL}admin/warmup_generation.js?v=20261117-buttons",)

    def get_changelist_instance(self, request):
        # This is UI progress state, not a Django model-list filter.
        request.GET = request.GET.copy()
        request.GET.pop("batch", None)
        return super().get_changelist_instance(request)

    def has_add_permission(self, request):
        return False

    def changelist_view(self, request, extra_context=None):
        context = dict(extra_context or {})
        context["warmup_action"] = template_generation_action(request, self.admin_site, "templates")
        return super().changelist_view(request, extra_context=context)

    @admin.display(description="Preview")
    def preview_link(self, obj):
        url = reverse("admin:contents_warmuptemplate_change", args=(obj.pk,))
        return format_html('<a href="{}#warmup-preview">Open preview</a>', url)

    def get_urls(self):
        custom = [
            path(
                "sample/",
                self.admin_site.admin_view(self.sample_view),
                name="contents_warmuptemplate_sample",
            ),
            path(
                "sample/<int:variation>/frame/",
                self.admin_site.admin_view(self.sample_frame_view),
                name="contents_warmuptemplate_sample_frame",
            ),
            path(
                "<int:object_id>/preview-frame/",
                self.admin_site.admin_view(self.preview_frame_view),
                name="contents_warmuptemplate_preview_frame",
            ),
            path(
                "<int:object_id>/download/",
                self.admin_site.admin_view(self.download_view),
                name="contents_warmuptemplate_download",
            ),
        ]
        return custom + super().get_urls()

    def _get_template(self, request, object_id):
        obj = get_object_or_404(self.get_queryset(request), pk=object_id)
        if not self.has_view_or_change_permission(request, obj):
            raise PermissionDenied
        return obj

    def _preview_response(self, markup):
        sample = (
            "Your existing email content will appear here. "
            "This text is shown only in the preview."
        )
        # Older local samples used a URL slot; keep their preview readable.
        markup = re.sub(r'href=([\"\'])\{\{unsubscribe\}\}\1', 'href="#"', markup)
        markup = markup.replace(CONTENT_TOKEN, sample).replace(
            UNSUBSCRIBE_TOKEN, '<span style="text-decoration:underline;">Unsubscribe (preview)</span>'
        )
        response = HttpResponse(markup, content_type="text/html; charset=utf-8")
        response["Content-Security-Policy"] = (
            "default-src 'none'; img-src https://images.pexels.com "
            "https://picsum.photos https://fastly.picsum.photos; "
            "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; "
            "frame-ancestors 'self'"
        )
        return response

    @xframe_options_sameorigin
    def preview_frame_view(self, request, object_id):
        obj = self._get_template(request, object_id)
        return self._preview_response(obj.generated_content)

    def sample_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied
        try:
            variation = int(request.GET.get("layout", 0))
        except (TypeError, ValueError):
            variation = 0
        if variation not in range(len(LAYOUT_NAMES)):
            variation = 0
        sample_url = reverse("admin:contents_warmuptemplate_sample")
        return render(request, "admin/contents/warmuptemplate/sample.html", {
            **self.admin_site.each_context(request),
            "title": "Warmup template design samples",
            "variation": variation,
            "design_name": LAYOUT_NAMES[variation],
            "design_count": len(LAYOUT_NAMES),
            "frame_url": reverse(
                "admin:contents_warmuptemplate_sample_frame", args=(variation,)
            ),
            "designs": [
                {"label": name, "url": f"{sample_url}?layout={index}", "active": index == variation}
                for index, name in enumerate(LAYOUT_NAMES)
            ],
        })

    @xframe_options_sameorigin
    def sample_frame_view(self, request, variation):
        if not self.has_view_permission(request):
            raise PermissionDenied
        if variation not in range(len(LAYOUT_NAMES)):
            raise PermissionDenied
        sample_date = date(2026, 11, 16)
        sequence = (variation - sample_date.toordinal()) % len(LAYOUT_NAMES)
        markup = render_warmup_html(
            SAMPLE_PHOTO, sample_date, sequence,
            settings.WARMUP_TEMPLATE_LINK_URL,
        )
        return self._preview_response(markup)

    def download_view(self, request, object_id):
        obj = self._get_template(request, object_id)
        response = HttpResponse(
            obj.generated_content,
            content_type="application/octet-stream",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="warmup-template-{obj.pk}.html"'
        )
        return response

    def render_change_form(self, request, context, *args, **kwargs):
        obj = context.get("original")
        if obj:
            context["warmup_preview_url"] = reverse(
                "admin:contents_warmuptemplate_preview_frame", args=(obj.pk,)
            )
            context["warmup_download_url"] = reverse(
                "admin:contents_warmuptemplate_download", args=(obj.pk,)
            )
        return super().render_change_form(request, context, *args, **kwargs)

    def save_model(self, request, obj, form, change):
        obj.content_hash = hashlib.sha256(
            obj.generated_content.encode("utf-8")
        ).hexdigest()
        super().save_model(request, obj, form, change)
