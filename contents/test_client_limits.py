from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from rest_framework.test import APIClient

from contents.models import (
    Audience,
    Content,
    ExternalClient,
    GenerationJob,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)


LOC_MEMORY_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "client-limit-tests",
    }
}


class ClientLimitFixtureMixin:
    @classmethod
    def create_fixtures(cls):
        cls.client_a = ExternalClient.objects.create(
            name="Limited A",
            code="limited-a",
            api_key="limited-key-a",
        )
        cls.client_b = ExternalClient.objects.create(
            name="Limited B",
            code="limited-b",
            api_key="limited-key-b",
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
    def headers(client, idempotency_key=None):
        result = {"HTTP_X_API_KEY": client.api_key}
        if idempotency_key:
            result["HTTP_IDEMPOTENCY_KEY"] = idempotency_key
        return result


@override_settings(CACHES=LOC_MEMORY_CACHE)
class ClientLimitTests(ClientLimitFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_fixtures()

    def setUp(self):
        self.api = APIClient()
        self.jobs_url = reverse("contents:api-generation-job-list-create")
        self.export_url = reverse("contents:api-content-export")

    def test_defaults_preserve_unlimited_behavior(self):
        with patch("contents.tasks.run_generation_job_task.delay"):
            response = self.api.post(
                self.jobs_url,
                {"count": 10000},
                format="json",
                **self.headers(self.client_a),
            )

        self.assertEqual(response.status_code, 201)

    def test_rate_limits_are_separate_and_include_retry_after(self):
        ExternalClient.objects.filter(pk__in=[self.client_a.pk, self.client_b.pk]).update(
            limits_enabled=True,
            requests_per_minute=1,
        )

        first_a = self.api.get("/api/v1/datasets/", **self.headers(self.client_a))
        second_a = self.api.get("/api/v1/datasets/", **self.headers(self.client_a))
        first_b = self.api.get("/api/v1/datasets/", **self.headers(self.client_b))

        self.assertEqual(first_a.status_code, 200)
        self.assertEqual(second_a.status_code, 429)
        self.assertIn("Retry-After", second_a)
        self.assertEqual(first_b.status_code, 200)

    def test_generation_count_and_active_job_quotas(self):
        self.client_a.limits_enabled = True
        self.client_a.max_generation_content_count = 2
        self.client_a.max_active_generation_jobs = 1
        self.client_a.save()

        too_large = self.api.post(
            self.jobs_url,
            {"count": 3},
            format="json",
            **self.headers(self.client_a),
        )
        with patch("contents.tasks.run_generation_job_task.delay"):
            accepted = self.api.post(
                self.jobs_url,
                {"count": 2},
                format="json",
                **self.headers(self.client_a),
            )
            active_limit = self.api.post(
                self.jobs_url,
                {"count": 1},
                format="json",
                **self.headers(self.client_a),
            )

        self.assertEqual(too_large.status_code, 429)
        self.assertEqual(accepted.status_code, 201)
        self.assertEqual(active_limit.status_code, 429)

    def test_daily_export_quota_limits_actual_exported_items(self):
        self.client_a.limits_enabled = True
        self.client_a.daily_export_item_quota = 1
        self.client_a.save()
        for index in range(2):
            Content.objects.create(
                title=f"Content {index}",
                prompt="Prompt",
                content_hash=f"quota-hash-{index}",
                status="generated",
            )

        first = self.api.post(
            self.export_url,
            {"count": 100},
            format="json",
            **self.headers(self.client_a),
        )
        second = self.api.post(
            self.export_url,
            {"count": 100},
            format="json",
            **self.headers(self.client_a),
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["exported"], 1)
        self.assertEqual(second.status_code, 429)

    def test_idempotent_export_replay_does_not_consume_quota_twice(self):
        self.client_a.limits_enabled = True
        self.client_a.daily_export_item_quota = 1
        self.client_a.save()
        Content.objects.create(
            title="Content",
            prompt="Prompt",
            content_hash="idempotent-quota-hash",
            status="generated",
        )

        first = self.api.post(
            self.export_url,
            {},
            format="json",
            **self.headers(self.client_a, "quota-replay"),
        )
        replay = self.api.post(
            self.export_url,
            {},
            format="json",
            **self.headers(self.client_a, "quota-replay"),
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), replay.json())
        self.assertEqual(self.client_a.content_exports.count(), 1)


class ClientLimitConcurrencyTests(ClientLimitFixtureMixin, TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.create_fixtures()
        self.client_a.limits_enabled = True
        self.client_a.max_active_generation_jobs = 1
        self.client_a.save()

    def test_concurrent_generation_requests_cannot_exceed_active_quota(self):
        barrier = Barrier(2, timeout=10)

        def worker():
            close_old_connections()
            try:
                barrier.wait()
                return APIClient().post(
                    reverse("contents:api-generation-job-list-create"),
                    {},
                    format="json",
                    **self.headers(self.client_a),
                ).status_code
            finally:
                close_old_connections()

        with patch("contents.tasks.run_generation_job_task.delay") as delay:
            with ThreadPoolExecutor(max_workers=2) as executor:
                statuses = [future.result(15) for future in [
                    executor.submit(worker),
                    executor.submit(worker),
                ]]

        self.assertEqual(sorted(statuses), [201, 429])
        self.assertEqual(GenerationJob.objects.count(), 1)
        delay.assert_called_once()
