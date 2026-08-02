from django.urls import reverse
from rest_framework.test import APITestCase

from contents.models import (
    Content,
    ContentExport,
    ExternalClient,
    Language,
)


class GreetingExportAPITests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.language_en = Language.objects.create(
            name="English",
            code="en",
            is_active=True,
        )

        cls.language_de = Language.objects.create(
            name="German",
            code="de",
            is_active=True,
        )

        cls.client_record = ExternalClient.objects.create(
            name="Greeting Export Client",
            code="greeting-export-client",
            is_active=True,
        )

        cls.api_key = cls.client_record.rotate_api_key()

        cls.url = reverse(
            "contents:api-greeting-export"
        )

    def headers(self):
        return {
            "HTTP_X_API_KEY": self.api_key,
        }

    def create_greeting(
        self,
        *,
        language,
        body,
    ):
        return Content.objects.create(
            title="Greeting",
            content_type="greeting",
            language=language,
            prompt="Greeting prompt",
            generated_content=body,
            content_hash=(
                f"hash-{language.code}-{body}"
            ),
            status="generated",
        )

    def test_export_all_greetings(self):
        first = self.create_greeting(
            language=self.language_en,
            body="Hello, hope you're doing well.",
        )

        second = self.create_greeting(
            language=self.language_de,
            body="Hallo, ich hoffe, es geht dir gut.",
        )

        response = self.client.post(
            self.url,
            {
                "count": 10,
                "delay_seconds": 0,
                "languages": "all",
            },
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = response.json()

        self.assertTrue(
            payload["success"]
        )

        self.assertEqual(
            payload["message"],
            "Greetings exported successfully.",
        )

        self.assertEqual(
            payload["data"]["exported"],
            2,
        )

        exported_ids = {
            item["id"]
            for item in payload["data"]["items"]
        }

        self.assertEqual(
            exported_ids,
            {
                first.pk,
                second.pk,
            },
        )

        self.assertEqual(
            ContentExport.objects.filter(
                client=self.client_record,
            ).count(),
            2,
        )

    def test_export_filters_by_language(self):
        english = self.create_greeting(
            language=self.language_en,
            body="Hello there.",
        )

        self.create_greeting(
            language=self.language_de,
            body="Hallo zusammen.",
        )

        response = self.client.post(
            self.url,
            {
                "count": 10,
                "languages": [
                    self.language_en.pk,
                ],
            },
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = response.json()

        self.assertEqual(
            payload["data"]["exported"],
            1,
        )

        self.assertEqual(
            payload["data"]["items"][0]["id"],
            english.pk,
        )

    def test_standard_and_reply_contents_are_not_exported(self):
        greeting = self.create_greeting(
            language=self.language_en,
            body="Good morning!",
        )

        Content.objects.create(
            title="Standard",
            content_type="standard",
            language=self.language_en,
            prompt="Standard prompt",
            generated_content="Standard content",
            content_hash="standard-hash",
            status="generated",
        )

        Content.objects.create(
            title="Reply",
            content_type="email_reply",
            language=self.language_en,
            prompt="Reply prompt",
            generated_content="Reply content",
            content_hash="reply-hash",
            status="generated",
        )

        response = self.client.post(
            self.url,
            {
                "count": 10,
                "languages": "all",
            },
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        items = response.json()["data"]["items"]

        self.assertEqual(
            len(items),
            1,
        )

        self.assertEqual(
            items[0]["id"],
            greeting.pk,
        )

    def test_successful_greeting_is_not_exported_twice(self):
        greeting = self.create_greeting(
            language=self.language_en,
            body="Hope your day is going well.",
        )

        first = self.client.post(
            self.url,
            {
                "count": 1,
                "languages": "all",
            },
            format="json",
            **self.headers(),
        )

        second = self.client.post(
            self.url,
            {
                "count": 1,
                "languages": "all",
            },
            format="json",
            **self.headers(),
        )

        self.assertEqual(
            first.status_code,
            200,
        )

        self.assertEqual(
            second.status_code,
            200,
        )

        self.assertEqual(
            first.json()["data"]["exported"],
            1,
        )

        self.assertEqual(
            second.json()["data"]["exported"],
            0,
        )

        self.assertEqual(
            ContentExport.objects.filter(
                content=greeting,
                client=self.client_record,
                status="success",
            ).count(),
            1,
        )

    def test_invalid_language_is_rejected(self):
        response = self.client.post(
            self.url,
            {
                "count": 1,
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
