from contents.core_services.selector import (
    intelligent_generation_choice,
    weighted_sample,
)


class DatasetResolver:
    """
    Resolves all datasets required for a generation run.

    Today:
        Uses the existing selector logic.

    Future:
        Will read GenerationTypeDataset configuration from the database.
    """

    @staticmethod
    def resolve(
        *,
        job,
        languages,
        topics,
        audiences,
        goals,
        prompt_templates,
        content_rules,
        generator,
        random_module,
    ):
        context = generator.select_generation_context(
            languages=languages,
            topics=topics,
            audiences=audiences,
            goals=goals,
            prompt_templates=prompt_templates,
            intelligent_generation_choice=intelligent_generation_choice,
            random_module=random_module,
        )

        if context["selected_rules"] is None:
            context["selected_rules"] = weighted_sample(
                content_rules,
                max_count=3,
            )

        return context
