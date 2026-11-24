from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock, patch

from django.db import close_old_connections
from django.test import TransactionTestCase, override_settings

from contents.core_services.delivery import deliver_content
from contents.models import Content, ContentDelivery, ExternalClient


@override_settings(MTA_API_KEY="test-key", CALLBACK_DELIVERY_ALLOW_PRIVATE_NETWORKS=True)
class CallbackConcurrencyTests(TransactionTestCase):
    def test_duplicate_task_does_not_post_while_first_request_is_running(self):
        client = ExternalClient.objects.create(name="Callback", code="callback")
        content = Content.objects.create(title="Content", prompt="Prompt")
        delivery = ContentDelivery.objects.create(
            client=client, content=content, destination_url="https://example.com/callback"
        )
        entered, release = Event(), Event()

        def post(*args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise RuntimeError("test timed out")
            return Mock(status_code=204, text="")

        def worker():
            close_old_connections()
            try:
                return deliver_content(delivery.pk).status
            finally:
                close_old_connections()

        with patch("contents.core_services.delivery.requests.post", side_effect=post) as request:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(worker)
                try:
                    self.assertTrue(entered.wait(10))
                    self.assertEqual(deliver_content(delivery.pk).status, "processing")
                    self.assertEqual(request.call_count, 1)
                finally:
                    release.set()
                self.assertEqual(future.result(timeout=10), "success")
            self.assertEqual(deliver_content(delivery.pk).status, "success")
            self.assertEqual(request.call_count, 1)
