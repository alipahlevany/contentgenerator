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

        # Keep shared instructions stable and compact; put variation and
        # retry-specific guidance only in the user input. Do not shorten the
        # answer budget: truncation can cause extra paid generation attempts.
        system_prompt = (
            "Write only a ready-to-send email reply body in the requested language. "
            "Be natural, warm, professional and useful; vary openings and flow. "
            "Avoid stock phrases, repeated courtesies and unnecessary introductions. "
            "Invent no facts, identities, dates, deadlines, promises, URLs or contact/order details. "
            f"If needed, use only these exact placeholders: {placeholder_list}. "
            "40-120 words, ideally 50-70, in 2-4 short paragraphs. "
            "No subject, labels, explanation, signature or initials. "
            "Finish the sentence. Never print the variation ID."
        )
        user_prompt = f"Language: {language_name}. Variation: {variation_key}."
        if retry_feedback:
            user_prompt += f"\n{retry_feedback.strip()}"

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

        # The exact-token check above does not catch incomplete delimiters.
        without_valid_tokens = self.PLACEHOLDER_PATTERN.sub("", text)
        if "[[" in without_valid_tokens or "]]" in without_valid_tokens:
            raise GeneratorOutputError("Malformed reply placeholder.")

    def extract_output(
        self,
        generated_text,
        fallback_title,
        *,
        language=None,
    ):
        body = generated_text.strip()

        self._validate_placeholders(body)

        return fallback_title, body
