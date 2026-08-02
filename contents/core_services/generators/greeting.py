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

    MIN_WORDS = 2
    MAX_WORDS = 30

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
    ):
        language_name = getattr(
            language,
            "name",
            str(language),
        )

        system_prompt = """
You generate short, natural greetings for the beginning of
emails and messages.

Rules:

- Write only the greeting text.
- Do not write a subject line.
- Do not explain the output.
- Do not add labels such as "Greeting" or "Message".
- Use the requested language naturally and fluently.
- Sound human, warm, and conversational.
- Avoid robotic or overly formal wording.
- Keep the greeting short.
- Do not write a complete email.
- Do not add a signature.
- Do not invent names, companies, dates, links, or facts.
- Do not use placeholders.
- Do not use quotation marks around the output.
- Generate one greeting only.
- The result must be immediately usable.
        """.strip()

        user_prompt = f"""
Generate one short and natural greeting in {language_name}.

Requirements:
- Return only the greeting.
- Keep it concise and human.
- Do not include a subject or signature.
- Do not use placeholders.
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
        body = generated_text.strip()

        if not body:
            raise GeneratorOutputError(
                "Greeting output is empty."
            )

        if "[[" in body or "]]" in body:
            raise GeneratorOutputError(
                "Greeting output contains placeholders."
            )

        word_count = len(body.split())

        if word_count < self.MIN_WORDS:
            raise GeneratorOutputError(
                "Greeting output is too short."
            )

        if word_count > self.MAX_WORDS:
            raise GeneratorOutputError(
                "Greeting output is too long."
            )

        return fallback_title, body
