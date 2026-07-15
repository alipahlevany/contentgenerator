from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APIClient

from contents.models import Content, ExternalClient, GenerationJob


class CursorPaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.client_a = ExternalClient.objects.create(
            name="Pagination A",
            code="pagination-a",
            api_key="pagination-key-a",
        )
        cls.client_b = ExternalClient.objects.create(
            name="Pagination B",
            code="pagination-b",
            api_key="pagination-key-b",
        )

        cls.contents = [
            Content.objects.create(
                title=f"Searchable {index}",
                prompt="needle" if index != 4 else "other",
                content_hash=f"page-hash-{index}",
                status="generated" if index != 3 else "draft",
            )
            for index in range(5)
        ]
        cls.jobs_a = [
            GenerationJob.objects.create(external_client=cls.client_a)
            for _ in range(5)
        ]
        cls.job_b = GenerationJob.objects.create(external_client=cls.client_b)

        same_time = timezone.now()
        Content.objects.filter(pk__in=[item.pk for item in cls.contents]).update(
            created_at=same_time
        )
        GenerationJob.objects.filter(
            pk__in=[item.pk for item in cls.jobs_a] + [cls.job_b.pk]
        ).update(created_at=same_time)

    def setUp(self):
        self.api = APIClient()
        self.content_url = reverse("contents:api-content-list")
        self.jobs_url = reverse("contents:api-generation-job-list-create")

    @staticmethod
    def headers(client):
        return {"HTTP_X_API_KEY": client.api_key}

    def collect_pages(self, url, client, extra=None):
        cursor = None
        collected = []
        while True:
            params = {"page_size": 2, **(extra or {})}
            if cursor:
                params["cursor"] = cursor
            response = self.api.get(url, params, **self.headers(client))
            self.assertEqual(response.status_code, 200)
            collected.extend(item["id"] for item in response.json()["results"])
            cursor = response.json()["next_cursor"]
            if not cursor:
                return collected

    def test_content_pages_have_stable_order_without_duplicates_or_gaps(self):
        ids = self.collect_pages(self.content_url, self.client_a)

        self.assertEqual(ids, sorted([item.pk for item in self.contents], reverse=True))
        self.assertEqual(len(ids), len(set(ids)))

    def test_generation_pages_are_stable_and_tenant_filtered(self):
        ids = self.collect_pages(self.jobs_url, self.client_a)

        self.assertEqual(ids, sorted([item.pk for item in self.jobs_a], reverse=True))
        self.assertNotIn(self.job_b.pk, ids)

    def test_content_filters_and_search_are_applied_before_cursor(self):
        ids = self.collect_pages(
            self.content_url,
            self.client_a,
            {"status": "generated", "q": "needle"},
        )
        expected = [
            item.pk
            for item in self.contents
            if item.status == "generated" and item.prompt == "needle"
        ]
        self.assertEqual(ids, sorted(expected, reverse=True))

    def test_invalid_cursor_and_page_size_return_exact_400(self):
        invalid_cursor = self.api.get(
            self.content_url,
            {"cursor": "invalid", "page_size": 2},
            **self.headers(self.client_a),
        )
        invalid_size = self.api.get(
            self.jobs_url,
            {"page_size": 101},
            **self.headers(self.client_a),
        )

        self.assertEqual(invalid_cursor.status_code, 400)
        self.assertEqual(
            invalid_cursor.json(),
            {"detail": "Invalid or expired cursor."},
        )
        self.assertEqual(invalid_size.status_code, 400)
        self.assertEqual(
            invalid_size.json(),
            {"detail": "page_size must be between 1 and 100."},
        )

    def test_legacy_requests_keep_raw_array_response(self):
        content_response = self.api.get(
            self.content_url,
            **self.headers(self.client_a),
        )
        job_response = self.api.get(
            self.jobs_url,
            **self.headers(self.client_a),
        )

        self.assertIsInstance(content_response.json(), list)
        self.assertIsInstance(job_response.json(), list)
