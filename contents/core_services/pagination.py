from django.core import signing
from django.db.models import Q
from django.utils.dateparse import parse_datetime


CURSOR_SALT = "contents.api.cursor.v1"
CURSOR_MAX_AGE = 86400


class InvalidCursor(ValueError):
    pass


def cursor_mode_requested(request):
    return "cursor" in request.query_params or "page_size" in request.query_params


def paginate_queryset(queryset, request, *, maximum_page_size=100):
    try:
        page_size = int(request.query_params.get("page_size", maximum_page_size))
    except (TypeError, ValueError) as exc:
        raise InvalidCursor("page_size must be an integer.") from exc
    if page_size < 1 or page_size > maximum_page_size:
        raise InvalidCursor(f"page_size must be between 1 and {maximum_page_size}.")

    cursor = request.query_params.get("cursor")
    if cursor:
        try:
            payload = signing.loads(
                cursor,
                salt=CURSOR_SALT,
                max_age=CURSOR_MAX_AGE,
            )
            created_at = parse_datetime(payload["created_at"])
            object_id = int(payload["id"])
            if created_at is None:
                raise ValueError
        except (signing.BadSignature, KeyError, TypeError, ValueError) as exc:
            raise InvalidCursor("Invalid or expired cursor.") from exc
        queryset = queryset.filter(
            Q(created_at__lt=created_at)
            | Q(created_at=created_at, id__lt=object_id)
        )

    items = list(queryset.order_by("-created_at", "-id")[:page_size + 1])
    has_more = len(items) > page_size
    items = items[:page_size]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = signing.dumps(
            {"created_at": last.created_at.isoformat(), "id": last.id},
            salt=CURSOR_SALT,
        )
    return items, next_cursor
