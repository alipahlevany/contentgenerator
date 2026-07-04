import hashlib

from contents.core_services.cleaner import normalize
from contents.models import Content


def make_content_hash(content_body):
    normalized_content = normalize(content_body)

    if not normalized_content:
        return ""

    return hashlib.sha256(
        normalized_content.encode("utf-8")
    ).hexdigest()


def is_duplicate_content(title, content_body):
    content_hash = make_content_hash(content_body)

    if Content.objects.filter(title__iexact=title).exists():
        return True, "duplicate title", content_hash

    if content_hash and Content.objects.filter(content_hash=content_hash).exists():
        return True, "duplicate content", content_hash

    return False, None, content_hash