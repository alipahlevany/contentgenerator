from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APIClient

from contents.models import (
    APIIdempotencyRecord,
    Audience,
    Content,
    ExternalClient,
    GenerationJob,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)


class IdempotencyFixtureMixin:
    @classmethod
    def create_fixtures(cls):
        cls.client_record = ExternalClient.objects.create(
            name="Idempotency client",
            code="idempotency-client",
            api_key="idempotency-api-key",
            callback_url="https://callback.example/delivery",
        )
        cls.other_client = ExternalClient.objects.create(
            name="Other idempotency client",
            code="other-idempotency-client",
            api_key="other-idempotency-api-key",
        )
        Language.objects.create(name="English", code="en")
        Topic.objects.create(name="Topic")
        Audience.objects.create(name="Audience")
        Goal.objects.create(name="Goal")
        PromptTemplate.objects.create(
            name="Template",
            system_prompt="System",
            user_prompt_template="User",
        )

    @staticmethod
    def headers(client, key=None):
        headers = {"HTTP_X_API_KEY": client.api_key}
        if key is not None:
            headers["HTTP_IDEMPOTENCY_KEY"] = key
        return headers


class APIIdempotencyTests(IdempotencyFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_fixtures()

    def setUp(self):
        self.api = APIClient()
        self.jobs_url = reverse("contents:api-generation-job-list-create")
        self.export_url = reverse("contents:api-content-export")

    def test_repeated_generation_create_returns_same_job_and_dispatches_once(self):
        with patch("contents.tasks.run_generation_job_task.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                first = self.api.post(
                    self.jobs_url,
                    {"count": 2},
                    format="json",
                    **self.headers(self.client_record, "job-key"),
                )
            with self.captureOnCommitCallbacks(execute=True):
                second = self.api.post(
                    self.jobs_url,
                    {"count": 2},
                    format="json",
                    **self.headers(self.client_record, "job-key"),
                )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(GenerationJob.objects.count(), 1)
        delay.assert_called_once_with(first.json()["job"]["id"])

    def test_repeated_export_returns_exact_items_without_consuming_more(self):
        content = Content.objects.create(
            title="Export",
            prompt="Prompt",
            generated_content="Body",
            content_hash="export-idempotency-hash",
            status="generated",
        )

        first = self.api.post(
            self.export_url,
            {},
            format="json",
            **self.headers(self.client_record, "export-key"),
        )
        second = self.api.post(
            self.export_url,
            {},
            format="json",
            **self.headers(self.client_record, "export-key"),
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(first.json()["items"][0]["id"], content.pk)
        self.assertEqual(content.exports.count(), 1)

    def test_conflicting_payload_returns_409(self):
        with patch("contents.tasks.run_generation_job_task.delay"):
            self.api.post(
                self.jobs_url,
                {"count": 1},
                format="json",
                **self.headers(self.client_record, "conflict-key"),
            )
            response = self.api.post(
                self.jobs_url,
                {"count": 2},
                format="json",
                **self.headers(self.client_record, "conflict-key"),
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(),
            {"detail": "Idempotency key was already used with a different request."},
        )

    def test_keys_are_isolated_between_clients(self):
        with patch("contents.tasks.run_generation_job_task.delay"):
            first = self.api.post(
                self.jobs_url,
                {},
                format="json",
                **self.headers(self.client_record, "shared-key"),
            )
            second = self.api.post(
                self.jobs_url,
                {},
                format="json",
                **self.headers(self.other_client, "shared-key"),
            )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first.json()["job"]["id"], second.json()["job"]["id"])

    def test_expired_record_allows_a_new_operation(self):
        with patch("contents.tasks.run_generation_job_task.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                first = self.api.post(
                    self.jobs_url,
                    {},
                    format="json",
                    **self.headers(self.client_record, "expired-key"),
                )
            APIIdempotencyRecord.objects.update(expires_at=timezone.now())
            with self.captureOnCommitCallbacks(execute=True):
                second = self.api.post(
                    self.jobs_url,
                    {},
                    format="json",
                    **self.headers(self.client_record, "expired-key"),
                )

        self.assertNotEqual(first.json()["job"]["id"], second.json()["job"]["id"])
        self.assertEqual(delay.call_count, 2)

    def test_missing_and_malformed_keys_preserve_non_idempotent_behavior(self):
        for key in (None, "contains spaces"):
            with self.subTest(key=key):
                with patch("contents.tasks.run_generation_job_task.delay"):
                    first = self.api.post(
                        self.jobs_url,
                        {},
                        format="json",
                        **self.headers(self.client_record, key),
                    )
                    second = self.api.post(
                        self.jobs_url,
                        {},
                        format="json",
                        **self.headers(self.client_record, key),
                    )
                self.assertNotEqual(
                    first.json()["job"]["id"],
                    second.json()["job"]["id"],
                )

    def test_validation_failure_does_not_persist_idempotency_record(self):
        response = self.api.post(
            self.jobs_url,
            {"count": 0},
            format="json",
            **self.headers(self.client_record, "invalid-key"),
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(APIIdempotencyRecord.objects.filter(key="invalid-key").exists())


class APIIdempotencyConcurrencyTests(
    IdempotencyFixtureMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self):
        self.create_fixtures()

    def test_concurrent_generation_create_dispatches_once(self):
        barrier = Barrier(2, timeout=10)

        def worker():
            close_old_connections()
            try:
                barrier.wait()
                response = APIClient().post(
                    reverse("contents:api-generation-job-list-create"),
                    {"count": 1},
                    format="json",
                    **self.headers(self.client_record, "concurrent-key"),
                )
                return response.status_code, response.json()
            finally:
                close_old_connections()

        with patch("contents.tasks.run_generation_job_task.delay") as delay:
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = [future.result(15) for future in [
                    executor.submit(worker),
                    executor.submit(worker),
                ]]

        self.assertEqual([result[0] for result in results], [201, 201])
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(GenerationJob.objects.count(), 1)
        delay.assert_called_once()
