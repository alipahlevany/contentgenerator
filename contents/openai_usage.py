"""Read organization usage without mixing it with application usage estimates.

Official contract:
https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/completions
No generation calls, credentials, raw API errors, or per-user identifiers leave here.
"""
from datetime import datetime, timedelta, timezone as dt_timezone
import hashlib
import json
import time

import httpx
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables


USAGE_URL = "https://api.openai.com/v1/organization/usage/completions"
CACHE_SECONDS = 300
FAILURE_CACHE_SECONDS = 60
LAST_SUCCESS_SECONDS = 86400
FETCH_BUDGET_SECONDS = 8
MAX_PAGES = 8
UTC = dt_timezone.utc


class UsageUnavailable(Exception):
    def __init__(self, status="unavailable"):
        self.status = status


def _count(value):
    if type(value) is not int or value < 0:
        raise UsageUnavailable()
    return value


@sensitive_variables("admin_key")
def _fetch_usage(admin_key, project_ids, start, end):
    params = {"start_time": int(start.timestamp()), "end_time": int(end.timestamp()),
              "bucket_width": "1d", "limit": 31}
    if project_ids:
        params["project_ids[]"] = list(project_ids)
    totals = {"input": 0, "output": 0, "cached": 0, "requests": 0, "tokens": 0}
    today_tokens = 0
    seen_pages, seen_buckets = set(), set()
    deadline = time.monotonic() + FETCH_BUDGET_SECONDS
    # Never follow redirects with the organization credential; no automatic retries.
    with httpx.Client(headers={"Authorization": f"Bearer {admin_key}", "Accept": "application/json"},
                      follow_redirects=False) as client:
        for _ in range(MAX_PAGES):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise UsageUnavailable()
            response = client.get(USAGE_URL, params=params, timeout=min(3.0, remaining))
            if response.status_code in (401, 403):
                raise UsageUnavailable("access_denied")
            if response.status_code == 429:
                raise UsageUnavailable("rate_limited")
            if response.status_code != 200:
                raise UsageUnavailable()
            page = response.json()
            if not isinstance(page, dict) or not isinstance(page.get("data"), list):
                raise UsageUnavailable()
            for bucket in page["data"]:
                if not isinstance(bucket, dict) or not isinstance(bucket.get("results"), list):
                    raise UsageUnavailable()
                timestamp = _count(bucket.get("start_time"))
                if timestamp in seen_buckets or not params["start_time"] <= timestamp < params["end_time"]:
                    raise UsageUnavailable()
                seen_buckets.add(timestamp)
                day = datetime.fromtimestamp(timestamp, UTC).date()
                for result in bucket["results"]:
                    if not isinstance(result, dict) or result.get("object") != "organization.usage.completions.result":
                        raise UsageUnavailable()
                    cached = result.get("input_cached_tokens")
                    counts = {
                        "input": _count(result.get("input_tokens")),
                        "output": _count(result.get("output_tokens")),
                        "cached": _count(0 if cached is None else cached),
                        "requests": _count(result.get("num_model_requests")),
                    }
                    # input_tokens already includes cache reads and writes.
                    counts["tokens"] = counts["input"] + counts["output"]
                    if counts["cached"] > counts["input"]:
                        raise UsageUnavailable()
                    for field, value in counts.items():
                        totals[field] += value
                    if day == end.date():
                        today_tokens += counts["tokens"]
            if page.get("has_more") is False:
                return {"totals": totals, "today_tokens": today_tokens}
            cursor = page.get("next_page")
            if page.get("has_more") is not True or not isinstance(cursor, str) or not cursor or cursor in seen_pages:
                raise UsageUnavailable()
            seen_pages.add(cursor)
            params["page"] = cursor
    # Never publish a partial total when pagination could not be completed.
    raise UsageUnavailable()


@sensitive_variables("admin_key")
def get_openai_usage(days=7):
    days = 30 if str(days) == "30" else 7
    now = timezone.now().astimezone(UTC).replace(microsecond=0)
    start = now.replace(hour=0, minute=0, second=0) - timedelta(days=days - 1)
    admin_key = settings.OPENAI_ADMIN_KEY
    project_ids = tuple(sorted(set(settings.OPENAI_USAGE_PROJECT_IDS)))
    base = {
        "source": "OpenAI Usage API", "period_days": days, "timezone": "UTC",
        "scope": "selected_projects" if project_ids else "organization",
        "project_count": len(project_ids), "start_date": start.date().isoformat(),
        "end_date": now.date().isoformat(), "totals": None, "today_tokens": None,
        "fetched_at": None, "through_at": None, "refresh_seconds": CACHE_SECONDS,
    }
    if not admin_key:
        return {**base, "status": "not_configured"}
    # A changed credential, project scope, period, or UTC day must not reuse totals.
    identity = hashlib.sha256(json.dumps([admin_key, project_ids]).encode()).hexdigest()[:24]
    key = f"openai_usage_v1:{identity}:{now.date().isoformat()}:{days}"
    saved = cache.get(key)
    if saved is not None:
        return saved
    last = cache.get(key + ":last")
    if not cache.add(key + ":lock", True, timeout=30):
        return {**(last or base), "status": "stale" if last else "loading"}
    try:
        try:
            result = _fetch_usage(admin_key, project_ids, start, now)
        except (UsageUnavailable, httpx.HTTPError, ValueError, OverflowError) as error:
            status = error.status if isinstance(error, UsageUnavailable) else "unavailable"
            # Authorization failure must not keep exposing a revoked credential's cache.
            if status == "access_denied":
                cache.delete(key + ":last")
                last = None
            result = {**(last or base), "status": "stale" if last else status}
            cache.set(key, result, FAILURE_CACHE_SECONDS)
            return result
        result = {**base, **result, "status": "ready", "fetched_at": timezone.now().isoformat(),
                  "through_at": now.isoformat()}
        cache.set(key + ":last", result, LAST_SUCCESS_SECONDS)
        cache.set(key, result, CACHE_SECONDS)
        return result
    finally:
        cache.delete(key + ":lock")
