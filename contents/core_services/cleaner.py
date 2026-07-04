import re


def normalize(text):
    return re.sub(r"\s+", " ", text or "").strip().casefold()


def clean_generated_content(text):
    if not text:
        return ""

    text = text.strip()
    text = re.sub(r"^\s*content\s*:\s*", "", text, flags=re.IGNORECASE)

    return text.strip()