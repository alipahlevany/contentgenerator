"""Generate and save local warmup templates without storing photo files."""

import hashlib
import logging
import re
from datetime import timedelta

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from contents.core_services.warmup_template_renderer import (
    WarmupTemplateError,
    _has_host,
    render_warmup_html,
    validate_warmup_html,
    validate_destination_url,
)
from contents.models import Content, WarmupButtonRotation
from contents.core_services.warmup_buttons import BUTTON_BANK_VERSION, BUTTON_LABELS

logger = logging.getLogger(__name__)

PHOTO_THEMES = (
    "coffee and reading",
    "a calm workspace",
    "travel landscape",
    "books and creativity",
    "nature and sunlight",
    "architecture and design",
    "food and everyday life",
    "technology and work",
)
RECENT_PHOTO_CACHE_KEY = "warmup-template-recent-photo-usage-v2"

class WarmupTemplateInProgress(WarmupTemplateError):
    """Another worker is already generating this exact template slot."""


def photo_source_status():
    """Resolve the source without making network requests."""
    provider = settings.WARMUP_TEMPLATE_PHOTO_PROVIDER
    key_ready = bool((settings.PEXELS_API_KEY or "").strip())
    if provider == "auto":
        provider = "pexels" if key_ready else "picsum"
    error = ""
    if provider not in {"pexels", "picsum"}:
        error = "WARMUP_TEMPLATE_PHOTO_PROVIDER must be auto, pexels, or picsum."
    elif provider == "pexels" and not key_ready:
        error = "Configure PEXELS_API_KEY or select the Picsum photo source."
    return {
        "provider": provider,
        "label": {"pexels": "Pexels", "picsum": "Unsplash via Picsum"}.get(provider, provider),
        "ready": not error,
        "error": error,
    }


def _recent_photo_usage():
    cached = cache.get(RECENT_PHOTO_CACHE_KEY)
    if cached is not None:
        return cached
    since = timezone.now() - timedelta(days=45)
    prompts = (
        Content.objects.filter(content_type="warmup_template", created_at__gte=since)
        .values_list("prompt", "created_at")
        .iterator(chunk_size=500)
    )
    usage = {}
    for prompt, created_at in prompts:
        match = re.search(r"(Pexels|Picsum) photo ID: (\d+)", prompt or "")
        if match:
            key = f"{match.group(1).lower()}:{match.group(2)}"
            usage[key] = max(usage.get(key, 0), created_at.timestamp())
    cache.set(RECENT_PHOTO_CACHE_KEY, usage, timeout=300)
    return usage


def _recent_photo_ids(provider="pexels"):
    prefix = provider + ":"
    return {key[len(prefix):] for key in _recent_photo_usage() if key.startswith(prefix)}


def _get_remote_photo(index, run_date):
    source = photo_source_status()
    if not source["ready"]:
        raise WarmupTemplateError(source["error"])
    if source["provider"] == "picsum":
        return _get_picsum_photo(index, run_date)
    return _get_pexels_photo(index, run_date)


def _get_pexels_photo(index, run_date):
    api_key = getattr(settings, "PEXELS_API_KEY", "").strip()
    if not api_key:
        raise WarmupTemplateError("Configure PEXELS_API_KEY to use remote photos.")

    seed = int(hashlib.sha256(f"{run_date}:{index}".encode()).hexdigest()[:12], 16)
    theme = PHOTO_THEMES[(index + run_date.toordinal()) % len(PHOTO_THEMES)]
    recent_ids = _recent_photo_ids()
    page_numbers = tuple(dict.fromkeys((1 + seed % 40, 1 + (seed + 1) % 40, 1, 2)))[:3]
    for page in page_numbers:
        response = requests.get(
            "https://api.pexels.com/v1/search",
            params={
                "query": theme,
                "orientation": "landscape",
                "per_page": 10,
                "page": page,
            },
            headers={"Authorization": api_key},
            timeout=(5, 15),
        )
        if 400 <= response.status_code < 500 and response.status_code != 429:
            raise WarmupTemplateError(
                f"Pexels rejected the photo request (HTTP {response.status_code})."
            )
        response.raise_for_status()
        payload = response.json()
        photos = payload.get("photos") if isinstance(payload, dict) else None
        if not isinstance(photos, list) or not photos:
            continue
        rotated = photos[seed % len(photos):] + photos[:seed % len(photos)]
        for item in rotated:
            if not isinstance(item, dict):
                continue
            photo_id = item.get("id")
            if not photo_id or str(photo_id) in recent_ids:
                continue
            source = item.get("src") or {}
            if not isinstance(source, dict):
                continue
            image_url = source.get("large") or source.get("medium") or ""
            photo_page = item.get("url") or ""
            if not _has_host(image_url, "images.pexels.com") or not _has_host(
                photo_page, "www.pexels.com"
            ):
                continue
            if not cache.add(
                f"warmup-photo-reservation:pexels:{photo_id}", 1, timeout=3600
            ):
                continue
            photographer = str(item.get("photographer") or "Pexels")[:80]
            alt = str(item.get("alt") or f"Photo by {photographer} on Pexels")[:180]
            return {
                "id": str(photo_id),
                "provider": "pexels",
                "credit_source": "Pexels",
                "image_url": image_url,
                "photo_page": photo_page,
                "photographer": photographer,
                "alt": alt,
                "theme": theme,
            }
    raise WarmupTemplateError("No unused Pexels photo was found for this template.")


def _picsum_page(page):
    """Cache only small JSON metadata, never image files."""
    key = f"warmup-picsum-page-v1:{page}"
    items = cache.get(key)
    if items is not None:
        return items
    response = requests.get(
        "https://picsum.photos/v2/list",
        params={"page": page, "limit": 100},
        timeout=(5, 15),
    )
    response.raise_for_status()
    items = response.json()
    if not isinstance(items, list):
        raise WarmupTemplateError("Picsum returned invalid photo metadata.")
    cache.set(key, items, timeout=86400)
    return items


def _get_picsum_photo(index, run_date):
    seed = int(hashlib.sha256(f"{run_date}:{index}:picsum".encode()).hexdigest()[:12], 16)
    history = _recent_photo_usage()
    fallback = []
    # The public catalogue is finite. Prefer unused photos, then the oldest
    # eligible photo, never one used in the last 24 hours.
    for offset in range(12):
        page = (seed + offset) % 12 + 1
        items = _picsum_page(page)
        if not items:
            continue
        rotated = items[seed % len(items):] + items[:seed % len(items)]
        for item in rotated:
            if not isinstance(item, dict):
                continue
            photo_id = str(item.get("id", ""))
            width, height = item.get("width"), item.get("height")
            page_url = item.get("url") or ""
            if (
                not re.fullmatch(r"\d{1,8}", photo_id)
                or not isinstance(width, int) or not isinstance(height, int)
                or height <= 0 or width < max(height, 1200)
                or not _has_host(page_url, "unsplash.com")
                or not page_url.startswith("https://unsplash.com/photos/")
            ):
                continue
            author = str(item.get("author") or "Unsplash photographer")[:80]
            photo = {
                "id": photo_id,
                "provider": "picsum",
                "credit_source": "Unsplash via Picsum",
                "image_url": f"https://picsum.photos/id/{photo_id}/1200/800.jpg",
                "photo_page": page_url,
                "photographer": author,
                "alt": f"Photo by {author}",
                "theme": "A reflective pause and a fresh perspective. The photo subject is unknown; do not describe its scene",
            }
            used_at = history.get(f"picsum:{photo_id}", 0)
            if used_at:
                fallback.append((used_at, photo))
            elif cache.add(f"warmup-photo-reservation:picsum:{photo_id}", 1, timeout=3600):
                return photo
    cutoff = (timezone.now() - timedelta(days=1)).timestamp()
    for used_at, photo in sorted(fallback, key=lambda pair: pair[0]):
        if used_at < cutoff and cache.add(
            f"warmup-photo-reservation:picsum:{photo['id']}", 1, timeout=3600
        ):
            logger.info("Picsum catalogue rotation | photo_id=%s", photo["id"])
            return photo
    raise WarmupTemplateError("No eligible remote photo is available. Try again later.")


def generate_warmup_template(run_date, sequence, batch_key=None):
    """Generate one slot once, keeping HTML and no image bytes locally."""
    if sequence < 0:
        raise WarmupTemplateError("Template sequence cannot be negative.")
    batch_key = batch_key or run_date.isoformat()
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", batch_key):
        raise WarmupTemplateError("Invalid template batch key.")

    title = f"Warmup Template {batch_key} #{sequence + 1:03d}"
    existing = Content.objects.filter(content_type="warmup_template", title=title).first()
    if existing:
        return existing
    lock_key = "warmup-template:" + hashlib.sha256(title.encode()).hexdigest()
    if not cache.add(lock_key, "locked", timeout=600):
        raise WarmupTemplateInProgress("This template slot is already being generated.")

    try:
        existing = Content.objects.filter(content_type="warmup_template", title=title).first()
        if existing:
            return existing
        destination_url = validate_destination_url(settings.WARMUP_TEMPLATE_LINK_URL)
        photo = _get_remote_photo(sequence, run_date)
        # Photo I/O happens before taking the database lock. The label and HTML
        # commit together: retries and failed saves never consume a label.
        with transaction.atomic():
            WarmupButtonRotation.objects.get_or_create(bank_version=BUTTON_BANK_VERSION)
            rotation = WarmupButtonRotation.objects.select_for_update().get(
                bank_version=BUTTON_BANK_VERSION,
            )
            # The shared DB lock also protects this slot if a cache lease expires.
            existing = Content.objects.filter(content_type="warmup_template", title=title).first()
            if existing:
                return existing
            button_index = rotation.next_position % len(BUTTON_LABELS)
            markup = validate_warmup_html(
                render_warmup_html(photo, run_date, sequence, destination_url,
                                   button_label=BUTTON_LABELS[button_index]),
                photo, destination_url=destination_url,
            )
            user_prompt = (
                f"Empty HTML shell. {photo.get('provider', 'pexels').title()} photo ID: {photo['id']}. "
                f"Button label: {BUTTON_BANK_VERSION}:{button_index:04d}. "
                "Melal supplies the existing message through {{content}}."
            )
            content = Content.objects.create(
                title=title,
                content_type="warmup_template",
                prompt=user_prompt,
                generated_content=markup,
                content_hash=hashlib.sha256(markup.encode("utf-8")).hexdigest(),
                status="generated",
            )
            rotation.next_position += 1
            rotation.save(update_fields=["next_position"])
        logger.info(
            "Warmup template saved locally | content_id=%s | photo_id=%s",
            content.pk, photo["id"],
        )
        return content
    finally:
        cache.delete(lock_key)
