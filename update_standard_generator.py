from pathlib import Path

path = Path("contents/core_services/generators/standard.py")

text = path.read_text(encoding="utf-8")

if "def get_pool_log_message" in text:
    print("Already updated.")
    raise SystemExit

insert = '''
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

'''

marker = "class StandardGenerator(BaseGenerator):\n"
text = text.replace(marker, marker + insert)

path.write_text(text, encoding="utf-8")

print("OK: StandardGenerator updated.")
