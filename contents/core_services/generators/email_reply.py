import re

from contents.core_services.generators.base import (
    BaseGenerator,
    GeneratorOutputError,
)
from contents.core_services.prompt import (
    build_context,
    render_template,
)


class EmailReplyGenerator(BaseGenerator):
    ALLOWED_PLACEHOLDERS = {
        "[[email]]",
        "[[name]]",
        "[[code]]",
        "[[date]]",
    }

    PLACEHOLDER_PATTERN = re.compile(r"\[\[[^\[\]\r\n]+\]\]")

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
        context = build_context(
            app_settings=app_settings,
            language=language,
            topic=topic,
            audience=audience,
            goal=goal,
            selected_rules=selected_rules,
        )

        base_system_prompt = render_template(
            prompt_template.system_prompt,
            context,
        )

        base_user_prompt = render_template(
            prompt_template.user_prompt_template,
            context,
        )

        placeholder_list = ", ".join(sorted(self.ALLOWED_PLACEHOLDERS))

        system_prompt = (
            f"{base_system_prompt}\n\n"
            "Generate only the email reply body.\n"
            "Do not generate a title or subject.\n"
            f"Allowed placeholders: {placeholder_list}.\n"
            "Never create any other placeholder."
        )

        user_prompt = base_user_prompt

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "fallback_title": f"Email Reply - {topic.name}",
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
