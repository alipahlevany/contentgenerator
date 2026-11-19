"""Exercise persistence, scheduling, previews, and the delivery boundary together."""

from datetime import date, datetime, timezone as datetime_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import OperationalError
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from contents.admin.warmup_template import SAMPLE_PHOTO
from contents.core_services.warmup_template_renderer import LAYOUT_NAMES
from contents.core_services.delivery import deliver_content
from contents.core_services.delivery_queue import queue_content_deliveries
from contents.core_services.warmup_templates import generate_warmup_template
from contents.core_services.warmup_runs import LATEST_KEY
from contents.models import AIUsageLog, AppSettings, Content, ContentDelivery, ExternalClient
from contents.tasks import run_daily_warmup_template_task


@override_settings(
    WARMUP_TEMPLATE_PHOTO_PROVIDER="auto", PEXELS_API_KEY="", OPENAI_API_KEY="",
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class WarmupTemplateFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        article_patch = patch("contents.core_services.warmup_templates.choose_article", return_value="https://medium.com/test/story-123")
        article_patch.start()
        self.addCleanup(article_patch.stop)
        self.settings_record = AppSettings.objects.create(
            auto_daily_warmup_template_enabled=True, daily_warmup_template_count=3,
            daily_warmup_template_delay_seconds=2, daily_warmup_template_hour=5,
        )
        self.external_client = ExternalClient.objects.create(
            name="Template boundary test", code="template-test", api_key="test-template-key",
            callback_url="https://example.com/callback", is_active=True,
        )
        self.photo = {
            **SAMPLE_PHOTO, "id": "1018", "provider": "picsum", "theme": "A fresh perspective",
        }

    def make_template(self):
        with patch("contents.core_services.warmup_templates._get_remote_photo", return_value=self.photo), patch(
            "contents.core_services.ai.client.responses.create",
        ) as create:
            first = generate_warmup_template(date(2026, 11, 17), 0, "integration-test")
            again = generate_warmup_template(date(2026, 11, 17), 0, "integration-test")
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(Content.objects.count(), 1)
        create.assert_not_called()
        self.assertFalse(AIUsageLog.objects.exists())
        self.assertEqual(first.generated_content.count("{{content}}"), 1)
        self.assertEqual(first.generated_content.count("{{unsubscribe}}"), 1)
        self.assertNotIn("<h1", first.generated_content)
        self.assertNotIn("Hello there", first.generated_content)
        return first

    def login_admin(self):
        admin = get_user_model().objects.create_superuser("template-admin", "admin@example.com", "test-password")
        self.client.force_login(admin)

    def test_empty_template_is_saved_without_ai_and_previewed_once(self):
        template = self.make_template()
        self.login_admin()
        preview = self.client.get(reverse("admin:contents_warmuptemplate_preview_frame", args=[template.pk]))
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "picsum.photos/id/1018/1200/800.jpg")
        self.assertNotContains(preview, "{{content}}")
        self.assertIn("https://fastly.picsum.photos", preview["Content-Security-Policy"])
        download = self.client.get(reverse("admin:contents_warmuptemplate_download", args=[template.pk]))
        self.assertEqual(download.content.decode(), template.generated_content)
        settings_page = self.client.get(reverse("admin:contents_warmuptemplategenerationsettings_change", args=[self.settings_record.pk]))
        self.assertContains(settings_page, "Unsplash via Picsum")
        self.assertContains(settings_page, "Create 3 templates")

    def test_all_designs_are_available_without_generating_paid_content(self):
        self.login_admin()
        with patch("contents.core_services.ai.client.responses.create") as generate:
            for index, name in enumerate(LAYOUT_NAMES):
                page = self.client.get(reverse("admin:contents_warmuptemplate_sample"), {"layout": index})
                self.assertContains(page, name)
                frame = self.client.get(reverse("admin:contents_warmuptemplate_sample_frame", args=[index]))
                self.assertEqual(frame.status_code, 200)
                self.assertContains(frame, "picsum.photos/id/1018/1200/800.jpg")
                self.assertNotContains(frame, "{{content}}")
            generate.assert_not_called()
        self.assertFalse(Content.objects.exists())

    def test_persistence_retry_never_generates_paid_copy(self):
        with patch("contents.core_services.warmup_templates._get_remote_photo", return_value=self.photo), patch(
            "contents.core_services.ai.client.responses.create",
        ) as generate:
            with patch("contents.core_services.warmup_templates.Content.objects.create", side_effect=OperationalError("temporary failure")):
                with self.assertRaises(OperationalError):
                    generate_warmup_template(date(2026, 11, 17), 0, "retry-test")
            self.assertFalse(Content.objects.exists())
            saved = generate_warmup_template(date(2026, 11, 17), 0, "retry-test")
            repeated = generate_warmup_template(date(2026, 11, 17), 0, "retry-test")
        self.assertEqual(saved.pk, repeated.pk)
        self.assertIn("Picsum photo ID: 1018", saved.prompt)
        generate.assert_not_called()
        self.assertFalse(AIUsageLog.objects.exists())

    def test_template_is_hidden_from_every_external_content_endpoint(self):
        template = self.make_template()
        api = APIClient()
        headers = {"HTTP_X_API_KEY": "test-template-key"}
        listing = api.get(reverse("contents:api-content-list"), **headers)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["data"], [])
        self.assertEqual(api.get(reverse("contents:api-content-detail", args=[template.pk]), **headers).status_code, 404)
        with patch("contents.api.views.delivery.deliver_content_callback.delay") as enqueue:
            result = api.post(reverse("contents:api-content-delivery", args=[template.pk]), **headers)
        self.assertEqual(result.status_code, 404)
        enqueue.assert_not_called()
        self.assertEqual(queue_content_deliveries(template), [])
        self.assertFalse(ContentDelivery.objects.exists())

    @patch("contents.core_services.delivery.requests.post")
    @patch("contents.core_services.delivery.socket.getaddrinfo")
    def test_existing_delivery_cannot_send_template(self, dns, post):
        template = self.make_template()
        delivery = ContentDelivery.objects.create(
            client=self.external_client, content=template, content_hash=template.content_hash,
            destination_url=self.external_client.callback_url,
        )
        result = deliver_content(delivery.pk)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.attempt_count, 0)
        dns.assert_not_called()
        post.assert_not_called()

    @patch("contents.tasks.generate_warmup_template_task.apply_async")
    @patch("contents.tasks.timezone.localtime", return_value=datetime(2026, 11, 17, 5, 0, tzinfo=datetime_timezone.utc))
    def test_schedule_queues_exact_count_and_only_once_per_day(self, _now, enqueue):
        self.assertIn("Queued 3", run_daily_warmup_template_task.run())
        self.assertIn("already ran", run_daily_warmup_template_task.run())
        self.assertEqual(enqueue.call_count, 3)
        self.assertEqual([call.kwargs["countdown"] for call in enqueue.call_args_list], [0, 2, 4])
        self.settings_record.refresh_from_db()
        self.assertEqual(self.settings_record.last_daily_warmup_template_date, date(2026, 11, 17))

    @patch("contents.tasks.run_daily_warmup_template_task.delay")
    def test_manual_run_works_without_pexels_and_blocks_double_click(self, enqueue):
        self.login_admin()
        url = reverse("admin:contents_warmuptemplategenerationsettings_run_now")
        self.assertEqual(self.client.get(url).status_code, 405)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(url).status_code, 302)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(url).status_code, 302)
        enqueue.assert_called_once_with(force=True, batch_key=cache.get(LATEST_KEY))
