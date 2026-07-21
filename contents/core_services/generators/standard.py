from contents.core_services.generators.base import BaseGenerator
from contents.core_services.prompt import (
    build_context,
    extract_title_and_content,
    render_template,
)


class StandardGenerator(BaseGenerator):
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

        system_prompt = render_template(
            prompt_template.system_prompt,
            context,
        )

        user_prompt = render_template(
            prompt_template.user_prompt_template,
            context,
        )

        fallback_title = f"{topic.name} for {audience.name}"

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "fallback_title": fallback_title,
        }

    def extract_output(
        self,
        generated_text,
        fallback_title,
    ):
        return extract_title_and_content(
            generated_text,
            fallback_title,
        )