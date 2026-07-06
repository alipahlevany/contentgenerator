from django.core.cache import cache

from contents.core_services.weight_optimizer import optimize_dataset_weights


OPTIMIZATION_EVENT_INTERVAL = 50
CACHE_KEY = "content_intelligence_event_counter"


def maybe_run_intelligence_optimization():
    current_count = cache.get(CACHE_KEY, 0) + 1
    cache.set(CACHE_KEY, current_count, timeout=None)

    if current_count < OPTIMIZATION_EVENT_INTERVAL:
        return False

    cache.set(CACHE_KEY, 0, timeout=None)
    optimize_dataset_weights(limit=100)

    return True