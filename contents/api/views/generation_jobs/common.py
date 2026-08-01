from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter


API_KEY_HEADER = OpenApiParameter(
    name="X-API-Key",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=True,
    description=(
        "External API key generated in Django Admin under "
        "System Settings. Include this header in every protected request."
    ),
)

JOB_ID_PARAMETER = OpenApiParameter(
    name="job_id",
    type=OpenApiTypes.INT,
    location=OpenApiParameter.PATH,
    required=True,
    description="Unique numeric ID of the generation job.",
)
