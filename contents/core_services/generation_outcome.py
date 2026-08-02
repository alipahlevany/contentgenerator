from contents.core_services.dataset_manager import run_dataset_refill
from contents.core_services.intelligence import record_generation_event
from contents.core_services.logger import log_job
from contents.core_services.runner import increment_skipped
from contents.core_services.weight_optimizer import optimize_dataset_weights


def is_email_reply_job(job):
    return job.generation_type == "email_reply"


def uses_dataset_intelligence(job):
    """
    Dataset intelligence currently applies only to standard
    content generation.

    Lightweight generation types such as email_reply and
    greeting intentionally do not use Topic, Audience, Goal,
    PromptTemplate, refill, or weight optimization.
    """
    return job.generation_type == "standard"


def _dataset_name(value):
    if value is None:
        return None

    return getattr(
        value,
        "name",
        str(value),
    )


def _build_generation_context_label(
    *,
    language,
    topic,
    audience,
    goal,
    prompt_template,
):
    values = (
        language,
        topic,
        audience,
        goal,
        prompt_template,
    )

    names = [
        _dataset_name(value)
        for value in values
        if value is not None
    ]

    return " | ".join(names)


def handle_generation_failure(
    job,
    app_settings,
    event_type,
    language,
    topic,
    audience,
    goal,
    prompt_template,
    message,
    failure_kind=None,
):
    increment_skipped(job)

    update_fields = []

    if failure_kind == "duplicate":
        job.duplicate_count += 1
        update_fields.append("duplicate_count")
    elif failure_kind == "empty":
        job.empty_output_count += 1
        update_fields.append("empty_output_count")
    else:
        job.failed_count += 1
        update_fields.append("failed_count")

    job.save(
        update_fields=update_fields + ["updated_at"]
    )

    log_job(
        job,
        "warning"
        if event_type in ["duplicate", "blocked"]
        else "error",
        message,
    )

    # Lightweight generation types do not participate
    # in standard dataset intelligence.
    if not uses_dataset_intelligence(job):
        return

    record_generation_event(
        event_type=event_type,
        job=job,
        language=language,
        topic=topic,
        audience=audience,
        goal=goal,
        prompt_template=prompt_template,
        message=message,
    )

    run_dataset_refill(
        job=job,
        app_settings=app_settings,
    )

    optimize_dataset_weights()


def handle_generation_success(
    job,
    language,
    topic,
    audience,
    goal,
    prompt_template,
    content,
):
    context_label = _build_generation_context_label(
        language=language,
        topic=topic,
        audience=audience,
        goal=goal,
        prompt_template=prompt_template,
    )

    if is_email_reply_job(job):
        log_job(
            job,
            "success",
            (
                f"Generated email reply #{content.id}: "
                f"{context_label}"
            ),
        )
        return

    if not uses_dataset_intelligence(job):
        log_job(
            job,
            "success",
            (
                f"Generated {job.generation_type} "
                f"content #{content.id}: "
                f"{context_label}"
            ),
        )
        return

    record_generation_event(
        event_type="success",
        job=job,
        language=language,
        topic=topic,
        audience=audience,
        goal=goal,
        prompt_template=prompt_template,
        content=content,
        message="Content generated successfully.",
    )

    log_job(
        job,
        "success",
        (
            f"Generated content #{content.id}: "
            f"{context_label}"
        ),
    )

    optimize_dataset_weights()
