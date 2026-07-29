from pathlib import Path

services_path = Path("contents/services.py")
pipeline_dir = Path("contents/core_services/pipeline")
blocked_keywords_path = pipeline_dir / "blocked_keywords.py"
init_path = pipeline_dir / "__init__.py"

pipeline_dir.mkdir(parents=True, exist_ok=True)
init_path.touch(exist_ok=True)

services = services_path.read_text(encoding="utf-8")

blocked_keywords_code = '''import re

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

    return rf"(?<!\\\\w){re.escape(keyword)}(?!\\\\w)"


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

    cleaned_text = re.sub(r"[ \\\\t]{2,}", " ", cleaned_text)

    cleaned_text = re.sub(
        r"[ \\\\t]+([.,!?;:])",
        r"\\\\1",
        cleaned_text,
    )

    cleaned_text = re.sub(
        r"([\\\\(\\\\[\\\\{])[ \\\\t]+",
        r"\\\\1",
        cleaned_text,
    )

    cleaned_text = re.sub(
        r"[ \\\\t]+([\\\\)\\\\]\\\\}])",
        r"\\\\1",
        cleaned_text,
    )

    cleaned_text = re.sub(
        r"\\\\n[ \\\\t]+\\\\n",
        "\\\\n\\\\n",
        cleaned_text,
    )

    cleaned_text = re.sub(
        r"\\\\n{3,}",
        "\\\\n\\\\n",
        cleaned_text,
    )

    return cleaned_text.strip()
'''

blocked_keywords_path.write_text(
    blocked_keywords_code,
    encoding="utf-8",
)

old_cache_import = (
    "from .core_services.cache import get_app_settings, "
    "get_blocked_keywords"
)
new_cache_import = (
    "from .core_services.cache import get_app_settings"
)

if old_cache_import not in services:
    raise SystemExit(
        "ERROR: Expected cache import was not found in services.py."
    )

services = services.replace(
    old_cache_import,
    new_cache_import,
    1,
)

services = services.replace(
    "import re\n",
    "",
    1,
)

pipeline_import = '''from .core_services.pipeline.blocked_keywords import (
    contains_blocked_keyword,
    remove_blocked_keywords,
)
'''

anchor_import = (
    "from .core_services.logger import fail_job, log_job\n"
)

if pipeline_import not in services:
    if anchor_import not in services:
        raise SystemExit(
            "ERROR: Import anchor was not found in services.py."
        )

    services = services.replace(
        anchor_import,
        pipeline_import + anchor_import,
        1,
    )

start_marker = "def build_blocked_keyword_pattern(keyword):\n"
end_marker = "\n\ndef run_generation_job(job_id):\n"

start_index = services.find(start_marker)
end_index = services.find(end_marker)

if start_index == -1:
    raise SystemExit(
        "ERROR: Blocked keyword function block start was not found."
    )

if end_index == -1:
    raise SystemExit(
        "ERROR: run_generation_job marker was not found."
    )

if end_index <= start_index:
    raise SystemExit(
        "ERROR: Invalid blocked keyword function block range."
    )

services = (
    services[:start_index]
    + "def run_generation_job(job_id):\n"
    + services[end_index + len(end_marker):]
)

services_path.write_text(
    services,
    encoding="utf-8",
)

print("OK: pipeline package ensured.")
print("OK: blocked_keywords.py created.")
print("OK: blocked keyword functions removed from services.py.")
print("OK: services.py imports pipeline blocked keyword functions.")
