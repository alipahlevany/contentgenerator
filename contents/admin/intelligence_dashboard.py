from django.db.models import Count, Q, Sum
from django.core.cache import cache
from django.db import DatabaseError
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone
from datetime import datetime, time, timedelta

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
        return ExternalClient.objects.filter(is_active=True).aggregate(
            standard=Count("pk", filter=Q(receives_standard_content=True)),
            reply=Count("pk", filter=Q(receives_email_replies=True)),
            greeting=Count("pk", filter=Q(receives_greetings=True)),
        )
    except DatabaseError:
        # Keep the dashboard available during rolling deployments before the
        # delivery-preference migration has reached the database.
        return {"standard": 0, "reply": 0, "greeting": 0}


def get_dashboard_metrics():
    today = timezone.localdate()
    start_date = today - timedelta(days=6)
    start_at = timezone.make_aware(datetime.combine(start_date, time.min))
    end_at = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min))

    # Compare the indexed timestamp directly. Casting every row to a date
    # forces a table scan even when only the current week is needed.
    daily_rows = list(
        Content.objects.filter(created_at__gte=start_at, created_at__lt=end_at)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"), greetings=Count("id", filter=Q(content_type="greeting")))
    )
    daily = {
        row["day"].isoformat(): row["count"]
        for row in daily_rows
    }

    greeting_daily = {
        row["day"].isoformat(): row["greetings"]
        for row in daily_rows
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
    greeting_weekly_total = sum(greeting_daily.values())
    content_by_type = list(
        Content.objects.values("content_type").annotate(count=Count("id"))
        .order_by("content_type")
    )

    return {
        "content_total": sum(row["count"] for row in content_by_type),
        "content_today": daily.get(today.isoformat(), 0),
        "content_this_week": weekly_total,
        "greeting_total": sum(row["count"] for row in content_by_type if row["content_type"] == "greeting"),
        "greeting_today": greeting_daily.get(today.isoformat(), 0),
        "greetings_this_week": greeting_weekly_total,
        "daily_average": round(weekly_total / 7, 1),
        "total_jobs": sum(job_status_counts.values()),
        "running_jobs": job_status_counts.get("running", 0),
        "failed_jobs": job_status_counts.get("failed", 0),
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
        "content_by_type": content_by_type,
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
        "daily_greeting_counts": [
            greeting_daily.get(
                (start_date + timedelta(days=offset)).isoformat(),
                0,
            )
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
    context = {
        **get_intelligence_context(),
        "dashboard_metrics": cache.get_or_set(
            "operations_dashboard_metrics_v1", get_dashboard_metrics, timeout=15,
        ),
    }

    if extra_context:
        context.update(extra_context)

    return render(
        request,
        "dashboard/index.html",
        context,
    )
