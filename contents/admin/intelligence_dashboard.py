from django.contrib import admin
from django.template.response import TemplateResponse

from contents.core_services.analyzer import (
    get_best_dataset_items,
    get_best_generation_patterns,
    get_dataset_health,
    get_worst_dataset_items,
    get_worst_generation_patterns,
)


def get_intelligence_context():
    return {
        "health": get_dataset_health(),
        "best_items": get_best_dataset_items(limit=5),
        "worst_items": get_worst_dataset_items(limit=5),
        "best_patterns": get_best_generation_patterns(limit=5),
        "worst_patterns": get_worst_generation_patterns(limit=5),
    }


def custom_admin_index(request, extra_context=None):
    app_list = admin.site.get_app_list(request)

    context = {
        **admin.site.each_context(request),
        "title": "AI Content Dashboard",
        "app_list": app_list,
        **get_intelligence_context(),
    }

    if extra_context:
        context.update(extra_context)

    request.current_app = admin.site.name

    return TemplateResponse(
        request,
        "admin/custom_index.html",
        context,
    )