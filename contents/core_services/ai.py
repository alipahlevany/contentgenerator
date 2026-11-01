import logging

from django.conf import settings
from django.db import transaction

import httpx
from openai import OpenAI

from contents.core_services.cache import get_app_settings
from contents.core_services.cleaner import clean_generated_content
from contents.core_services.retry import RETRYABLE_ERRORS, sleep_before_retry
from contents.models import AIUsageLog


logger = logging.getLogger(__name__)


# Keep retries in one place; SDK retries would multiply our attempt budget.
client = OpenAI(
    api_key=settings.OPENAI_API_KEY,
    timeout=httpx.Timeout(90.0, connect=10.0, write=30.0, pool=10.0),
    max_retries=0,
)


class PermanentGenerationError(RuntimeError):
    """A configuration/account error that another generation cannot fix."""


class TransientGenerationError(RuntimeError):
    """The request retry budget was exhausted by a temporary API failure."""


def get_response_text_from_content(content):
    if isinstance(content, dict):
        return content.get("text", "")

    return getattr(content, "text", "")


def extract_response_text(response):
    output_text = getattr(response, "output_text", None)

    if output_text:
        return output_text.strip()

    parts = []

    for item in getattr(response, "output", []) or []:
        item_content = getattr(item, "content", None)

        if item_content is None and isinstance(item, dict):
            item_content = item.get("content", [])

        for content in item_content or []:
            text = get_response_text_from_content(content)

            if text:
                parts.append(text)

    return "\n".join(parts).strip()


def record_response_usage(response, model_name, purpose, generation_type):
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    try:
        details = getattr(usage, "input_tokens_details", None)
        # An incomplete or later-rejected response still consumed tokens.
        # Keep the log compact: no prompts or copies of generated content.
        with transaction.atomic():
            AIUsageLog.objects.create(
                model_name=getattr(response, "model", None) or model_name,
                purpose=purpose,
                generation_type=generation_type,
                input_tokens=usage.input_tokens,
                cached_input_tokens=getattr(details, "cached_tokens", 0) or 0,
                output_tokens=usage.output_tokens,
            )
    except Exception:
        # A metering failure must not discard an already paid-for response.
        logger.exception("Unable to record AI response token usage")


def generate_content(system_prompt, user_prompt=None, max_retries=3, *,
                     purpose="content_generation", generation_type=""):
    app_settings = get_app_settings()
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            request = {
                "model": app_settings.model_name,
                "instructions": system_prompt,
                "input": user_prompt or "",
                "max_output_tokens": app_settings.max_output_tokens,
                "temperature": app_settings.temperature,
            }
            if app_settings.model_name == "gpt-6-luna":
                request.update(
                    reasoning={"effort": "none"},
                    service_tier="default",
                )
            response = client.responses.create(**request)

            record_response_usage(response, app_settings.model_name, purpose, generation_type)

            if getattr(response, "status", None) in {"incomplete", "failed"}:
                raise ValueError("OpenAI returned an incomplete or failed response.")

            text = extract_response_text(response)

            if not text:
                raise ValueError("OpenAI returned empty output.")

            cleaned_text = clean_generated_content(text)
            if not cleaned_text:
                raise ValueError("OpenAI returned empty output after cleanup.")
            return cleaned_text

        except RETRYABLE_ERRORS as exc:
            status = getattr(exc, "status_code", None)
            code = getattr(exc, "code", None)
            if (
                status is not None
                and status < 500
                and status not in {408, 409, 429}
            ) or code == "insufficient_quota":
                raise PermanentGenerationError(
                    f"OpenAI generation failed: {exc}"
                ) from exc
            last_error = exc

            print(
                f"OpenAI retryable error "
                f"(attempt {attempt}/{max_retries}): {exc}"
            )

            if attempt < max_retries:
                delay = sleep_before_retry(exc, attempt)
                print(f"Retrying OpenAI request in {delay} seconds.")

        except ValueError as exc:
            last_error = exc
            break

    error_type = (
        TransientGenerationError
        if isinstance(last_error, RETRYABLE_ERRORS)
        else RuntimeError
    )
    raise error_type(f"OpenAI generation failed: {last_error}") from last_error
