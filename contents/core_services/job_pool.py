from .selector import get_optional_pool, get_required_pool
from ..models import (
    Audience,
    ContentRule,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)


def _selected_active_items(relation):
    return list(
        relation.filter(is_active=True)
        .order_by("id")
    )


def _required_job_pool(
    job,
    *,
    use_all_field,
    relation_name,
    model,
    label,
):
    if getattr(job, use_all_field):
        return get_required_pool(model, label)

    selected_items = _selected_active_items(
        getattr(job, relation_name)
    )

    if selected_items:
        return selected_items

    # Backward compatibility for old jobs created before per-job
    # dataset selection was introduced.
    return get_required_pool(model, label)


def _prompt_template_pool(job):
    if job.use_all_prompt_templates:
        return get_required_pool(
            PromptTemplate,
            "prompt templates",
        )

    selected_templates = _selected_active_items(
        job.prompt_templates
    )

    if selected_templates:
        return selected_templates

    if (
        job.prompt_template_id
        and job.prompt_template
        and job.prompt_template.is_active
    ):
        return [job.prompt_template]

    return get_required_pool(
        PromptTemplate,
        "prompt templates",
    )


def _content_rule_pool(job):
    if job.use_all_rules:
        return get_optional_pool(ContentRule)

    return _selected_active_items(job.rules)


def get_job_generation_pool(job):
    """
    Return the datasets that are allowed for one generation job.

    Selection rules:
    - use_all_* = True: use every active item.
    - Explicit M2M selections: use only those active items.
    - Empty required selections on legacy jobs: fall back to all active.
    - Empty rules selection: use no content rules.
    - prompt_template is used as a fallback when prompt_templates is empty.
    """
    languages = _required_job_pool(
        job,
        use_all_field="use_all_languages",
        relation_name="languages",
        model=Language,
        label="languages",
    )

    topics = _required_job_pool(
        job,
        use_all_field="use_all_topics",
        relation_name="topics",
        model=Topic,
        label="topics",
    )

    audiences = _required_job_pool(
        job,
        use_all_field="use_all_audiences",
        relation_name="audiences",
        model=Audience,
        label="audiences",
    )

    goals = _required_job_pool(
        job,
        use_all_field="use_all_goals",
        relation_name="goals",
        model=Goal,
        label="goals",
    )

    prompt_templates = _prompt_template_pool(job)
    content_rules = _content_rule_pool(job)

    return (
        languages,
        topics,
        audiences,
        goals,
        prompt_templates,
        content_rules,
    )
