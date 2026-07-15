from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from contents.api.serializers.system import HealthCheckSerializer


@extend_schema(
    tags=["System"],
    summary="Check API health",
    description=(
        "Public health-check endpoint used to verify that the "
        "Content Generator API is online and responding."
    ),
    auth=[],
    responses={
        200: OpenApiResponse(
            response=HealthCheckSerializer,
            description="The API service is online.",
        ),
    },
    examples=[
        OpenApiExample(
            name="Healthy service",
            value={
                "status": "ok",
                "service": "content-generator",
            },
            response_only=True,
            status_codes=["200"],
        ),
    ],
)
class HealthCheckAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                "status": "ok",
                "service": "content-generator",
            },
            status=status.HTTP_200_OK,
        )
