"""Small, shared progress records for manual template batches; HTML stays in SQL."""
import math
import re
import time
import uuid

from django.core.cache import cache
from django.utils import timezone

from contents.models import Content


BATCH_TTL = 86400
COOLDOWN_SECONDS = 300
COOLDOWN_KEY = "warmup-template-manual-run-cooldown"
LATEST_KEY = "warmup-template-latest-manual-batch"
BATCH_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}-manual-[a-f0-9]{10}\Z")


def batch_cache_key(batch_key):
    return f"warmup-template-batch:{batch_key}"


def get_manual_batch(batch_key):
    if not isinstance(batch_key, str) or not BATCH_PATTERN.fullmatch(batch_key):
        return None
    return cache.get(batch_cache_key(batch_key))


def cooldown_remaining():
    value = cache.get(COOLDOWN_KEY)
    if isinstance(value, dict):
        return max(0, math.ceil(value["expires_at"] - time.time()))
    return COOLDOWN_SECONDS if value else 0


def release_batch_cooldown(batch_key):
    value = cache.get(COOLDOWN_KEY)
    if isinstance(value, dict) and value.get("batch_key") == batch_key:
        cache.delete(COOLDOWN_KEY)


def create_manual_batch(config):
    """Snapshot the saved count/delay and atomically reject repeated clicks."""
    day = timezone.localdate().isoformat()
    batch_key = f"{day}-manual-{uuid.uuid4().hex[:10]}"
    count, delay = config.daily_warmup_template_count, config.daily_warmup_template_delay_seconds
    if not 1 <= count <= 50 or not math.isfinite(delay) or delay < 0:
        raise ValueError("Template count or delay is outside its allowed range.")
    now = time.time()
    if not cache.add(COOLDOWN_KEY, {"batch_key": batch_key, "expires_at": now + COOLDOWN_SECONDS}, timeout=COOLDOWN_SECONDS):
        return None
    batch = {"batch_key": batch_key, "run_date": day, "count": count, "delay": delay,
             "created_at": now, "phase": "queued", "accepted": 0, "error": ""}
    try:
        cache.set(batch_cache_key(batch_key), batch, timeout=BATCH_TTL)
        cache.set(LATEST_KEY, batch_key, timeout=BATCH_TTL)
    except Exception:
        release_batch_cooldown(batch_key)
        raise
    return batch


def record_batch_dispatch(batch_key, accepted, error=""):
    batch = get_manual_batch(batch_key)
    if batch is None:
        return
    batch.update(phase="failed" if error else "dispatched", accepted=accepted, error=error)
    cache.set(batch_cache_key(batch_key), batch, timeout=BATCH_TTL)
    if error and not accepted:
        release_batch_cooldown(batch_key)


def record_template_progress(batch_key, sequence, state, error=""):
    batch = get_manual_batch(batch_key)
    if batch is not None and 0 <= sequence < batch["count"]:
        # Each slot owns a key, so simultaneous workers cannot overwrite one another.
        cache.set(f"{batch_cache_key(batch_key)}:slot:{sequence}",
                  {"state": state, "error": error}, timeout=BATCH_TTL)


def manual_batch_progress(batch_key):
    batch = get_manual_batch(batch_key)
    if batch is None:
        return None
    count = batch["count"]
    titles = {f"Warmup Template {batch_key} #{i + 1:03d}": i for i in range(count)}
    saved = list(Content.objects.filter(content_type="warmup_template", title__in=titles)
                 .values("id", "title").order_by("title"))
    completed = {titles[row["title"]] for row in saved}
    keys = {i: f"{batch_cache_key(batch_key)}:slot:{i}" for i in range(count)}
    slots = cache.get_many(keys.values())
    failed = {i for i, key in keys.items() if slots.get(key, {}).get("state") == "failed"} - completed
    if batch["phase"] == "failed":
        failed.update(set(range(batch["accepted"], count)) - completed)
    pending = count - len(completed) - len(failed)
    errors = list(dict.fromkeys(
        slots[keys[i]].get("error") for i in sorted(failed)
        if keys[i] in slots and slots[keys[i]].get("error")
    ))
    if batch["error"]:
        errors.insert(0, batch["error"])
    if len(completed) == count:
        state = "complete"
        message = f"{count} template{'s' if count != 1 else ''} ready. Open a preview or download the HTML below."
    elif pending == 0:
        state = "partial" if completed else "failed"
        message = f"{len(completed)} of {count} templates ready; {len(failed)} could not be created."
    elif time.time() - batch["created_at"] > 180 + (count - 1) * batch["delay"]:
        state = "delayed"
        message = "Taking longer than expected. Progress updates continue; you do not need to submit again."
    elif batch["phase"] == "queued" and not completed:
        state = "queued"
        message = "Your request is queued. Results will appear here automatically."
    else:
        state = "generating"
        message = f"Creating templates: {len(completed)} of {count} ready."
    return {"batch_key": batch_key, "state": state, "message": message, "total": count,
            "ready": len(completed), "failed": len(failed), "pending": pending,
            "terminal": not pending, "errors": errors,
            "results": [{"id": row["id"], "number": titles[row["title"]] + 1} for row in saved]}
