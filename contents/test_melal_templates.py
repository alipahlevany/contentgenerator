from datetime import date
from unittest.mock import Mock, patch
import os
from unittest import skipUnless
import requests
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from contents.models import Content, MelalTemplateDelivery
from contents.core_services.melal_templates import queue_template, send_template
from contents.core_services.warmup_templates import generate_warmup_template
from contents.admin.warmup_template import SAMPLE_PHOTO
from contents.tasks import send_melal_template, dispatch_melal_templates


@override_settings(MELAL_TEMPLATE_ENABLED=True,
                   MELAL_TEMPLATE_ENDPOINT="https://melal.example/templates/import/",
                   MELAL_TEMPLATE_API_KEY="test-key", MELAL_TEMPLATE_SOURCE="local-test")
class MelalConnectorTests(TestCase):
    def setUp(self):
        self.content = Content.objects.create(title="test",content_type="warmup_template",
                                              generated_content="{{content}}{{unsubscribe}}",status="generated")
        queue_template(self.content)
        self.row=MelalTemplateDelivery.objects.get()

    @override_settings(MELAL_TEMPLATE_SOURCE="long-source" * 30)
    def test_long_source_respects_remote_id_limit(self):
        self.row.delete()
        queue_template(self.content)
        first = MelalTemplateDelivery.objects.get().external_id
        self.assertLessEqual(len(first), 100)
        queue_template(self.content)
        self.assertEqual(MelalTemplateDelivery.objects.get().external_id, first)

    @override_settings(MELAL_TEMPLATE_ENABLED=False)
    @patch("contents.core_services.melal_templates.requests.post")
    def test_disabled_connector_does_not_send(self, post):
        self.assertEqual(send_template(self.row.pk), "disabled")
        post.assert_not_called()

    @patch("contents.core_services.melal_templates.requests.post")
    def test_success_preserves_payload_and_duplicate_is_noop(self, post):
        post.return_value=Mock(status_code=201,json=lambda:{"id":123})
        self.assertEqual(send_template(self.row.pk),"sent")
        self.assertEqual(send_template(self.row.pk),"sent")
        self.assertEqual(post.call_count,1)
        self.assertEqual(post.call_args.kwargs["json"]["html"],self.content.generated_content)
        self.assertFalse(post.call_args.kwargs["allow_redirects"])

    @patch("contents.core_services.melal_templates.requests.post",side_effect=requests.Timeout)
    def test_timeout_saves_retry_and_does_not_expose_secret(self, post):
        self.assertEqual(send_template(self.row.pk),"pending")
        self.row.refresh_from_db()
        self.assertEqual(self.row.attempts,1)
        self.assertGreater(self.row.next_attempt_at,timezone.now())
        self.assertNotIn("test-key",self.row.last_error)

    @patch("contents.core_services.melal_templates.requests.post")
    def test_permanent_rejection_stops_retry(self, post):
        post.return_value=Mock(status_code=409)
        self.assertEqual(send_template(self.row.pk),"failed")

    @patch("contents.core_services.melal_templates.requests.post")
    def test_transient_status_retries_then_stops_at_limit(self, post):
        post.return_value=Mock(status_code=503)
        self.row.attempts=7
        self.row.save()
        self.assertEqual(send_template(self.row.pk),"failed")

    @patch("contents.core_services.melal_templates.requests.post")
    def test_invalid_success_response_is_retryable(self, post):
        post.return_value=Mock(status_code=200,json=lambda:{"id":True})
        self.assertEqual(send_template(self.row.pk),"pending")

    @override_settings(MELAL_TEMPLATE_ENDPOINT="https://other.example/")
    @patch("contents.core_services.melal_templates.requests.post")
    def test_changed_destination_does_not_receive_credentials(self, post):
        self.assertEqual(send_template(self.row.pk),"configuration_error")
        post.assert_not_called()

    @patch("contents.tasks.send_melal_template.delay",side_effect=RuntimeError("broker unavailable"))
    def test_broker_failure_keeps_outbox(self, delay):
        with self.captureOnCommitCallbacks(execute=True):
            queue_template(self.content)
        self.assertEqual(MelalTemplateDelivery.objects.count(),1)

    @patch("contents.tasks.send_melal_template.delay")
    def test_periodic_dispatch_recovers_pending(self, delay):
        dispatch_melal_templates.run()
        delay.assert_called_once_with(self.row.pk)


@skipUnless(os.getenv("MELAL_SIM_URL"),"Requires the explicit local Melal simulation server")
class LiveMelalConnectorTests(TransactionTestCase):
    def test_generation_automatically_posts_to_local_melal(self):
        photo={**SAMPLE_PHOTO,"id":"1018","provider":"picsum"}
        with override_settings(
            MELAL_TEMPLATE_ENABLED=True,MELAL_TEMPLATE_ENDPOINT=os.environ["MELAL_SIM_URL"],
            MELAL_TEMPLATE_API_KEY=os.environ["MELAL_SIM_KEY"],MELAL_TEMPLATE_ALLOW_LOCAL_HTTP=True,
            MELAL_TEMPLATE_SOURCE=os.environ["MELAL_SIM_SOURCE"],
        ), patch("contents.core_services.warmup_templates.choose_article",return_value="https://medium.com/test/story-123"), patch("contents.core_services.warmup_templates._get_remote_photo",return_value=photo), patch(
            "contents.tasks.send_melal_template.delay",side_effect=send_melal_template.run
        ):
            saved=generate_warmup_template(date(2026,11,18),0,"connector-local-live")
            row=MelalTemplateDelivery.objects.get(content=saved)
            self.assertEqual(row.status,"sent")
            self.assertIsNotNone(row.remote_id)
            self.assertEqual(row.html,saved.generated_content)
            response=requests.post(os.environ["MELAL_SIM_URL"],headers={
                "Authorization":"Api-Key "+os.environ["MELAL_SIM_KEY"]},
                json={"external_id":row.external_id,"html":row.html},timeout=10)
            self.assertEqual(response.status_code,200)
            self.assertFalse(response.json()["created"])
            self.assertFalse(response.json()["status"])
            self.assertEqual(response.json()["id"],row.remote_id)
