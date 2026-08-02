from unittest.mock import patch

from django.urls import reverse
from rest_framework.test import APITestCase

from contents.models import ExternalClient, GenerationJob, Language


class GreetingGenerationAPITests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.language = Language.objects.create(
            name="English",
            code="en",
            is_active=True,
        )

        cls.client_record = ExternalClient.objects.create(
            name="Greeting Client",
            code="greeting-client",
            is_active=True,
        )

        cls.api_key = cls.client_record.rotate_api_key()

        cls.url = reverse(
            "contents:api-greeting-generation-job-create"
        )

    def headers(self):
        return {
            "HTTP_X_API_KEY": self.api_key,
        }

    @patch(
    "contents.core_services.generation_jobs.creation."
    "run_generation_job_task.delay"
)
    def test_create_greeting_job_with_all_languages(
        self,
        mock_delay,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.url,
                {
                    "count": 3,
                    "delay_seconds": 0,
                    "languages": "all",
                },
                format="json",
                **self.headers(),
            )

        self.assertEqual(
            response.status_code,
            201,
        )

        job = GenerationJob.objects.get()

        self.assertEqual(
            job.generation_type,
            "greeting",
        )
        self.assertEqual(
            job.count,
            3,
        )
        self.assertEqual(
            job.delay_seconds,
            0,
        )
        self.assertTrue(
            job.use_all_languages,
        )
        self.assertEqual(
            job.external_client,
            self.client_record,
        )

        mock_delay.assert_called_once_with(
            job.pk
        )

    @patch(
    "contents.core_services.generation_jobs.creation."
    "run_generation_job_task.delay"
)
    def test_create_greeting_job_with_selected_language(
        self,
        mock_delay,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.url,
                {
                    "count": 1,
                    "delay_seconds": 0,
                    "languages": [
                        self.language.pk,
                    ],
                },
                format="json",
                **self.headers(),
            )

        self.assertEqual(
            response.status_code,
            201,
        )

        job = GenerationJob.objects.get()

        self.assertFalse(
            job.use_all_languages,
        )

        self.assertEqual(
            list(
                job.languages.values_list(
                    "id",
                    flat=True,
                )
            ),
            [
                self.language.pk,
            ],
        )

        mock_delay.assert_called_once_with(
            job.pk
        )

    def test_greeting_endpoint_does_not_require_standard_datasets(
        self,
    ):
        response = self.client.post(
            self.url,
            {
                "count": 1,
                "delay_seconds": 0,
                "languages": "all",
            },
            format="json",
            **self.headers(),
        )

        self.assertNotEqual(
            response.status_code,
            400,
        )

        if response.status_code == 201:
            job = GenerationJob.objects.get()

            self.assertEqual(
                job.generation_type,
                "greeting",
            )

    def test_empty_languages_are_rejected(self):
        response = self.client.post(
            self.url,
            {
                "count": 1,
                "delay_seconds": 0,
                "languages": [],
            },
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        payload = response.json()

        self.assertFalse(
            payload["success"]
        )

        self.assertEqual(
            payload["error"]["code"],
            "validation_error",
        )

        self.assertIn(
            "languages",
            payload["error"]["fields"],
        )

    def test_invalid_language_id_is_rejected(self):
        response = self.client.post(
            self.url,
            {
                "count": 1,
                "delay_seconds": 0,
                "languages": [999999],
            },
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        payload = response.json()

        self.assertIn(
            "languages",
            payload["error"]["fields"],
        )

    def test_missing_api_key_is_rejected(self):
        response = self.client.post(
            self.url,
            {
                "count": 1,
                "languages": "all",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        payload = response.json()

        self.assertFalse(
            payload["success"]
        )

        self.assertEqual(
            payload["error"]["code"],
            "authentication_failed",
        )
