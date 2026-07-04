import time

from django.conf import settings

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

from contents.core_services.cache import get_app_settings
from contents.core_services.cleaner import clean_generated_content


client = OpenAI(api_key=settings.OPENAI_API_KEY)


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


def generate_content(system_prompt, user_prompt=None, max_retries=3):
    app_settings = get_app_settings()
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            response = client.responses.create(
                model=app_settings.model_name,
                instructions=system_prompt,
                input=user_prompt or "",
                max_output_tokens=app_settings.max_output_tokens,
                temperature=app_settings.temperature,
            )

            text = extract_response_text(response)

            if not text:
                raise ValueError("OpenAI returned empty output.")

            return clean_generated_content(text)

        except (
            APIConnectionError,
            APIError,
            APITimeoutError,
            RateLimitError,
            ValueError,
        ) as exc:
            last_error = exc

            print(
                f"OpenAI generation failed "
                f"(attempt {attempt}/{max_retries}): {exc}"
            )

            if attempt < max_retries:
                time.sleep(2 * attempt)

    raise RuntimeError(f"OpenAI generation failed: {last_error}")