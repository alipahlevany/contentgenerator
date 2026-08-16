from contents.core_services.generators.base import BaseGenerator
from contents.core_services.prompt import (
    build_context,
    extract_title_and_content,
    render_template,
)


class StandardGenerator(BaseGenerator):

    def get_pool_log_message(
        self,
        languages,
        topics,
        audiences,
        goals,
        prompt_templates,
        content_rules,
    ):
        return (
            "Using job-specific generation pool. "
            f"Languages: {len(languages)}, "
            f"Topics: {len(topics)}, "
            f"Audiences: {len(audiences)}, "
            f"Goals: {len(goals)}, "
            f"PromptTemplates: {len(prompt_templates)}, "
            f"ContentRules: {len(content_rules)}."
        )

    def select_generation_context(
        self,
        *,
        languages,
        topics,
        audiences,
        goals,
        prompt_templates,
        intelligent_generation_choice,
        **kwargs,
    ):
        language, topic, audience, goal, prompt_template = intelligent_generation_choice(
            languages=languages,
            topics=topics,
            audiences=audiences,
            goals=goals,
            prompt_templates=prompt_templates,
        )

        return {
            "language": language,
            "topic": topic,
            "audience": audience,
            "goal": goal,
            "prompt_template": prompt_template,
            "selected_rules": None,
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