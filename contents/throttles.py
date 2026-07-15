import time

from django.core.cache import cache
from rest_framework.throttling import BaseThrottle


class ExternalClientRateThrottle(BaseThrottle):
    def allow_request(self, request, view):
        client = getattr(request, "client", None)
        if (
            client is None
            or not client.limits_enabled
            or client.requests_per_minute is None
        ):
            return True

        now = int(time.time())
        window = now // 60
        self.remaining_seconds = 60 - (now % 60)
        key = f"external-client-rate:{client.pk}:{window}"
        if cache.add(key, 1, timeout=self.remaining_seconds + 1):
            count = 1
        else:
            count = cache.incr(key)
        return count <= client.requests_per_minute

    def wait(self):
        return self.remaining_seconds
