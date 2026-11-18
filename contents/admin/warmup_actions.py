"""Shared display state for the template generation buttons."""
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from contents.core_services.warmup_templates import photo_source_status
from contents.core_services.warmup_runs import LATEST_KEY, cooldown_remaining, manual_batch_progress
from contents.models import WarmupTemplate, WarmupTemplateGenerationSettings


def batch_payload(batch_key):
    progress = manual_batch_progress(batch_key)
    if progress is None:
        return None
    progress["cooldown_seconds"] = cooldown_remaining()
    progress["status_url"] = reverse("admin:contents_warmuptemplategenerationsettings_status") + "?batch=" + batch_key
    for result in progress["results"]:
        result["preview_url"] = reverse("admin:contents_warmuptemplate_change", args=(result["id"],)) + "#warmup-preview"
        result["download_url"] = reverse("admin:contents_warmuptemplate_download", args=(result["id"],))
    if progress["terminal"]:
        templates = WarmupTemplate.objects.filter(content_type="warmup_template")
        latest = templates.order_by("-id").values_list("pk", flat=True).first()
        progress["summary"] = {
            "today_count": templates.filter(created_at__date=timezone.localdate()).count(),
            "latest_url": reverse("admin:contents_warmuptemplate_change", args=(latest,)) + "#warmup-preview" if latest else "",
        }
    return progress


def template_generation_action(request, admin_site, return_to):
    active = WarmupTemplateGenerationSettings.objects.filter(is_active=True).order_by("-id").first()
    settings_admin = admin_site._registry[WarmupTemplateGenerationSettings]
    can_generate = settings_admin.has_change_permission(request)
    source = photo_source_status()
    error = ""
    if not active:
        error = "Save active generation settings before generating templates."
    elif not source["ready"]:
        error = source["error"]
    remaining = cooldown_remaining()
    batch_key = request.GET.get("batch") or cache.get(LATEST_KEY)
    progress = batch_payload(batch_key) if batch_key and settings_admin.has_view_or_change_permission(request) else None
    return {
        "url": reverse("admin:contents_warmuptemplategenerationsettings_run_now"),
        "settings_url": reverse("admin:contents_warmuptemplategenerationsettings_change", args=(active.pk,))
        if active else reverse("admin:contents_warmuptemplategenerationsettings_changelist"),
        "templates_url": reverse("admin:contents_warmuptemplate_changelist"),
        "count": active.daily_warmup_template_count if active else None,
        "schedule_enabled": bool(active and active.auto_daily_warmup_template_enabled),
        "can_generate": can_generate,
        "error": error,
        "cooldown_seconds": remaining,
        "disabled": bool(error or remaining),
        "progress": progress,
        "return_to": return_to,
    }
