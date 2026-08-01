"""
Public generation service compatibility layer.

Generation job orchestration lives in:
    contents.core_services.generation.job_service

Keep this module as the stable public import path for existing
tasks, tests, and integrations.
"""

from contents.core_services.generation.job_service import (
    run_generation_job,
)


__all__ = [
    "run_generation_job",
]
