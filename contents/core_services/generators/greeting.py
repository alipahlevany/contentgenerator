import uuid

from contents.core_services.generators.base import (
    BaseGenerator,
    GeneratorOutputError,
)


class GreetingGenerator(BaseGenerator):
    """
    Generate short, natural greetings in the requested language.

    Greeting generation intentionally depends only on Language.
    """

    MIN_WORDS = 12
    MAX_WORDS = 50

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
    ):
        language_name = getattr(
            language,
            "name",
            str(language),
        )

        system_prompt = """
You generate professional, natural, ready-to-use email greetings.

Your output MUST follow this exact format:

TITLE:
<short email subject>

GREETING:
<greeting message>

STRICT RULES:

TITLE RULES:
- Title must be 3 to 8 words.
- Title must be related to the greeting.
- Title must sound like a natural email subject.
- Do not use emojis.
- Do not use quotes.
- Do not use placeholders.

GREETING RULES:
- Write only the greeting message.
- Minimum 12 words.
- Maximum 45 words.
- Use 1 to 3 natural sentences.
- Sound warm, human, and conversational.
- Must be immediately usable at the beginning of an email.
- Do not write a complete email.
- Do not add a signature.
- Do not include names, companies, dates, links, or fake information.
- Do not add explanations.

QUALITY REQUIREMENTS:
- Never return only a title.
- Never return incomplete output.
- Always return both TITLE and GREETING.
- Never produce a greeting shorter than 12 words.

Return only the required format.
        """.strip()

        user_prompt = f"""
Generate one natural and warm greeting in {language_name}.

Variation seed: {variation_key}
Use this seed only to vary the wording, opening style, sentence
structure, rhythm, and tone of the greeting.
Never mention, print, explain, or expose the variation seed.

Return exactly this format:

TITLE:
A short email subject/title

GREETING:
The greeting text


TITLE RULES:
- 3 to 8 words.
- Natural email subject.
- Related to the greeting.
- No emojis.
- No placeholders.

GREETING RULES:
- Write approximately 15 to 45 words.
- Use 1 to 3 short sentences.
- Make it conversational and immediately usable.
- Do not write a full email.
- Do not add signature.
- Do not add explanations.
        """.strip()

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "fallback_title": (
                f"Greeting {uuid.uuid4().hex[:12]}"
            ),
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

        title = fallback_title
        body = text

        if "TITLE:" in text and "GREETING:" in text:

            title_part = text.split(
                "TITLE:",
                1
            )[1]

            title, body = title_part.split(
                "GREETING:",
                1
            )

            title = title.strip()
            body = body.strip()

        if not title:
            title = fallback_title

        word_count = len(body.split())

        minimum_words = self.MIN_WORDS

        if word_count < minimum_words:
            raise GeneratorOutputError(
                "Greeting output is too short."
            )

        if word_count > self.MAX_WORDS:
            raise GeneratorOutputError(
                "Greeting output is too long."
            )

        return title, body
