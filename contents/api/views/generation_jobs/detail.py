from drf_spectacular.utils import (
    OpenApiResponse,
    extend_schema,
)
from rest_framework.generics import RetrieveAPIView

from contents.api.responses import api_success

from contents.api.serializers.generation_jobs import (
    GenerationJobSerializer,
)
from contents.api.serializers.system import APIErrorSerializer
from contents.models import GenerationJob
from contents.permissions import HasValidAPIKey

from .common import API_KEY_HEADER


@extend_schema(
    tags=["Generation Jobs"],
    summary="Retrieve generation job details",
    description=(
        "Returns the full status and progress details of one generation "
        "job. Use this endpoint to monitor generated, skipped, remaining, "
        "and current-step values."
    ),
    parameters=[
        API_KEY_HEADER,
    ],
    responses={
        200: OpenApiResponse(
            response=GenerationJobSerializer,
            description="Generation job details.",
        ),
        403: OpenApiResponse(
            response=APIErrorSerializer,
            description="Missing or invalid API key.",
        ),
        404: OpenApiResponse(
            response=APIErrorSerializer,
            description="Generation job not found.",
        ),
    },
)
class GenerationJobDetailAPIView(RetrieveAPIView):
    permission_classes = [HasValidAPIKey]
    serializer_class = GenerationJobSerializer

    def get_queryset(self):
        return GenerationJob.objects.filter(
            external_client=self.request.client,
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        serializer = self.get_serializer(
            instance
        )

        return api_success(
            data={
                "job": serializer.data,
            },
            message="Generation job retrieved successfully.",
        )

