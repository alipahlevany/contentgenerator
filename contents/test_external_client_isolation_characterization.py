import inspect
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from rest_framework.test import APIClient, APIRequestFactory

from contents.models import (
    Audience,
    Content,
    ContentExport,
    ContentRule,
    ExternalClient,
    GenerationJob,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)
from contents.permissions import HasValidAPIKey
from contents.tasks import send_model_data_to_api


class ExternalClientIsolationCharacterizationTests(TestCase):
    authentication_error = {
        "detail": "Authentication credentials were not provided."
    }

    @classmethod
    def setUpTestData(cls):
        cls.client_a = ExternalClient.objects.create(
            name="Client A",
            code="client-a",
            api_key="plain-api-key-a",
            callback_url="https://client-a.example/callback/",
        )
        cls.client_b = ExternalClient.objects.create(
            name="Client B",
            code="client-b",
            api_key="plain-api-key-b",
            callback_url="https://client-b.example/callback/",
        )

        cls.language = Language.objects.create(name="English", code="en")
        cls.topic = Topic.objects.create(name="Technology")
        cls.audience = Audience.objects.create(name="Developers")
        cls.goal = Goal.objects.create(name="Education")
        cls.rule = ContentRule.objects.create(
            name="No hype",
            prompt_text="Do not use hype.",
        )
        cls.template = PromptTemplate.objects.create(
            name="Standard",
            system_prompt="System prompt",
            user_prompt_template="User prompt",
        )

    def setUp(self):
        self.api = APIClient()
        self.datasets_url = reverse("contents:api-datasets")
        self.export_url = reverse("contents:api-content-export")
        self.jobs_url = reverse("contents:api-generation-job-list-create")

    @staticmethod
    def headers(client):
        return {"HTTP_X_API_KEY": client.api_key}

    def create_content(self, suffix="one"):
        return Content.objects.create(
            title=f"Content {suffix}",
            language=self.language,
            topic=self.topic,
            audience=self.audience,
            goal=self.goal,
            prompt_template=self.template,
            prompt=f"Prompt {suffix}",
            generated_content=f"Body {suffix}",
            content_hash=f"hash-{suffix}",
            status="generated",
        )

    def create_job_through_client_b(self, payload=None):
        with patch("contents.views.run_generation_job_task.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.api.post(
                    self.jobs_url,
                    payload or {},
                    format="json",
                    **self.headers(self.client_b),
                )

        self.assertEqual(response.status_code, 201)
        delay.assert_called_once()
        return GenerationJob.objects.get(pk=response.json()["job"]["id"])

    def test_each_client_authenticates_and_permission_sets_request_client(self):
        factory = APIRequestFactory()
        permission = HasValidAPIKey()

        for external_client in (self.client_a, self.client_b):
            with self.subTest(client=external_client.code):
                response = self.api.get(
                    self.datasets_url,
                    **self.headers(external_client),
                )
                self.assertEqual(response.status_code, 200)

                request = factory.get(
                    self.datasets_url,
                    **self.headers(external_client),
                )
                self.assertTrue(permission.has_permission(request, None))
                self.assertEqual(request.client, external_client)

    def test_api_key_validation_errors_are_exact(self):
        cases = (
            ("missing", {}),
            ("invalid", {"HTTP_X_API_KEY": "not-a-real-key"}),
        )

        for label, headers in cases:
            with self.subTest(case=label):
                response = self.api.get(self.datasets_url, **headers)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), self.authentication_error)

    def test_inactive_client_loses_access_immediately(self):
        self.assertEqual(
            self.api.get(
                self.datasets_url,
                **self.headers(self.client_a),
            ).status_code,
            200,
        )

        self.client_a.is_active = False
        self.client_a.save(update_fields=["is_active", "updated_at"])

        response = self.api.get(
            self.datasets_url,
            HTTP_X_API_KEY="plain-api-key-a",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), self.authentication_error)

    def test_changing_api_key_immediately_invalidates_old_key(self):
        self.client_a.api_key = "replacement-plain-api-key-a"
        self.client_a.save(update_fields=["api_key", "updated_at"])

        old_response = self.api.get(
            self.datasets_url,
            HTTP_X_API_KEY="plain-api-key-a",
        )
        new_response = self.api.get(
            self.datasets_url,
            HTTP_X_API_KEY="replacement-plain-api-key-a",
        )

        self.assertEqual(old_response.status_code, 403)
        self.assertEqual(old_response.json(), self.authentication_error)
        self.assertEqual(new_response.status_code, 200)

    def test_legacy_api_keys_are_stored_and_queried_as_plaintext(self):
        stored_key = ExternalClient.objects.values_list(
            "api_key",
            flat=True,
        ).get(pk=self.client_a.pk)
        self.assertEqual(stored_key, "plain-api-key-a")

        field = ExternalClient._meta.get_field("api_key")
        self.assertEqual(field.get_internal_type(), "CharField")
        self.assertTrue(field.unique)
        self.assertTrue(field.db_index)

        request = APIRequestFactory().get(
            self.datasets_url,
            **self.headers(self.client_a),
        )
        with CaptureQueriesContext(connection) as queries:
            self.assertTrue(HasValidAPIKey().has_permission(request, None))

        self.assertTrue(
            any("plain-api-key-a" in query["sql"] for query in queries)
        )

    def test_export_history_is_per_client_and_content_remains_eligible_for_b(self):
        content = self.create_content()

        response_a = self.api.post(
            self.export_url,
            {},
            format="json",
            **self.headers(self.client_a),
        )
        response_a_again = self.api.post(
            self.export_url,
            {},
            format="json",
            **self.headers(self.client_a),
        )
        response_b = self.api.post(
            self.export_url,
            {},
            format="json",
            **self.headers(self.client_b),
        )

        self.assertEqual(response_a.status_code, 200)
        self.assertEqual(response_a.json()["client"], "client-a")
        self.assertEqual(response_a.json()["exported"], 1)
        self.assertEqual(response_a_again.status_code, 200)
        self.assertEqual(response_a_again.json()["exported"], 0)
        self.assertEqual(response_b.status_code, 200)
        self.assertEqual(response_b.json()["client"], "client-b")
        self.assertEqual(response_b.json()["exported"], 1)

        exports = ContentExport.objects.filter(content=content).order_by("client_id")
        self.assertEqual(exports.count(), 2)
        self.assertEqual(
            set(exports.values_list("client_id", flat=True)),
            {self.client_a.id, self.client_b.id},
        )

    def test_client_a_cannot_list_or_retrieve_job_created_through_client_b(self):
        job = self.create_job_through_client_b()

        list_response = self.api.get(
            self.jobs_url,
            **self.headers(self.client_a),
        )
        detail_response = self.api.get(
            reverse("contents:api-generation-job-detail", kwargs={"pk": job.pk}),
            **self.headers(self.client_a),
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertNotIn(job.pk, [item["id"] for item in list_response.json()])
        self.assertEqual(detail_response.status_code, 404)
        self.assertEqual(
            detail_response.json(),
            {"detail": "No GenerationJob matches the given query."},
        )

    def test_client_a_cannot_start_job_created_through_client_b(self):
        job = self.create_job_through_client_b()

        with patch("contents.views.run_generation_job_task.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.api.post(
                    reverse(
                        "contents:api-generation-job-start",
                        kwargs={"job_id": job.pk},
                    ),
                    format="json",
                    **self.headers(self.client_a),
                )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {"detail": "No GenerationJob matches the given query."},
        )
        delay.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.status, "pending")

    def test_client_a_cannot_stop_job_created_through_client_b(self):
        job = self.create_job_through_client_b()

        response = self.api.post(
            reverse(
                "contents:api-generation-job-stop",
                kwargs={"job_id": job.pk},
            ),
            format="json",
            **self.headers(self.client_a),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {"detail": "No GenerationJob matches the given query."},
        )
        job.refresh_from_db()
        self.assertEqual(job.status, "pending")
        self.assertFalse(job.should_stop)

    def test_api_created_job_stores_authenticated_client_ownership(self):
        job = self.create_job_through_client_b()
        field_names = {field.name for field in GenerationJob._meta.get_fields()}

        self.assertIn("external_client", field_names)
        self.assertEqual(job.external_client, self.client_b)

    def test_request_payload_cannot_override_authenticated_owner(self):
        job = self.create_job_through_client_b(
            {
                "external_client": self.client_a.pk,
                "external_client_id": self.client_a.pk,
            }
        )

        self.assertEqual(job.external_client, self.client_b)

    def test_client_b_can_list_retrieve_start_and_stop_its_own_job(self):
        job = self.create_job_through_client_b()

        list_response = self.api.get(
            self.jobs_url,
            **self.headers(self.client_b),
        )
        detail_response = self.api.get(
            reverse("contents:api-generation-job-detail", kwargs={"pk": job.pk}),
            **self.headers(self.client_b),
        )
        with patch("contents.views.run_generation_job_task.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                start_response = self.api.post(
                    reverse(
                        "contents:api-generation-job-start",
                        kwargs={"job_id": job.pk},
                    ),
                    format="json",
                    **self.headers(self.client_b),
                )
        stop_response = self.api.post(
            reverse(
                "contents:api-generation-job-stop",
                kwargs={"job_id": job.pk},
            ),
            format="json",
            **self.headers(self.client_b),
        )

        self.assertIn(job.pk, [item["id"] for item in list_response.json()])
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(start_response.status_code, 200)
        delay.assert_called_once_with(job.pk)
        self.assertEqual(stop_response.status_code, 200)
        job.refresh_from_db()
        self.assertEqual(job.status, "stopped")
        self.assertTrue(job.should_stop)

    def test_legacy_unowned_job_is_hidden_from_all_job_endpoints(self):
        job = GenerationJob.objects.create()

        list_response = self.api.get(
            self.jobs_url,
            **self.headers(self.client_a),
        )
        detail_response = self.api.get(
            reverse("contents:api-generation-job-detail", kwargs={"pk": job.pk}),
            **self.headers(self.client_a),
        )
        with patch("contents.views.run_generation_job_task.delay") as delay:
            start_response = self.api.post(
                reverse(
                    "contents:api-generation-job-start",
                    kwargs={"job_id": job.pk},
                ),
                format="json",
                **self.headers(self.client_a),
            )
        stop_response = self.api.post(
            reverse(
                "contents:api-generation-job-stop",
                kwargs={"job_id": job.pk},
            ),
            format="json",
            **self.headers(self.client_a),
        )

        self.assertNotIn(job.pk, [item["id"] for item in list_response.json()])
        for response in (detail_response, start_response, stop_response):
            self.assertEqual(response.status_code, 404)
            self.assertEqual(
                response.json(),
                {"detail": "No GenerationJob matches the given query."},
            )
        delay.assert_not_called()

    def test_internal_job_creation_remains_valid_without_owner(self):
        job = GenerationJob.objects.create(count=17)

        self.assertIsNone(job.external_client)

    def test_content_delivery_ignores_clients_and_callback_urls(self):
        with patch("contents.tasks.send_model_data_to_api.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                self.create_content("delivery")

        delay.assert_called_once_with(
            "Content delivery",
            "Body delivery",
            "Technology",
        )

        model_source = inspect.getsource(Content.save)
        task_source = inspect.getsource(send_model_data_to_api)
        combined_source = model_source + task_source

        self.assertNotIn("callback_url", combined_source)
        self.assertNotIn("ExternalClient", combined_source)
        self.assertIn(
            'url = "https://melal.org/createContentAPIView/"',
            task_source,
        )
        self.assertIn('os.getenv("mta_api_key")', task_source)
