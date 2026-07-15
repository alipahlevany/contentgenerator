from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from contents.api.serializers.datasets import (
    DatasetCollectionSerializer,
    LanguageDatasetSerializer,
    NamedDatasetSerializer,
)
from contents.api.serializers.system import APIErrorSerializer
from contents.models import (
    Audience,
    ContentRule,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)
from contents.permissions import HasValidAPIKey


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

DATASET_TYPE_PARAMETER = OpenApiParameter(
    name="type",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.QUERY,
    required=False,
    enum=[
        "languages",
        "topics",
        "audiences",
        "goals",
        "rules",
        "prompt_templates",
    ],
    description=(
        "Optional dataset type. Leave it empty to return all active "
        "generation datasets."
    ),
)


@extend_schema(
    tags=["Datasets"],
    parameters=[
        API_KEY_HEADER,
        DATASET_TYPE_PARAMETER,
    ],
)
class DatasetAPIView(APIView):
    permission_classes = [HasValidAPIKey]

    dataset_map = {
        "languages": (
            Language,
            LanguageDatasetSerializer,
        ),
        "topics": (
            Topic,
            NamedDatasetSerializer,
        ),
        "audiences": (
            Audience,
            NamedDatasetSerializer,
        ),
        "goals": (
            Goal,
            NamedDatasetSerializer,
        ),
        "rules": (
            ContentRule,
            NamedDatasetSerializer,
        ),
        "prompt_templates": (
            PromptTemplate,
            NamedDatasetSerializer,
        ),
    }

    @extend_schema(
        summary="Retrieve active generation datasets",
        description=(
            "Returns active languages, topics, audiences, goals, content "
            "rules, and prompt templates. Pass the optional `type` query "
            "parameter to retrieve only one dataset group."
        ),
        responses={
            200: OpenApiResponse(
                response=DatasetCollectionSerializer,
                description="Active datasets retrieved successfully.",
            ),
            400: OpenApiResponse(
                response=APIErrorSerializer,
                description="Unsupported dataset type.",
            ),
            403: OpenApiResponse(
                response=APIErrorSerializer,
                description="Missing or invalid API key.",
            ),
        },
        examples=[
            OpenApiExample(
                name="All datasets",
                value={
                    "languages": [
                        {
                            "id": 1,
                            "name": "English",
                            "code": "en",
                        }
                    ],
                    "topics": [
                        {
                            "id": 10,
                            "name": "Technology",
                        }
                    ],
                    "audiences": [],
                    "goals": [],
                    "rules": [],
                    "prompt_templates": [],
                },
                response_only=True,
                status_codes=["200"],
            ),
        ],
    )
    def get(self, request):
        dataset_type = request.query_params.get("type")

        if dataset_type:
            config = self.dataset_map.get(dataset_type)

            if config is None:
                return Response(
                    {
                        "detail": (
                            "Invalid dataset type. Supported values are: "
                            + ", ".join(self.dataset_map.keys())
                            + "."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            model, serializer_class = config

            queryset = (
                model.objects
                .filter(is_active=True)
                .order_by("name")
            )

            return Response(
                {
                    dataset_type: serializer_class(
                        queryset,
                        many=True,
                    ).data
                },
                status=status.HTTP_200_OK,
            )

        response_data = {}

        for key, (model, serializer_class) in self.dataset_map.items():
            queryset = (
                model.objects
                .filter(is_active=True)
                .order_by("name")
            )

            response_data[key] = serializer_class(
                queryset,
                many=True,
            ).data

        return Response(
            response_data,
            status=status.HTTP_200_OK,
        )
