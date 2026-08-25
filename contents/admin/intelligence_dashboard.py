from django.contrib import admin
from django.db.models import Count, Sum
from django.db import DatabaseError
from django.db.models.functions import TruncDate
from django.template.response import TemplateResponse
from django.utils import timezone
from datetime import timedelta

from contents.core_services.analyzer import (
    get_best_dataset_items,
    get_best_generation_patterns,
    get_dataset_health,
    get_worst_dataset_items,
    get_worst_generation_patterns,
)
from contents.models import Content, ContentDelivery, ExternalClient, GenerationJob


def get_recipient_counts():
    try:
        return {
            "standard": ExternalClient.objects.filter(is_active=True, receives_standard_content=True).count(),
            "reply": ExternalClient.objects.filter(is_active=True, receives_email_replies=True).count(),
            "greeting": ExternalClient.objects.filter(is_active=True, receives_greetings=True).count(),
        }
    except DatabaseError:
        # Keep the dashboard available during rolling deployments before the
        # delivery-preference migration has reached the database.
        return {"standard": 0, "reply": 0, "greeting": 0}


def get_dashboard_metrics():
    today = timezone.localdate()
    start_date = today - timedelta(days=6)

    daily = {
        row["day"].isoformat(): row["count"]
        for row in (
            Content.objects
            .filter(created_at__date__gte=start_date)
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(count=Count("id"))
        )
    }

    job_totals = GenerationJob.objects.aggregate(
        generated=Sum("generated_count"),
        skipped=Sum("skipped_count"),
        failed=Sum("failed_count"),
    )
    generated = job_totals["generated"] or 0
    skipped = job_totals["skipped"] or 0
    failed = job_totals["failed"] or 0
    total_outcomes = generated + skipped

    job_status_counts = {
        row["status"]: row["count"]
        for row in GenerationJob.objects.values("status").annotate(
            count=Count("id")
        )
    }
    delivery_status_counts = {
        row["status"]: row["count"]
        for row in ContentDelivery.objects.values("status").annotate(
            count=Count("id")
        )
    }
    delivery_total = sum(delivery_status_counts.values())
    delivery_successes = delivery_status_counts.get("success", 0)
    recipient_counts = get_recipient_counts()
    weekly_total = sum(daily.values())

    return {
        "content_total": Content.objects.count(),
        "content_today": Content.objects.filter(created_at__date=today).count(),
        "content_this_week": weekly_total,
        "daily_average": round(weekly_total / 7, 1),
        "total_jobs": sum(job_status_counts.values()),
        "running_jobs": GenerationJob.objects.filter(status="running").count(),
        "failed_jobs": GenerationJob.objects.filter(status="failed").count(),
        "completed_jobs": job_status_counts.get("completed", 0),
        "generated_total": generated,
        "skipped_total": skipped,
        "failed_total": failed,
        "success_rate": round((generated / total_outcomes) * 100, 1) if total_outcomes else 0,
        "skip_rate": round((skipped / total_outcomes) * 100, 1) if total_outcomes else 0,
        "delivery_total": delivery_total,
        "delivery_success_rate": (
            round((delivery_successes / delivery_total) * 100, 1)
            if delivery_total
            else 0
        ),
        "recipient_counts": recipient_counts,
        "recipient_total": sum(recipient_counts.values()),
        "attention_total": (
            job_status_counts.get("failed", 0)
            + delivery_status_counts.get("failed", 0)
        ),
        "content_by_type": list(
            Content.objects.values("content_type")
            .annotate(count=Count("id"))
            .order_by("content_type")
        ),
        "content_by_status": list(
            Content.objects.values("status")
            .annotate(count=Count("id"))
            .order_by("status")
        ),
        "jobs_by_status": [
            {"status": status, "count": count}
            for status, count in sorted(job_status_counts.items())
        ],
        "deliveries_by_status": [
            {"status": status, "count": count}
            for status, count in sorted(delivery_status_counts.items())
        ],
        "recent_jobs": list(
            GenerationJob.objects.order_by("-created_at")[:8]
            .values("id", "generation_type", "status", "count", "generated_count", "skipped_count", "created_at")
        ),
        "recent_failed_jobs": list(
            GenerationJob.objects.filter(status="failed")
            .order_by("-updated_at")[:5]
            .values("id", "generation_type", "error_message", "updated_at")
        ),
        "recent_failed_deliveries": list(
            ContentDelivery.objects.filter(status="failed")
            .select_related("client", "content")
            .order_by("-updated_at")[:5]
            .values("id", "client__name", "content__content_type", "last_error", "updated_at")
        ),
        "daily_labels": [
            (start_date + timedelta(days=offset)).isoformat()
            for offset in range(7)
        ],
        "daily_counts": [
            daily.get((start_date + timedelta(days=offset)).isoformat(), 0)
            for offset in range(7)
        ],
    }


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
        "dashboard_metrics": get_dashboard_metrics(),
    }

    if extra_context:
        context.update(extra_context)

    request.current_app = admin.site.name

    return TemplateResponse(
        request,
        "admin/custom_index.html",
        context,
    )
