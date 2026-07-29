import re

from contents.core_services.cache import get_blocked_keywords


def build_blocked_keyword_pattern(keyword):
    """
    Build a safe regex pattern for a blocked keyword.

    The boundaries prevent short blocked words from matching
    inside larger words.

    Example:
    "sex" will not match inside "Sussex".
    """
    keyword = keyword.strip()

    if not keyword:
        return None

    return rf"(?<!\\w){re.escape(keyword)}(?!\\w)"


def contains_blocked_keyword(text):
    """
    Check whether the generated text contains a blocked keyword.

    Returns:
        tuple: (has_blocked_keyword, blocked_keyword)
    """
    if not text:
        return False, None

    for keyword in get_blocked_keywords():
        pattern = build_blocked_keyword_pattern(keyword)

        if not pattern:
            continue

        if re.search(pattern, text, flags=re.IGNORECASE):
            return True, keyword

    return False, None


def remove_blocked_keywords(text):
    """
    Remove blocked keywords from generated text without rejecting
    the entire OpenAI response.
    """
    if not text:
        return text

    cleaned_text = text

    for keyword in get_blocked_keywords():
        pattern = build_blocked_keyword_pattern(keyword)

        if not pattern:
            continue

        cleaned_text = re.sub(
            pattern,
            "",
            cleaned_text,
            flags=re.IGNORECASE,
        )

    cleaned_text = re.sub(r"[ \\t]{2,}", " ", cleaned_text)

    cleaned_text = re.sub(
        r"[ \\t]+([.,!?;:])",
        r"\\1",
        cleaned_text,
    )

    cleaned_text = re.sub(
        r"([\\(\\[\\{])[ \\t]+",
        r"\\1",
        cleaned_text,
    )

    cleaned_text = re.sub(
        r"[ \\t]+([\\)\\]\\}])",
        r"\\1",
        cleaned_text,
    )

    cleaned_text = re.sub(
        r"\\n[ \\t]+\\n",
        "\\n\\n",
        cleaned_text,
    )

    cleaned_text = re.sub(
        r"\\n{3,}",
        "\\n\\n",
        cleaned_text,
    )

    return cleaned_text.strip()
