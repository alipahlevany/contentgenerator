from pathlib import Path

services_path = Path("contents/services.py")
services = services_path.read_text(encoding="utf-8")

validator_import = '''from .core_services.pipeline.validator import (
    validate_content_body,
    validate_final_blocked_keyword,
    validate_generated_text,
)
'''

anchor_import = '''from .core_services.pipeline.blocked_keywords import (
    contains_blocked_keyword,
    remove_blocked_keywords,
)
'''

if validator_import not in services:
    if anchor_import not in services:
        raise SystemExit(
            "ERROR: blocked keywords pipeline import not found."
        )

    services = services.replace(
        anchor_import,
        anchor_import + validator_import,
        1,
    )

old_generated_validation = '''            if not generated_text or not generated_text.strip():
                handle_generation_failure(
                    job=job,
                    app_settings=app_settings,
                    event_type="error",
                    language=language,
                    topic=topic,
                    audience=audience,
                    goal=goal,
                    prompt_template=prompt_template,
                    message="OpenAI returned empty content.",
                    failure_kind="empty",
                )
                continue
'''

new_generated_validation = '''            generated_validation = validate_generated_text(
                generated_text
            )

            if not generated_validation.ok:
                handle_generation_failure(
                    job=job,
                    app_settings=app_settings,
                    event_type=generated_validation.event_type,
                    language=language,
                    topic=topic,
                    audience=audience,
                    goal=goal,
                    prompt_template=prompt_template,
                    message=generated_validation.message,
                    failure_kind=generated_validation.failure_kind,
                )
                continue
'''

if old_generated_validation not in services:
    raise SystemExit(
        "ERROR: raw generated text validation block not found."
    )

services = services.replace(
    old_generated_validation,
    new_generated_validation,
    1,
)

old_body_validation = '''            if not content_body:
                handle_generation_failure(
                    job=job,
                    app_settings=app_settings,
                    event_type="blocked",
                    language=language,
                    topic=topic,
                    audience=audience,
                    goal=goal,
                    prompt_template=prompt_template,
                    message=(
                        "Content body became empty after cleanup."
                    ),
                    failure_kind="empty",
                )
                continue
'''

new_body_validation = '''            body_validation = validate_content_body(
                content_body
            )

            if not body_validation.ok:
                handle_generation_failure(
                    job=job,
                    app_settings=app_settings,
                    event_type=body_validation.event_type,
                    language=language,
                    topic=topic,
                    audience=audience,
                    goal=goal,
                    prompt_template=prompt_template,
                    message=body_validation.message,
                    failure_kind=body_validation.failure_kind,
                )
                continue
'''

if old_body_validation not in services:
    raise SystemExit(
        "ERROR: content body validation block not found."
    )

services = services.replace(
    old_body_validation,
    new_body_validation,
    1,
)

old_final_validation = '''            if final_has_blocked:
                handle_generation_failure(
                    job=job,
                    app_settings=app_settings,
                    event_type="blocked",
                    language=language,
                    topic=topic,
                    audience=audience,
                    goal=goal,
                    prompt_template=prompt_template,
                    message=(
                        "Blocked keyword found after final extraction: "
                        f"{final_blocked_keyword}"
                    ),
                        failure_kind="failed",
                )
                continue
'''

new_final_validation = '''            final_validation = validate_final_blocked_keyword(
                final_has_blocked,
                final_blocked_keyword,
            )

            if not final_validation.ok:
                handle_generation_failure(
                    job=job,
                    app_settings=app_settings,
                    event_type=final_validation.event_type,
                    language=language,
                    topic=topic,
                    audience=audience,
                    goal=goal,
                    prompt_template=prompt_template,
                    message=final_validation.message,
                    failure_kind=final_validation.failure_kind,
                )
                continue
'''

if old_final_validation not in services:
    raise SystemExit(
        "ERROR: final blocked keyword validation block not found."
    )

services = services.replace(
    old_final_validation,
    new_final_validation,
    1,
)

services_path.write_text(
    services,
    encoding="utf-8",
)

print("OK: Validator connected to services.py.")
print("OK: Raw output validation extracted.")
print("OK: Content body validation extracted.")
print("OK: Final blocked keyword validation extracted.")
