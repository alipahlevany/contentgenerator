from pathlib import Path

services_path = Path("contents/services.py")
resolver_path = Path("contents/core_services/dataset_resolver.py")

services = services_path.read_text(encoding="utf-8")

old_import = (
    "from .core_services.job_pool import get_job_generation_pool"
)
new_import = (
    "from .core_services.datasets.job_pool_v2 import "
    "get_job_generation_pool_v2"
)

if old_import not in services:
    raise SystemExit("ERROR: Old job_pool import not found.")

services = services.replace(old_import, new_import, 1)

old_pool_block = '''        (
            languages,
            topics,
            audiences,
            goals,
            prompt_templates,
            content_rules,
        ) = get_job_generation_pool(job)
'''

new_pool_block = '''        generation_pool = get_job_generation_pool_v2(job)
'''

if old_pool_block not in services:
    raise SystemExit("ERROR: Old job pool assignment block not found.")

services = services.replace(
    old_pool_block,
    new_pool_block,
    1,
)

old_log_block = '''        if job.generation_type == "email_reply":
            log_job(
                job,
                "info",
                (
                    "Using email reply generation pool. "
                    f"Languages: {len(languages)}."
                ),
            )
        else:
            log_job(
                job,
                "info",
                (
                    "Using job-specific generation pool. "
                    f"Languages: {len(languages)}, "
                    f"Topics: {len(topics)}, "
                    f"Audiences: {len(audiences)}, "
                    f"Goals: {len(goals)}, "
                    f"PromptTemplates: {len(prompt_templates)}, "
                    f"ContentRules: {len(content_rules)}."
                ),
            )
'''

new_log_block = '''        pool_summary = ", ".join(
            (
                f"{dataset_key}: "
                f"{len(dataset_config['items'])}"
            )
            for dataset_key, dataset_config
            in generation_pool.items()
        )

        log_job(
            job,
            "info",
            (
                "Using Generation V2 dataset pool. "
                f"{pool_summary or 'No datasets configured'}."
            ),
        )
'''

if old_log_block not in services:
    raise SystemExit("ERROR: Old generation pool logging block not found.")

services = services.replace(
    old_log_block,
    new_log_block,
    1,
)

old_resolver_call = '''            context = DatasetResolver.resolve(
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
'''

new_resolver_call = '''            context = DatasetResolver.resolve(
                job=job,
                generator=generator,
                random_module=random,
            )
'''

if old_resolver_call not in services:
    raise SystemExit("ERROR: Old DatasetResolver call not found.")

services = services.replace(
    old_resolver_call,
    new_resolver_call,
    1,
)

services_path.write_text(services, encoding="utf-8")


resolver = resolver_path.read_text(encoding="utf-8")

old_signature = '''    def resolve(
        cls,
        *,
        job,
        languages=None,
        topics=None,
        audiences=None,
        goals=None,
        prompt_templates=None,
        content_rules=None,
        generator,
        random_module,
    ):
        """
        Build one generation context.

        The legacy dataset arguments are intentionally kept temporarily
        for backward compatibility with services.py. They are no longer
        used as the source of truth.
        """
'''

new_signature = '''    def resolve(
        cls,
        *,
        job,
        generator,
        random_module,
    ):
        """
        Build one generation context from the Generation V2 pool.
        """
'''

if old_signature not in resolver:
    raise SystemExit("ERROR: Legacy DatasetResolver signature not found.")

resolver = resolver.replace(
    old_signature,
    new_signature,
    1,
)

resolver_path.write_text(resolver, encoding="utf-8")

print("OK: services.py no longer uses the V1 job pool.")
print("OK: DatasetResolver legacy arguments removed.")
