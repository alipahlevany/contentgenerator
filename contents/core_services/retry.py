import time

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    RateLimitError,
)


RETRYABLE_ERRORS = (
    APIConnectionError,
    APIError,
    APITimeoutError,
    RateLimitError,
)


def get_retry_delay(error, attempt):
    if isinstance(error, RateLimitError):
        return min(30 * attempt, 120)

    if isinstance(error, APITimeoutError):
        return min(5 * attempt, 30)

    if isinstance(error, APIConnectionError):
        return min(5 * attempt, 30)

    if isinstance(error, APIError):
        return min(10 * attempt, 60)

    return min(2 * attempt, 20)


def sleep_before_retry(error, attempt):
    delay = get_retry_delay(error, attempt)
    time.sleep(delay)
    return delay