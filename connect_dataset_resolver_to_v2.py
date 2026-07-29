from pathlib import Path

path = Path("contents/core_services/dataset_resolver.py")

path.write_text(
'''from contents.core_services.datasets.job_pool_v2 import (
    get_job_generation_pool_v2,
)
from contents.core_services.selector import (
    intelligent_generation_choice,
    weighted_sample,
)


class DatasetResolver:
    """
    Resolve the datasets and selected context for one generation run.

    Dataset availability is defined by:
        GenerationType
        -> GenerationTypeDataset
        -> Dataset Registry
        -> Job Pool V2

    The existing generator selection behavior is preserved.
    """

    @staticmethod
    def _items(pool, dataset_key):
        """
        Return the loaded items for one dataset category.

        Dataset categories not configured for the current generation type
        return an empty list.
        """
        dataset = pool.get(dataset_key)

        if dataset is None:
            return []

        return dataset["items"]

    @classmethod
    def resolve(
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
        pool = get_job_generation_pool_v2(job)

        v2_languages = cls._items(pool, "language")
        v2_topics = cls._items(pool, "topic")
        v2_audiences = cls._items(pool, "audience")
        v2_goals = cls._items(pool, "goal")
        v2_prompt_templates = cls._items(
            pool,
            "prompt_template",
        )
        v2_content_rules = cls._items(
            pool,
            "content_rule",
        )

        context = generator.select_generation_context(
            languages=v2_languages,
            topics=v2_topics,
            audiences=v2_audiences,
            goals=v2_goals,
            prompt_templates=v2_prompt_templates,
            intelligent_generation_choice=intelligent_generation_choice,
            random_module=random_module,
        )

        if context["selected_rules"] is None:
            context["selected_rules"] = weighted_sample(
                v2_content_rules,
                max_count=3,
            )

        return context
''',
    encoding="utf-8",
)

print("OK: DatasetResolver connected to Job Pool V2.")
