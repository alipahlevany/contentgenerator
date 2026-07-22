from unittest.mock import Mock, patch

import requests
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from rest_framework.test import APIClient

from contents.core_services.delivery import (
    RetryableDeliveryError,
    deliver_content,
    validate_callback_url,
)
from contents.models import Content, ContentDelivery, ExternalClient
from contents.tasks import deliver_content_callback


PUBLIC_DNS = [(2, 1, 6, "", ("93.184.216.34", 443))]


@override_settings(MTA_API_KEY="test-api-key")
class ContentDeliveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.client_a = ExternalClient.objects.create(
            name="Delivery A",
            code="delivery-a",
            api_key="delivery-key-a",
            callback_url="https://a.example/callback",
        )
        cls.client_b = ExternalClient.objects.create(
            name="Delivery B",
            code="delivery-b",
            api_key="delivery-key-b",
            callback_url="https://b.example/callback",
        )
        cls.content = Content.objects.create(
            title="Deliverable",
            prompt="Prompt",
            generated_content="Body",
            content_hash="delivery-hash",
            status="generated",
        )

    def setUp(self):
        self.api = APIClient()
        self.url = reverse(
            "contents:api-content-delivery",
            kwargs={"pk": self.content.pk},
        )

    def create_delivery(self, client=None):
        client = client or self.client_a
        return ContentDelivery.objects.create(
            client=client,
            content=self.content,
            content_hash=self.content.content_hash,
            destination_url=client.callback_url,
        )

    @patch("contents.core_services.delivery.socket.getaddrinfo", return_value=PUBLIC_DNS)
    def test_endpoint_uses_authenticated_client_callback_and_is_idempotent(
        self,
        getaddrinfo,
    ):
        with patch(
            "contents.api.views.delivery.deliver_content_callback.delay"
        ) as delay:
            with self.captureOnCommitCallbacks(execute=True):
                first = self.api.post(
                    self.url,
                    HTTP_X_API_KEY=self.client_a.api_key,
                )
            with self.captureOnCommitCallbacks(execute=True):
                second = self.api.post(
                    self.url,
                    HTTP_X_API_KEY=self.client_a.api_key,
                )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(first.json()["destination_url"], self.client_a.callback_url)
        self.assertEqual(ContentDelivery.objects.count(), 1)
        delay.assert_called_once_with(first.json()["id"])

    @patch("contents.core_services.delivery.socket.getaddrinfo", return_value=PUBLIC_DNS)
    def test_clients_cannot_select_or_trigger_another_clients_callback(self, _):
        with patch(
            "contents.api.views.delivery.deliver_content_callback.delay"
        ) as delay:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.api.post(
                    self.url,
                    {"client": self.client_b.pk, "destination_url": self.client_b.callback_url},
                    format="json",
                    HTTP_X_API_KEY=self.client_a.api_key,
                )

        delivery = ContentDelivery.objects.get()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(delivery.client, self.client_a)
        self.assertEqual(delivery.destination_url, self.client_a.callback_url)
        self.assertNotEqual(delivery.destination_url, self.client_b.callback_url)
        delay.assert_called_once()

    @patch("contents.core_services.delivery.socket.getaddrinfo", return_value=PUBLIC_DNS)
    @patch("contents.core_services.delivery.requests.post")
    def test_success_uses_strict_http_options_and_records_status(self, post, _):
        post.return_value = Mock(status_code=204, text="")
        delivery = self.create_delivery()

        result = deliver_content(delivery.pk)

        result.refresh_from_db()
        self.assertEqual(result.status, "success")
        self.assertEqual(result.attempt_count, 1)
        self.assertIsNotNone(result.delivered_at)
        call = post.call_args
        self.assertEqual(call.args[0], self.client_a.callback_url)
        self.assertEqual(call.kwargs["timeout"], (5, 15))
        self.assertFalse(call.kwargs["allow_redirects"])
        self.assertEqual(
            call.kwargs["headers"],
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": "Api-Key test-api-key",
            },
        )

    @patch("contents.core_services.delivery.socket.getaddrinfo", return_value=PUBLIC_DNS)
    @patch("contents.core_services.delivery.requests.post")
    def test_timeout_and_connection_error_are_retryable_and_recorded(self, post, _):
        for exception in (requests.Timeout(), requests.ConnectionError()):
            delivery = self.create_delivery()
            post.side_effect = exception

            with self.assertRaises(RetryableDeliveryError):
                deliver_content(delivery.pk)

            delivery.refresh_from_db()
            self.assertEqual(delivery.status, "failed")
            self.assertEqual(delivery.attempt_count, 1)
            self.assertEqual(
                delivery.last_error,
                "Temporary callback connection failure.",
            )
            delivery.delete()

    @patch("contents.core_services.delivery.socket.getaddrinfo", return_value=PUBLIC_DNS)
    @patch("contents.core_services.delivery.requests.post")
    def test_5xx_is_retryable_but_4xx_and_redirect_are_not(self, post, _):
        for status_code, retryable in ((503, True), (400, False), (302, False)):
            delivery = self.create_delivery()
            post.side_effect = None
            post.return_value = Mock(status_code=status_code, text="")

            if retryable:
                with self.assertRaises(RetryableDeliveryError):
                    deliver_content(delivery.pk)
            else:
                result = deliver_content(delivery.pk)
                self.assertEqual(result.status, "failed")

            delivery.refresh_from_db()
            self.assertEqual(delivery.last_error, f"Callback returned HTTP {status_code}.")
            delivery.delete()

    def test_task_retry_policy_is_bounded(self):
        self.assertEqual(deliver_content_callback.max_retries, 3)

    def test_callback_url_validation_rejects_unsafe_destinations(self):
        unsafe = (
            "",
            "http://example.com/callback",
            "https://user:password@example.com/callback",
            "https://127.0.0.1/callback",
            "https://169.254.169.254/latest/meta-data/",
            "https://10.0.0.1/callback",
        )
        for url in unsafe:
            with self.subTest(url=url):
                with self.assertRaises(ValidationError):
                    validate_callback_url(url)

    @override_settings(CALLBACK_DELIVERY_ALLOW_PRIVATE_NETWORKS=True)
    def test_trusted_setting_can_explicitly_allow_private_callback(self):
        self.assertEqual(
            validate_callback_url("https://127.0.0.1/callback"),
            "https://127.0.0.1/callback",
        )

    def test_content_save_remains_side_effect_free(self):
        with patch(
            "contents.api.views.delivery.deliver_content_callback.delay"
        ) as delay:
            Content.objects.create(title="No delivery", prompt="Prompt")

        delay.assert_not_called()

    def test_legacy_hard_coded_destination_is_absent(self):
        from pathlib import Path

        task_source = Path("contents/tasks.py").read_text()
        self.assertNotIn("melal.org/createContentAPIView", task_source)
