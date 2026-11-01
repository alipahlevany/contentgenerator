import re

from contents.core_services.generators.base import (
    BaseGenerator,
    GeneratorOutputError,
)


def build_greeting_title(content_body, fallback_title="Greeting"):
    """Build a short, useful title without asking the model for metadata."""
    body = " ".join((content_body or "").split()).strip()
    fallback = " ".join(
        (fallback_title or "Greeting").split()
    ).strip()

    if not body:
        return fallback[:255]

    words = body.split()
    excerpt = " ".join(words[:7]).strip(
        " \t\r\n.,;:!?…،؛؟。！？”“\"'"
    )
    was_truncated = len(words) > 7

    if len(excerpt) > 72:
        excerpt = excerpt[:72].rstrip(
            " \t\r\n.,;:!?…،؛؟。！？”“\"'"
        )
        was_truncated = True

    if not excerpt:
        return fallback[:255]

    suffix = "…" if was_truncated else ""
    return f"{excerpt}{suffix}"[:255]


class GreetingGenerator(BaseGenerator):
    """
    Generate short, natural greetings in the requested language.

    Greeting generation intentionally depends only on Language.
    """

    DEFAULT_WORD_LIMITS = (15, 30)
    LANGUAGE_WORD_LIMITS = {
        "en": (15, 30), "fa": (15, 30),
        "fr": (15, 30), "es": (15, 30),
        # These languages often express a complete greeting in fewer words.
        "tr": (12, 30), "hu": (12, 30), "pl": (12, 30),
        "cs": (12, 30), "sk": (12, 30), "uk": (12, 30),
        "de": (12, 30), "nl": (12, 30), "bg": (12, 30),
    }
    FALLBACK_TITLE = "Warm Email Greeting"

    # A narrower prompt target leaves enough room around the hard
    # validation limits. This reduces length-related retries while keeping
    # the final greeting concise.
    TARGET_WORD_LIMITS = (20, 26)

    STYLE_DIRECTIONS = (
        (
            "Warm and grounded",
            "Open with calm, genuine warmth and a relaxed professional "
            "rhythm.",
        ),
        (
            "Bright and forward-looking",
            "Create a light sense of positive momentum without sounding "
            "excited or promotional.",
        ),
        (
            "Thoughtful and polished",
            "Use understated warmth and elegant, natural phrasing.",
        ),
        (
            "Friendly and conversational",
            "Sound like a considerate person beginning a real one-to-one "
            "email.",
        ),
        (
            "Calm and reassuring",
            "Use a composed, easy tone that feels welcoming without making "
            "any promises.",
        ),
        (
            "Fresh and concise",
            "Use an original opening cadence with one clear, warm thought.",
        ),
    )

    # Decode the random key into independent, concrete writing constraints.
    # A random number alone is not a useful instruction for linguistic variety.
    THEMES = (
        "simple, sincere goodwill",
        "a friendly yet restrained welcome",
        "a considerate wish for a pleasant moment",
        "quiet optimism without a prediction",
        "courteous warmth toward the recipient",
        "a light, positive opening",
        "warmth through plain, everyday wording",
        "respectful friendliness without flattery",
        "gentle encouragement without advice",
        "calm, understated good wishes",
        "a welcoming tone without a request",
        "cordiality in a direct, conversational voice",
        "modest kindness without grand sentiment",
        "a relaxed, professional manner",
        "an unhurried, friendly hello",
        "a balanced, warm and practical tone",
    )
    STRUCTURES = (
        "One sentence: a warm thought with a natural continuation.",
        "Two sentences: a brief salutation, then a complete warm thought.",
        "One sentence with a courteous first-person opening.",
        "Two sentences: a simple good wish followed by a cordial statement.",
        "One flowing sentence without a question.",
        "Two sentences with different grammatical openings.",
        "One sentence without starting with Hello or I hope.",
        "Two sentences: a short first sentence and a fuller second one.",
    )

    LABEL_PATTERN = re.compile(
        r"^\s*(?:greeting|email greeting)\s*[:\-–—]\s*",
        re.IGNORECASE,
    )

    def word_limits(self, language):
        code = str(getattr(language, "code", "")).lower().split("-")[0]
        return self.LANGUAGE_WORD_LIMITS.get(code, self.DEFAULT_WORD_LIMITS)

    def style_direction(self, variation_key):
        try:
            index = int(variation_key or 0) % len(self.STYLE_DIRECTIONS)
        except (TypeError, ValueError):
            index = 0

        return self.STYLE_DIRECTIONS[index]

    def writing_direction(self, variation_key):
        try:
            key = int(variation_key or 0)
        except (TypeError, ValueError):
            key = 0
        key //= len(self.STYLE_DIRECTIONS)
        theme = self.THEMES[key % len(self.THEMES)]
        key //= len(self.THEMES)
        structure = self.STRUCTURES[key % len(self.STRUCTURES)]
        return theme, structure

    def get_pool_log_message(
        self,
        languages,
        **kwargs,
    ):
        return (
            "Using greeting generation pool. "
            f"Languages: {len(languages)}."
        )

    def select_generation_context(
        self,
        *,
        languages,
        random_module,
        **kwargs,
    ):
        return {
            "language": random_module.choice(languages),
            "topic": None,
            "audience": None,
            "goal": None,
            "prompt_template": None,
            "selected_rules": [],
            "variation_key": random_module.randrange(
                1,
                1_000_000_000,
            ),
        }

    def build_prompt_data(
        self,
        app_settings,
        language,
        topic,
        audience,
        goal,
        prompt_template,
        selected_rules,
        variation_key=None,
        retry_feedback="",
    ):
        language_name = getattr(
            language,
            "name",
            str(language),
        )

        min_words, max_words = self.word_limits(language)
        target_min, target_max = (17, 23) if min_words == 12 else self.TARGET_WORD_LIMITS
        style_name, style_instruction = self.style_direction(
            variation_key
        )

        theme, structure = self.writing_direction(variation_key)

        system_prompt = f"""
Write a warm, professional email greeting in native {language_name}.
Start directly with a salutation or a sincere good wish to the recipient.
Sound like a considerate person: plain, modest, cordial, never poetic or salesy.
Write the greeting itself, without commenting on emails, words, writing,
conversations, reading, replies, or what comes next. No advice or requests.
Invent no prior contact, recipient details, or occasion. Use time-neutral
salutations: no morning, evening, or start-of-week greetings.
Avoid tired formulas such as "I hope this email finds you well", flattery,
abstract maxims, names, placeholders, signatures, links, and emojis.
Aim for {target_min} to {target_max} words in 1-2 complete sentences.
Return only the greeting; hard limit {min_words}-{max_words} space-separated words.
        """.strip()

        user_prompt = f"""
Language: {language_name}
Tone: {style_name}. {style_instruction}
Focus: {theme}.
Structure: {structure}
Use fresh native phrasing, not translations of these directions.
Count words: target {target_min}-{target_max}; valid {min_words}-{max_words}.
Variation {variation_key} (omit this identifier).
{retry_feedback}
        """.strip()

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "fallback_title": "Greeting",
        }

    def extract_output(
        self,
        generated_text,
        fallback_title,
        *,
        language=None,
    ):
        text = generated_text.strip()

        if not text:
            raise GeneratorOutputError(
                "Greeting output is empty."
            )

        if "[[" in text or "]]" in text:
            raise GeneratorOutputError(
                "Greeting output contains placeholders."
            )

        body = self.LABEL_PATTERN.sub("", text).strip()

        quote_pairs = {'"': '"', "'": "'", "“": "”", "‘": "’"}
        if (
            len(body) >= 2
            and body[0] in quote_pairs
            and body[-1] == quote_pairs[body[0]]
        ):
            body = body[1:-1].strip()

        # Line wrapping is harmless for a short greeting and should not turn
        # an otherwise useful output into a skipped attempt.
        body = " ".join(body.split())

        minimum_words, maximum_words = self.word_limits(language)
        word_count = len(body.split())

        if word_count < minimum_words:
            raise GeneratorOutputError(
                "Greeting output is too short."
            )

        if word_count > maximum_words:
            raise GeneratorOutputError(
                "Greeting output is too long."
            )

        return build_greeting_title(
            body,
            fallback_title or self.FALLBACK_TITLE,
        ), body
