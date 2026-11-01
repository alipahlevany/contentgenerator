import uuid
import re

from contents.core_services.generators.base import (
    BaseGenerator,
    GeneratorOutputError,
)


class EmailReplyGenerator(BaseGenerator):

    def get_pool_log_message(
        self,
        languages,
        **kwargs,
    ):
        return (
            "Using email reply generation pool. "
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

    ALLOWED_PLACEHOLDERS = {
        "[[name]]",
        "[[first_name]]",
        "[[company]]",
        "[[email]]",
        "[[phone]]",
        "[[website]]",
        "[[link]]",
        "[[order_number]]",
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
        variation_key=None,
        retry_feedback="",
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
Write a natural, ready-to-send email reply body in the requested language.
Use a warm, professional, conversational tone appropriate to that language.
Be clear and useful; avoid stock customer-service phrases, repeated courtesies,
and unnecessary introductions. Vary openings rather than always saying thanks.
Invent no facts, names, dates, deadlines, promises, links, contact details,
order numbers, or company information. Use placeholders only when necessary,
and only these exact tokens: {placeholder_list}.
Use 40-120 words in 2-4 short paragraphs; aim for 50-70 words.
Return only the body, with no subject, label, explanation, signature, or initials.
End with a complete sentence.
        """.strip()

        user_prompt = f"""
Write one email reply in {language_name} with fresh wording and paragraph flow.
Variation: {variation_key} (never include this identifier in the reply).
{retry_feedback}
        """.strip()

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "fallback_title": f"Email Reply {uuid.uuid4().hex[:12]}",
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
