import re

from contents.core_services.generators.base import (
    BaseGenerator,
    GeneratorOutputError,
)


class EmailReplyGenerator(BaseGenerator):
    ALLOWED_PLACEHOLDERS = {
        "[[email]]",
        "[[name]]",
        "[[code]]",
        "[[date]]",
    }

    PLACEHOLDER_PATTERN = re.compile(
        r"\[\[[^\[\]\r\n]+\]\]"
    )

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
        # Reply generation intentionally ignores:
        # topic, audience, goal, prompt_template and content rules.
        language_name = getattr(
            language,
            "name",
            str(language),
        )

        placeholder_list = ", ".join(
            sorted(self.ALLOWED_PLACEHOLDERS)
        )

        system_prompt = f"""
You are a professional business email reply writer.

Write exactly one complete email reply in {language_name}.

The reply must follow this structure:

Dear [[name]],

A polite opening sentence acknowledging the recipient or their message.

A clear main paragraph explaining the response, decision, update, acceptance,
rejection, request, or current status.

A short and polite closing sentence.

Sincerely,

Strict requirements:

- Write only in {language_name}.
- Return only the email body.
- Do not include a subject line.
- Do not include a title.
- Do not include explanations.
- Do not include markdown.
- Do not provide multiple versions.
- Do not write labels such as "Opening", "Response", or "Closing".
- Use natural, professional and human-sounding language.
- Keep the reply focused and coherent.
- Do not introduce unrelated topics.
- Do not mention audience, marketing goals or content-generation instructions.
- Use [[name]] when the recipient's name is unknown.
- Allowed placeholders: {placeholder_list}.
- Never create any other placeholder.
""".strip()

        user_prompt = f"""
Generate one professional email reply in {language_name}.

Use this exact general format:

Dear [[name]],

[Professional acknowledgement or opening.]

[Clear and polite response or decision.]

[Brief closing sentence.]

Sincerely,

The response should sound natural and suitable for real email communication.
Return only the finished email body.
""".strip()

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "fallback_title": "Email Reply",
        }

    def _validate_placeholders(self, text):
        placeholders = set(
            self.PLACEHOLDER_PATTERN.findall(text)
        )

        invalid = placeholders - self.ALLOWED_PLACEHOLDERS

        if invalid:
            raise GeneratorOutputError(
                "Unsupported placeholders: "
                + ", ".join(sorted(invalid))
            )

    def extract_output(
        self,
        generated_text,
        fallback_title,
    ):
        body = generated_text.strip()

        self._validate_placeholders(body)

        return fallback_title, body
