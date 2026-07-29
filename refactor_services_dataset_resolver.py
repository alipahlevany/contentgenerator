from pathlib import Path

path = Path("contents/services.py")
text = path.read_text(encoding="utf-8")

# Add import
import_line = "from .core_services.dataset_resolver import DatasetResolver\n"

if import_line not in text:
    marker = "from .core_services.delivery_queue import queue_content_deliveries\n"
    text = text.replace(marker, marker + import_line)

old = '''            if job.generation_type == "email_reply":
                language = random.choice(languages)
                topic = None
                audience = None
                goal = None
                prompt_template = None
                selected_rules = []
            else:
                (
                    language,
                    topic,
                    audience,
                    goal,
                    prompt_template,
                ) = intelligent_generation_choice(
                    languages=languages,
                    topics=topics,
                    audiences=audiences,
                    goals=goals,
                    prompt_templates=prompt_templates,
                )

                selected_rules = weighted_sample(
                    content_rules,
                    max_count=3,
                )
'''

new = '''            context = DatasetResolver.resolve(
                job=job,
                languages=languages,
                topics=topics,
                audiences=audiences,
                goals=goals,
                prompt_templates=prompt_templates,
                content_rules=content_rules,
                generator=generator,
                random_module=random,
            )

            language = context["language"]
            topic = context["topic"]
            audience = context["audience"]
            goal = context["goal"]
            prompt_template = context["prompt_template"]
            selected_rules = context["selected_rules"]
'''

if old not in text:
    raise SystemExit("Target block not found. No changes made.")

text = text.replace(old, new)

path.write_text(text, encoding="utf-8")

print("OK: services.py refactored to use DatasetResolver.")
