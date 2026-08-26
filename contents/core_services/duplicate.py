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


def is_duplicate_content(title, content_body, content_type=None):
    content_hash = make_content_hash(content_body)

    # Titles are presentation metadata, not content identity. Greeting titles
    # are intentionally system-generated and standard content can legitimately
    # reuse a useful headline with a different body. Rejecting on title alone
    # caused valid outputs to be skipped until the job hit its runtime limit.
    duplicates = Content.objects.all()
    if content_type:
        duplicates = duplicates.filter(content_type=content_type)

    if content_hash and duplicates.filter(content_hash=content_hash).exists():
        return True, "duplicate content", content_hash

    return False, None, content_hash
