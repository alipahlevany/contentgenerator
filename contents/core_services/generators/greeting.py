import re

from contents.core_services.generators.base import (
    BaseGenerator,
    GeneratorOutputError,
)


class GreetingGenerator(BaseGenerator):
    """
    Generate short, natural greetings in the requested language.

    Greeting generation intentionally depends only on Language.
    """

    DEFAULT_WORD_LIMITS = (15, 30)
    LANGUAGE_WORD_LIMITS = {
        "en": (15, 30), "fa": (15, 30), "de": (15, 30),
        "fr": (15, 30), "es": (15, 30),
    }
    FALLBACK_TITLE = "Warm Email Greeting"

    # A narrower prompt target leaves enough room around the hard
    # validation limits. This reduces length-related retries while keeping
    # the final greeting concise.
    TARGET_WORD_LIMITS = (18, 24)

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

    OVERUSED_PATTERNS = (
        "i hope this email finds you well",
        "i hope this message finds you well",
        "trust this email finds you well",
        "greetings of the day",
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
        target_min, target_max = self.TARGET_WORD_LIMITS
        style_name, style_instruction = self.style_direction(
            variation_key
        )

        system_prompt = f"""
You write exceptional, ready-to-use email openings in {language_name}.

The greeting must sound like a thoughtful person beginning a genuine
one-to-one email. It should be warm, polished, memorable, and effortless,
never robotic, ceremonial, salesy, or overly enthusiastic.

Quality rules:
- Write naturally in {language_name}; use phrasing and punctuation that feel
  native to that language instead of translating an English formula.
- Express one clear warm thought. Do not stack several wishes or compliments.
- Create a smooth bridge into the email that could naturally be followed by
  the sender's main message.
- Prefer fresh, specific-feeling language without inventing any personal fact,
  relationship, event, season, time of day, or reason for writing.
- Avoid tired formulas such as "I hope this email finds you well",
  "I hope you're doing well", "I hope you're having a wonderful day",
  "Greetings of the day", and close translations of those phrases.
- Do not begin every output with the equivalent of "Hello" or "I hope".
- Use at most one exclamation mark and avoid emojis.
- Use 1 or 2 complete, conversational sentences.
- Aim for {target_min} to {target_max} words. The absolute valid range is
  {min_words} to {max_words} words.

Return only the greeting text. Do not include a title, label, markdown,
quotation marks, signature, name, placeholder, date, link, explanation,
subject line, or the rest of an email.
        """.strip()

        user_prompt = f"""
Write one distinctive email greeting in {language_name}.

Variation seed: {variation_key}
Use this seed only to vary wording, sentence structure, opening cadence,
and tone. Never mention or expose it.

Creative direction: {style_name}
{style_instruction}

Make the result feel personal without using a name and without pretending to
know anything about the recipient. It must be immediately usable at the start
of a real email and should flow naturally into the next paragraph.

Target {target_min} to {target_max} words and stay inside the hard limit of
{min_words} to {max_words} words.

Return only the greeting itself, with no wrapper or extra text.
{retry_feedback}
        """.strip()

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "fallback_title": self.FALLBACK_TITLE,
        }

    def extract_output(
        self,
        generated_text,
        fallback_title,
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

        minimum_words, maximum_words = self.DEFAULT_WORD_LIMITS
        word_count = len(body.split())

        if word_count < minimum_words:
            raise GeneratorOutputError(
                "Greeting output is too short."
            )

        if word_count > maximum_words:
            raise GeneratorOutputError(
                "Greeting output is too long."
            )

        return fallback_title or self.FALLBACK_TITLE, body
