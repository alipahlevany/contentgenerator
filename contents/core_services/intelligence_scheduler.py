from django.core.cache import cache

from contents.core_services.weight_optimizer import optimize_dataset_weights


OPTIMIZATION_EVENT_INTERVAL = 50
CACHE_KEY = "content_intelligence_event_counter"


def maybe_run_intelligence_optimization():
    # Redis increment is atomic across workers; get + set could lose events.
    cache.add(CACHE_KEY, 0, timeout=None)
    try:
        current_count = cache.incr(CACHE_KEY)
    except ValueError:
        # A cache clear between add and incr should not fail a saved output.
        cache.add(CACHE_KEY, 1, timeout=None)
        return False

    if current_count % OPTIMIZATION_EVENT_INTERVAL:
        return False

    optimize_dataset_weights(limit=100)
    return True
