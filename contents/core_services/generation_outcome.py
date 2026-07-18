from contents.core_services.dataset_manager import run_dataset_refill
from contents.core_services.intelligence import record_generation_event
from contents.core_services.logger import log_job
from contents.core_services.runner import increment_skipped
from contents.core_services.weight_optimizer import optimize_dataset_weights
from contents.core_services.intelligence_scheduler import maybe_run_intelligence_optimization


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
    job.save(update_fields=update_fields + ["updated_at"])

    log_job(
        job,
        "warning" if event_type in ["duplicate", "blocked"] else "error",
        message,
    )

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
            f"{language.name} | {topic.name} | "
            f"{audience.name} | {goal.name} | "
            f"{prompt_template.name}"
        ),
    )

    optimize_dataset_weights()
