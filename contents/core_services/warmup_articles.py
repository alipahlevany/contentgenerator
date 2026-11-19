"""Choose real Medium stories for warmup shells without storing article bodies."""

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from contents.core_services.warmup_template_renderer import WarmupTemplateError, validate_destination_url
from contents.models import Content

logger = logging.getLogger(__name__)
DEFAULT_TOPICS = ("technology", "creativity", "productivity", "design", "travel", "science", "food", "nature", "books", "artificial-intelligence")
ARTICLE_MARKER = "Article URL: "


def _story_url(value):
    try:
        value = validate_destination_url(value.strip())
        parts = urlsplit(value)
        if parts.hostname not in {"medium.com", "www.medium.com"}:
            return None
        if not parts.path.strip("/") or parts.path.startswith("/tag/"):
            return None
        return urlunsplit(("https", "medium.com", parts.path.rstrip("/"), "", ""))
    except (AttributeError, WarmupTemplateError):
        return None


def _feed_stories(topic):
    key = f"warmup-medium-feed-v1:{topic}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    response = requests.get(
        f"https://medium.com/feed/tag/{topic}",
        headers={"Accept": "application/rss+xml, application/xml;q=0.9"},
        timeout=(5, 15),
    )
    response.raise_for_status()
    if len(response.content) > 2_000_000:
        raise WarmupTemplateError("Medium RSS response is too large.")
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        raise WarmupTemplateError("Medium returned invalid RSS.") from exc
    stories = []
    for item in root.findall("./channel/item"):
        url = _story_url(item.findtext("link") or "")
        if url and url not in stories:
            stories.append(url)
    if stories:
        cache.set(key, stories, timeout=6 * 3600)
    return stories


def _recent_usage():
    since = timezone.now() - timedelta(days=45)
    usage = {}
    prompts = Content.objects.filter(content_type="warmup_template", created_at__gte=since).values_list("prompt", "created_at")
    for prompt, created_at in prompts.iterator(chunk_size=500):
        match = re.search(r"Article URL: (https://\S+)", prompt or "")
        if match:
            usage[match.group(1)] = max(usage.get(match.group(1), 0), created_at.timestamp())
    return usage


def choose_article(run_date, sequence):
    """Prefer unseen stories; reuse the oldest only after a full day."""
    topics = getattr(settings, "WARMUP_TEMPLATE_ARTICLE_TOPICS", DEFAULT_TOPICS)
    if not topics:
        raise WarmupTemplateError("Configure at least one Medium article topic.")
    seed = int(hashlib.sha256(f"{run_date}:{sequence}:article".encode()).hexdigest()[:12], 16)
    usage = _recent_usage()
    candidates = []
    for offset in range(len(topics)):
        topic = topics[(seed + offset) % len(topics)]
        try:
            candidates.extend(_feed_stories(topic))
        except (requests.RequestException, WarmupTemplateError) as exc:
            logger.warning("Medium RSS unavailable for %s: %s", topic, exc)
    candidates = list(dict.fromkeys(candidates))
    if not candidates:
        raise WarmupTemplateError("No Medium article is available; template generation was skipped.")
    candidates = candidates[seed % len(candidates):] + candidates[:seed % len(candidates)]
    cutoff = (timezone.now() - timedelta(days=1)).timestamp()
    for url in sorted(candidates, key=lambda item: usage.get(item, 0)):
        if usage.get(url, 0) >= cutoff:
            continue
        if cache.add(f"warmup-article-reservation:{hashlib.sha256(url.encode()).hexdigest()}", 1, timeout=3600):
            return url
    raise WarmupTemplateError("No unused Medium article is available today; template generation was skipped.")
