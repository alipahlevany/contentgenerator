from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db import DatabaseError
from django.db.models import Count, Min, Q, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone

from contents.models import AIUsageLog, AppSettings, Content, ContentDelivery, ExternalClient, GenerationJob


# OpenAI Standard text rates, checked 2026-11-01:
# https://developers.openai.com/api/docs/models/gpt-6-luna
# Unknown models deliberately show no dollar estimate.
TOKEN_RATES = {"gpt-6-luna": (Decimal("0.10"), Decimal("0.01"), Decimal("0.50"))}
DASHBOARD_CACHE_SECONDS = 30


def dashboard_period(value):
    try:
        days = int(value)
    except (TypeError, ValueError):
        return 7
    return days if days in (7, 30) else 7


def get_recipient_counts():
    try:
        return ExternalClient.objects.filter(is_active=True).aggregate(
            standard=Count("pk", filter=Q(receives_standard_content=True)),
            reply=Count("pk", filter=Q(receives_email_replies=True)),
            greeting=Count("pk", filter=Q(receives_greetings=True)),
        )
    except DatabaseError:
        return {"standard": 0, "reply": 0, "greeting": 0}


def _rate(generated, skipped):
    total = generated + skipped
    return round(generated * 100 / total, 1) if total else None


def get_dashboard_metrics(days=7):
    days = dashboard_period(days)
    today = timezone.localdate()
    start_date = today - timedelta(days=days - 1)
    start_at = timezone.make_aware(datetime.combine(start_date, time.min))
    end_at = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min))
    period = Q(created_at__gte=start_at, created_at__lt=end_at)
    greeting_period = period & Q(generation_type="greeting")
    labels = [(start_date + timedelta(days=i)).isoformat() for i in range(days)]
    daily_rows = list(
        Content.objects.filter(period).annotate(day=TruncDate("created_at"))
        .values("day").annotate(count=Count("pk"), greetings=Count("pk", filter=Q(content_type="greeting")))
    )
    daily = {row["day"].isoformat(): row for row in daily_rows}
    content_by_type = list(Content.objects.values("content_type").annotate(count=Count("pk")).order_by("content_type"))
    jobs = GenerationJob.objects.aggregate(
        total=Count("pk"), running=Count("pk", filter=Q(status="running")),
        pending=Count("pk", filter=Q(status="pending")),
        completed=Count("pk", filter=Q(status="completed")),
        failed=Count("pk", filter=Q(status="failed") & period),
        generated=Sum("generated_count"), skipped=Sum("skipped_count"),
        greeting_generated=Sum("generated_count", filter=greeting_period),
        greeting_skipped=Sum("skipped_count", filter=greeting_period),
        greeting_duplicates=Sum("duplicate_count", filter=greeting_period),
        greeting_invalid=Sum("failed_count", filter=greeting_period),
    )
    recent_jobs = list(GenerationJob.objects.order_by("-pk").values(
        "id", "generation_type", "status", "count", "generated_count", "skipped_count", "created_at", "updated_at",
    )[:8])
    latest_greeting = GenerationJob.objects.filter(generation_type="greeting").order_by("-pk").values(
        "id", "status", "count", "generated_count", "skipped_count", "duplicate_count", "created_at",
    ).first()
    if latest_greeting:
        latest_greeting["acceptance"] = _rate(latest_greeting["generated_count"], latest_greeting["skipped_count"])
        latest_greeting["progress"] = min(100, round(latest_greeting["generated_count"] * 100 / max(latest_greeting["count"], 1)))
    deliveries = ContentDelivery.objects.aggregate(
        total=Count("pk"), success=Count("pk", filter=Q(status="success")),
        failed=Count("pk", filter=Q(status="failed", updated_at__gte=start_at)),
        pending=Count("pk", filter=Q(status__in=["pending", "processing"])),
    )
    recipients = get_recipient_counts()
    usage_rows = list(AIUsageLog.objects.filter(period).annotate(day=TruncDate("created_at"))
        .values("day", "generation_type", "model_name", "provider").annotate(
            requests=Count("pk"), input=Sum("input_tokens"), cached=Sum("cached_input_tokens"),
            output=Sum("output_tokens"), first_seen=Min("created_at"),
        ).order_by("day"))
    usage = {"requests": 0, "input": 0, "cached": 0, "output": 0, "unpriced_requests": 0, "first_seen": None}
    cost = Decimal(0)
    usage_by_type = {}
    usage_by_day = {}
    for row in usage_rows:
        kind = row["generation_type"] or "other"
        item = usage_by_type.setdefault(kind, {"type": kind, "requests": 0, "tokens": 0})
        for key in ("requests", "input", "cached", "output"):
            usage[key] += row[key] or 0
        item["requests"] += row["requests"]
        item["tokens"] += row["input"] + row["output"]
        day = row["day"].isoformat()
        usage_by_day[day] = usage_by_day.get(day, 0) + row["input"] + row["output"]
        if usage["first_seen"] is None or row["first_seen"] < usage["first_seen"]:
            usage["first_seen"] = row["first_seen"]
        rates = TOKEN_RATES.get(row["model_name"]) if row["provider"] == "openai" else None
        if rates:
            cached = min(row["cached"] or 0, row["input"])
            cost += ((row["input"] - cached) * rates[0] + cached * rates[1] + row["output"] * rates[2]) / 1_000_000
        else:
            usage["unpriced_requests"] += row["requests"]
    usage["tokens"] = usage["input"] + usage["output"]
    usage["estimated_cost"] = float(cost) if usage["requests"] and not usage["unpriced_requests"] else None
    usage["by_type"] = list(usage_by_type.values())
    usage["daily_tokens"] = [usage_by_day.get(day, 0) for day in labels]
    settings = AppSettings.objects.filter(is_active=True).order_by("-pk").values(
        "model_name", "daily_greeting_generation_count", "auto_daily_greeting_generation_enabled",
    ).first() or {}
    samples = list(Content.objects.filter(content_type="greeting", status="generated").order_by("-pk").values(
        "id", "generated_content", "language__name", "language__code", "created_at",
    )[:12])
    failed_jobs = list(GenerationJob.objects.filter(period, status="failed").order_by("-updated_at").values(
        "id", "generation_type", "updated_at",
    )[:3])
    failed_deliveries = list(ContentDelivery.objects.filter(status="failed", updated_at__gte=start_at)
        .order_by("-updated_at").values("id", "client__name", "updated_at")[:3])
    total = sum(row["count"] for row in content_by_type)
    period_total = sum(row["count"] for row in daily_rows)
    greeting_total = sum(row["count"] for row in content_by_type if row["content_type"] == "greeting")
    greeting_period_total = sum(row["greetings"] for row in daily_rows)
    today_row = daily.get(today.isoformat(), {})
    greeting_today = today_row.get("greetings", 0)
    target = settings.get("daily_greeting_generation_count") or 0
    generated, skipped = jobs["generated"] or 0, jobs["skipped"] or 0
    greeting_generated, greeting_skipped = jobs["greeting_generated"] or 0, jobs["greeting_skipped"] or 0
    return {
        "period_days": days, "reporting_timezone": timezone.get_current_timezone_name(),
        "updated_at": timezone.now(), "start_date": start_date.isoformat(), "today": today.isoformat(),
        "content_total": total, "content_today": today_row.get("count", 0),
        "content_this_week": period_total, "greeting_total": greeting_total,
        "greeting_today": greeting_today, "greetings_this_week": greeting_period_total,
        "daily_average": round(period_total / days, 1), "content_by_type": content_by_type,
        "total_jobs": jobs["total"], "running_jobs": jobs["running"], "pending_jobs": jobs["pending"],
        "completed_jobs": jobs["completed"], "failed_jobs": jobs["failed"],
        "generated_total": generated, "skipped_total": skipped,
        "success_rate": _rate(generated, skipped) or 0,
        "skip_rate": round(skipped * 100 / (generated + skipped), 1) if generated + skipped else 0,
        "greeting_success_rate": _rate(greeting_generated, greeting_skipped),
        "greeting_skipped": greeting_skipped, "greeting_duplicates": jobs["greeting_duplicates"] or 0,
        "greeting_invalid": jobs["greeting_invalid"] or 0,
        "greeting_target": target, "greeting_schedule_enabled": settings.get("auto_daily_greeting_generation_enabled", False),
        "greeting_target_progress": min(100, round(greeting_today * 100 / target)) if target else 0,
        "model_name": settings.get("model_name", "Not configured"),
        "latest_greeting": latest_greeting, "greeting_samples": samples,
        "delivery_total": deliveries["total"], "delivery_pending": deliveries["pending"],
        "delivery_success_rate": round(deliveries["success"] * 100 / deliveries["total"], 1) if deliveries["total"] else None,
        "attention_total": jobs["failed"] + deliveries["failed"],
        "recipient_counts": recipients, "recipient_total": sum(recipients.values()),
        "recent_jobs": recent_jobs, "recent_failed_jobs": failed_jobs, "recent_failed_deliveries": failed_deliveries,
        "daily_labels": labels, "daily_counts": [daily.get(day, {}).get("count", 0) for day in labels],
        "daily_greeting_counts": [daily.get(day, {}).get("greetings", 0) for day in labels],
        "usage": usage,
    }


def cached_dashboard_metrics(days=7):
    days = dashboard_period(days)
    key = f"operations_dashboard_metrics_v3:{timezone.get_current_timezone_name()}:{days}"
    return cache.get_or_set(key, lambda: get_dashboard_metrics(days), timeout=DASHBOARD_CACHE_SECONDS)


def custom_admin_index(request, extra_context=None):
    context = {"dashboard_metrics": cached_dashboard_metrics(request.GET.get("days", 7))}
    if extra_context:
        context.update(extra_context)
    return render(request, "dashboard/index.html", context)
