from django.test import SimpleTestCase, TestCase
from django.urls import resolve, reverse

from rest_framework.test import APIClient, APIRequestFactory

from contents.models import (
    Audience,
    ContentRule,
    ExternalClient,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)
from contents.permissions import HasValidAPIKey


class ImportCompatibilityTests(SimpleTestCase):
    def test_current_view_imports_remain_available(self):
        from contents.views import (
            ContentDetailAPIView,
            ContentExportAPIView,
            ContentListAPIView,
            DatasetAPIView,
            GenerationJobDetailAPIView,
            GenerationJobListCreateAPIView,
            GenerationJobStartAPIView,
            GenerationJobStopAPIView,
            HealthCheckAPIView,
        )

        imported_views = (
            ContentDetailAPIView,
            ContentExportAPIView,
            ContentListAPIView,
            DatasetAPIView,
            GenerationJobDetailAPIView,
            GenerationJobListCreateAPIView,
            GenerationJobStartAPIView,
            GenerationJobStopAPIView,
            HealthCheckAPIView,
        )

        self.assertTrue(all(imported_views))

    def test_current_serializer_imports_remain_available(self):
        from contents.serializers import (
            APIErrorSerializer,
            ContentDetailSerializer,
            ContentExportItemSerializer,
            ContentExportRequestSerializer,
            ContentExportResponseSerializer,
            ContentListSerializer,
            DatasetCollectionSerializer,
            DatasetSelectionField,
            GenerationJobActionResponseSerializer,
            GenerationJobCreateSerializer,
            GenerationJobSerializer,
            HealthCheckSerializer,
            LanguageDatasetSerializer,
            NamedDatasetSerializer,
        )

        imported_serializers = (
            APIErrorSerializer,
            ContentDetailSerializer,
            ContentExportItemSerializer,
            ContentExportRequestSerializer,
            ContentExportResponseSerializer,
            ContentListSerializer,
            DatasetCollectionSerializer,
            DatasetSelectionField,
            GenerationJobActionResponseSerializer,
            GenerationJobCreateSerializer,
            GenerationJobSerializer,
            HealthCheckSerializer,
            LanguageDatasetSerializer,
            NamedDatasetSerializer,
        )

        self.assertTrue(all(imported_serializers))


class URLContractTests(SimpleTestCase):
    expected_routes = {
        "api-health": "api/v1/health/",
        "api-datasets": "api/v1/datasets/",
        "api-generation-job-list-create": "api/v1/generation-jobs/",
        "api-generation-job-detail": "api/v1/generation-jobs/17/",
        "api-generation-job-start": "api/v1/generation-jobs/17/start/",
        "api-generation-job-stop": "api/v1/generation-jobs/17/stop/",
        "api-content-export": "api/v1/contents/export/",
        "api-content-list": "api/v1/contents/",
        "api-content-detail": "api/v1/contents/17/",
    }

    def test_all_current_url_names_reverse_to_exact_routes(self):
        for url_name, route in self.expected_routes.items():
            kwargs = {"pk": 17} if url_name in {
                "api-generation-job-detail",
                "api-content-detail",
            } else None

            if url_name in {
                "api-generation-job-start",
                "api-generation-job-stop",
            }:
                kwargs = {"job_id": 17}

            with self.subTest(url_name=url_name):
                self.assertEqual(
                    reverse(f"contents:{url_name}", kwargs=kwargs),
                    f"/{route}",
                )

    def test_routes_resolve_to_the_exact_current_url_names(self):
        for url_name, route in self.expected_routes.items():
            with self.subTest(route=route):
                match = resolve(f"/{route}")
                self.assertEqual(match.namespace, "contents")
                self.assertEqual(match.url_name, url_name)


class HealthEndpointTests(SimpleTestCase):
    def test_health_endpoint_is_public_and_returns_exact_response(self):
        response = APIClient().get(reverse("contents:api-health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "service": "content-generator",
            },
        )


class APIKeyPermissionTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.permission = HasValidAPIKey()
        self.active_client = ExternalClient.objects.create(
            name="Active client",
            code="active-client",
            api_key="active-api-key",
            is_active=True,
        )
        self.inactive_client = ExternalClient.objects.create(
            name="Inactive client",
            code="inactive-client",
            api_key="inactive-api-key",
            is_active=False,
        )

    def _request(self, api_key=None):
        headers = {}
        if api_key is not None:
            headers["HTTP_X_API_KEY"] = api_key
        return self.factory.get("/api/v1/datasets/", **headers)

    def test_missing_api_key_is_rejected(self):
        request = self._request()

        self.assertFalse(self.permission.has_permission(request, None))
        self.assertFalse(hasattr(request, "client"))

    def test_invalid_api_key_is_rejected(self):
        request = self._request("invalid-api-key")

        self.assertFalse(self.permission.has_permission(request, None))
        self.assertFalse(hasattr(request, "client"))

    def test_inactive_client_api_key_is_rejected(self):
        request = self._request(self.inactive_client.api_key)

        self.assertFalse(self.permission.has_permission(request, None))
        self.assertFalse(hasattr(request, "client"))

    def test_valid_api_key_is_accepted_and_attaches_client(self):
        request = self._request(self.active_client.api_key)

        self.assertTrue(self.permission.has_permission(request, None))
        self.assertEqual(request.client, self.active_client)


class DatasetEndpointTests(TestCase):
    supported_types = (
        "languages",
        "topics",
        "audiences",
        "goals",
        "rules",
        "prompt_templates",
    )

    def setUp(self):
        self.api = APIClient()
        self.url = reverse("contents:api-datasets")
        self.client_record = ExternalClient.objects.create(
            name="Dataset client",
            code="dataset-client",
            api_key="dataset-api-key",
            is_active=True,
        )
        self.inactive_client = ExternalClient.objects.create(
            name="Disabled dataset client",
            code="disabled-dataset-client",
            api_key="disabled-dataset-api-key",
            is_active=False,
        )

        self.language_zulu = Language.objects.create(
            name="Zulu",
            code="zu",
            is_active=True,
        )
        self.language_english = Language.objects.create(
            name="English",
            code="en",
            is_active=True,
        )
        Language.objects.create(
            name="Inactive Language",
            code="xx",
            is_active=False,
        )

        self.topic_zulu = Topic.objects.create(name="Zulu Topic", is_active=True)
        self.topic_alpha = Topic.objects.create(name="Alpha Topic", is_active=True)
        Topic.objects.create(name="Inactive Topic", is_active=False)

        self.audience_zulu = Audience.objects.create(
            name="Zulu Audience", is_active=True
        )
        self.audience_alpha = Audience.objects.create(
            name="Alpha Audience", is_active=True
        )
        Audience.objects.create(name="Inactive Audience", is_active=False)

        self.goal_zulu = Goal.objects.create(name="Zulu Goal", is_active=True)
        self.goal_alpha = Goal.objects.create(name="Alpha Goal", is_active=True)
        Goal.objects.create(name="Inactive Goal", is_active=False)

        self.rule_zulu = ContentRule.objects.create(
            name="Zulu Rule", prompt_text="Zulu", is_active=True
        )
        self.rule_alpha = ContentRule.objects.create(
            name="Alpha Rule", prompt_text="Alpha", is_active=True
        )
        ContentRule.objects.create(
            name="Inactive Rule", prompt_text="Inactive", is_active=False
        )

        self.template_zulu = PromptTemplate.objects.create(
            name="Zulu Template",
            system_prompt="System Zulu",
            user_prompt_template="User Zulu",
            is_active=True,
        )
        self.template_alpha = PromptTemplate.objects.create(
            name="Alpha Template",
            system_prompt="System Alpha",
            user_prompt_template="User Alpha",
            is_active=True,
        )
        PromptTemplate.objects.create(
            name="Inactive Template",
            system_prompt="Inactive",
            user_prompt_template="Inactive",
            is_active=False,
        )

        self.expected = {
            "languages": [
                {"id": self.language_english.id, "name": "English", "code": "en"},
                {"id": self.language_zulu.id, "name": "Zulu", "code": "zu"},
            ],
            "topics": [
                {"id": self.topic_alpha.id, "name": "Alpha Topic"},
                {"id": self.topic_zulu.id, "name": "Zulu Topic"},
            ],
            "audiences": [
                {"id": self.audience_alpha.id, "name": "Alpha Audience"},
                {"id": self.audience_zulu.id, "name": "Zulu Audience"},
            ],
            "goals": [
                {"id": self.goal_alpha.id, "name": "Alpha Goal"},
                {"id": self.goal_zulu.id, "name": "Zulu Goal"},
            ],
            "rules": [
                {"id": self.rule_alpha.id, "name": "Alpha Rule"},
                {"id": self.rule_zulu.id, "name": "Zulu Rule"},
            ],
            "prompt_templates": [
                {"id": self.template_alpha.id, "name": "Alpha Template"},
                {"id": self.template_zulu.id, "name": "Zulu Template"},
            ],
        }

    def _get(self, *, api_key=None, dataset_type=None):
        headers = {}
        if api_key is not None:
            headers["HTTP_X_API_KEY"] = api_key
        data = {} if dataset_type is None else {"type": dataset_type}
        return self.api.get(self.url, data, **headers)

    def test_missing_api_key_returns_exact_forbidden_response(self):
        response = self._get()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {"detail": "Authentication credentials were not provided."},
        )

    def test_invalid_api_key_returns_exact_forbidden_response(self):
        response = self._get(api_key="invalid-api-key")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {"detail": "Authentication credentials were not provided."},
        )

    def test_inactive_api_key_returns_exact_forbidden_response(self):
        response = self._get(api_key=self.inactive_client.api_key)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {"detail": "Authentication credentials were not provided."},
        )

    def test_valid_api_key_returns_all_active_datasets_in_exact_structure(self):
        response = self._get(api_key=self.client_record.api_key)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.expected)

    def test_each_supported_type_returns_only_that_active_ordered_dataset(self):
        for dataset_type in self.supported_types:
            with self.subTest(dataset_type=dataset_type):
                response = self._get(
                    api_key=self.client_record.api_key,
                    dataset_type=dataset_type,
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.json(),
                    {dataset_type: self.expected[dataset_type]},
                )

    def test_unsupported_type_returns_exact_bad_request_response(self):
        response = self._get(
            api_key=self.client_record.api_key,
            dataset_type="unsupported",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {
                "detail": (
                    "Invalid dataset type. Supported values are: "
                    "languages, topics, audiences, goals, rules, "
                    "prompt_templates."
                )
            },
        )
