from contents.core_services.cleaner import clean_generated_content


class SafeFormatDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def render_template(template_text, context):
    return (template_text or "").format_map(SafeFormatDict(**context))


def extract_title_and_content(text, fallback_title):
    text = clean_generated_content(text)

    if not text:
        return fallback_title[:255], ""

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    title = fallback_title
    content = text

    if lines:
        first_line = lines[0]

        if first_line.lower().startswith("title:"):
            title = first_line.split(":", 1)[1].strip()
            content = "\n".join(lines[1:]).strip() or text

        elif first_line.startswith("#"):
            title = first_line.lstrip("#").strip()
            content = "\n".join(lines[1:]).strip() or text

    content = clean_generated_content(content)

    if not title:
        title = fallback_title

    return title[:255], content


def build_context(app_settings, language, topic, audience, goal, selected_rules):
    rules_text = "\n".join(
        f"- {rule.prompt_text}"
        for rule in selected_rules
        if rule.prompt_text
    )

    if not rules_text:
        rules_text = "- No additional rules."

    return {
        "language": language.name,
        "language_name": language.name,
        "language_code": language.code,
        "topic": topic.name,
        "audience": audience.name,
        "goal": goal.name,
        "rules": rules_text,
        "min_words": app_settings.min_words,
        "max_words": app_settings.max_words,
    }