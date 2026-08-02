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

    model_lookup = {}

    for app in app_list:
        for model in app.get("models", []):
            model_lookup[model["object_name"]] = model

    section_specs = (
        {
            "key": "standard",
            "icon": "📝",
            "title": "Standard Generation",
            "description": (
                "Standard AI content generation and configuration."
            ),
            "models": (
                "Content",
                "StandardGenerationSettings",
            ),
        },
        {
            "key": "reply",
            "icon": "✉️",
            "title": "Email Reply",
            "description": (
                "Natural email reply generation and scheduling."
            ),
            "models": (
                "EmailReply",
                "ReplyGenerationSettings",
            ),
        },
        {
            "key": "greeting",
            "icon": "👋",
            "title": "Greeting",
            "description": (
                "Language-based greeting generation and scheduling."
            ),
            "models": (
                "Greeting",
                "GreetingGenerationSettings",
            ),
        },
        {
            "key": "shared",
            "icon": "⚙️",
            "title": "Shared Settings",
            "description": (
                "AI runtime, generation limits and dataset intelligence."
            ),
            "models": (
                "SharedGenerationSettings",
            ),
        },
    )

    generation_sections = []

    section_model_names = set()

    for spec in section_specs:
        models = []

        for model_name in spec["models"]:
            section_model_names.add(model_name)

            model = model_lookup.get(model_name)

            if model:
                models.append(model)

        generation_sections.append(
            {
                **spec,
                "models": models,
            }
        )

    other_app_list = []

    for app in app_list:
        models = [
            model
            for model in app.get("models", [])
            if model["object_name"]
            not in section_model_names
        ]

        if models:
            other_app_list.append(
                {
                    **app,
                    "models": models,
                }
            )

    context = {
        **admin.site.each_context(request),
        "title": "AI Content Dashboard",
        "app_list": app_list,
        "generation_sections": generation_sections,
        "other_app_list": other_app_list,
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