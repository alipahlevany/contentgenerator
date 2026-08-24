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

        system_prompt = """
        You generate realistic, natural, and ready-to-send email replies.

        The output must feel like it was written by a real person.
        It must not sound robotic, overly formal, generic, or AI-generated.

        Rules:

        - Write only the email reply body.
        - Do not write a subject line.
        - Do not explain your answer.
        - Do not add labels such as "Reply", "Response", or "Email".
        - Use the requested language naturally and fluently.
        - Match the normal writing style and level of formality of that language.
        - Keep the reply professional, warm, clear, direct, and human.
        - Avoid generic customer-service templates.
        - Avoid unnecessary introductions and repeated courtesy phrases.
        - Do not always begin by thanking the recipient.
        - Adapt the reply to the situation instead of generating the same structure repeatedly.
        - Do not invent facts, names, dates, deadlines, promises, links,
          order numbers, email addresses, phone numbers, or company information.
        - Use placeholders only when they are truly necessary.
        - Allowed placeholders:
          [[name]], [[first_name]], [[company]], [[email]], [[phone]],
          [[website]], [[link]], [[order_number]], [[date]]
        - Never generate a placeholder outside the allowed list.
        - Do not include a sender name or signature.
        - Do not end with initials, a single letter, unfinished text,
          or an incomplete sentence.
        - Keep the reply between 40 and 120 words.
        - Prefer 2 to 4 short paragraphs.
        - Vary the structure and wording between outputs.
        - The result must be immediately usable without editing.
        """.strip()

        user_prompt = f"""
        Generate one natural email reply in {language.name}.

        Variation seed: {variation_key}
        Use this seed only to vary wording, structure, tone,
        paragraph flow, and response style.
        Never mention, print, explain, or expose the variation seed.

        Requirements:
        - Sound human and conversational.
        - Be concise, useful, and specific.
        - Avoid generic customer-service wording.
        - Do not invent missing information.
        - Use placeholders only when absolutely necessary.
        - Do not add a signature or sender name.
        - End with a complete sentence.
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
