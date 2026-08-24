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

    def word_limits(self, language):
        code = str(getattr(language, "code", "")).lower().split("-")[0]
        return self.LANGUAGE_WORD_LIMITS.get(code, self.DEFAULT_WORD_LIMITS)

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
        system_prompt = f"""
You generate one short, natural, ready-to-use email greeting in {language_name}.
Return only the greeting text, with no title, labels, markdown, signature,
names, dates, links, explanations, or complete email.
Use 1 to 2 warm conversational sentences and keep it between
{min_words} and {max_words} words.
        """.strip()

        user_prompt = f"""
Generate one natural and warm greeting in {language_name}.

Variation seed: {variation_key}
Use this seed only to vary the wording, opening style, sentence
structure, rhythm, and tone of the greeting.
Never mention, print, explain, or expose the variation seed.

Return only the greeting text.
Keep it between {min_words} and {max_words} words. Do not include a title,
labels, markdown, signature, names, dates, links, or explanations.
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

        body = text

        if "GREETING:" in body:
            body = body.split("GREETING:", 1)[1].strip()

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
