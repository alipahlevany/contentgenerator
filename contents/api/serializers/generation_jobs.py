"""
Compatibility facade for generation job serializers.

Implementation is split into smaller modules while preserving
the existing public import path:

    contents.api.serializers.generation_jobs
"""

from .generation_job_create import GenerationJobCreateSerializer
from .generation_job_fields import DatasetSelectionField
from .generation_job_read import GenerationJobSerializer
from .generation_job_responses import (
    GenerationJobActionResponseSerializer,
)


__all__ = [
    "DatasetSelectionField",
    "GenerationJobCreateSerializer",
    "GenerationJobSerializer",
    "GenerationJobActionResponseSerializer",
]
