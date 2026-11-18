"""Exercise the button-to-results path, failures, and isolation from other content."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from contents.admin.warmup_template import SAMPLE_PHOTO
from contents.core_services.warmup_runs import (
    COOLDOWN_KEY, LATEST_KEY, batch_cache_key, create_manual_batch,
    manual_batch_progress, record_batch_dispatch, record_template_progress,
)
from contents.core_services.warmup_template_renderer import WarmupTemplateError
from contents.models import AIUsageLog, AppSettings, Content, ContentDelivery
from contents.tasks import generate_warmup_template_task, run_daily_warmup_template_task


@override_settings(OPENAI_API_KEY="", WARMUP_TEMPLATE_PHOTO_PROVIDER="picsum",
                   CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class WarmupProgressTests(TestCase):
    def setUp(self):
        cache.clear(); self.addCleanup(cache.clear)
        self.user = get_user_model().objects.create_superuser("progress-admin", password="test-password")
        self.client.force_login(self.user)
        self.config = AppSettings.objects.create(is_active=True, daily_warmup_template_count=2,
                                                  daily_warmup_template_delay_seconds=3)
        self.run_url = reverse("admin:contents_warmuptemplategenerationsettings_run_now")
        self.status_url = reverse("admin:contents_warmuptemplategenerationsettings_status")

    def saved(self, batch, sequence=0):
        return Content.objects.create(title=f"Warmup Template {batch['batch_key']} #{sequence + 1:03d}",
                                      content_type="warmup_template", generated_content="test", status="generated")

    @patch("contents.tasks.run_daily_warmup_template_task.delay")
    def test_button_returns_progress_then_saved_previews_without_page_refresh(self, enqueue):
        response = self.client.post(self.run_url, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 202)
        progress = response.json()
        self.assertEqual(progress["state"], "queued")
        self.assertEqual(progress["total"], 2)
        self.assertGreater(progress["cooldown_seconds"], 0)
        batch = cache.get(batch_cache_key(progress["batch_key"]))
        record_batch_dispatch(batch["batch_key"], 2)
        first = self.saved(batch)
        second = self.saved(batch, 1)
        result = self.client.get(progress["status_url"])
        self.assertEqual(result.json()["state"], "complete")
        self.assertTrue(result.json()["terminal"])
        self.assertEqual([row["id"] for row in result.json()["results"]], [first.pk, second.pk])
        self.assertEqual(result.json()["summary"]["today_count"], 2)
        self.assertIn(f"/{second.pk}/change/#warmup-preview", result.json()["summary"]["latest_url"])
        self.assertIn(f"/{first.pk}/change/#warmup-preview", result.json()["results"][0]["preview_url"])
        self.assertIn(f"/{first.pk}/download/", result.json()["results"][0]["download_url"])
        self.assertIn("no-cache", result["Cache-Control"])
        duplicate = self.client.post(self.run_url, HTTP_ACCEPT="application/json")
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["progress"]["ready"], 2)
        enqueue.assert_called_once()

    @patch("contents.tasks.run_daily_warmup_template_task.delay")
    def test_progress_survives_reload_on_both_lists_and_settings_detail(self, enqueue):
        response = self.client.post(self.run_url)
        batch = cache.get(LATEST_KEY)
        urls = [reverse("admin:contents_warmuptemplate_changelist"),
                reverse("admin:contents_warmuptemplategenerationsettings_changelist"),
                reverse("admin:contents_warmuptemplategenerationsettings_change", args=[self.config.pk])]
        for url in urls:
            result = self.client.get(url, {"batch": batch})
            self.assertEqual(result.status_code, 200)
            self.assertContains(result, batch)
            self.assertContains(result, "warmup_generation.js")
            self.assertContains(result, '/static/admin/warmup_generation.js?v=20261117-buttons')
            self.assertNotContains(result, 'warmup_generation.js%3F')
            self.assertContains(result, "Your request is queued")
        self.assertEqual(self.client.get(response["Location"]).status_code, 200)

    def test_progress_uses_only_its_batch_and_reports_partial_failure(self):
        batch = create_manual_batch(self.config)
        first = self.saved(batch)
        Content.objects.create(title="Unrelated template", content_type="warmup_template")
        record_batch_dispatch(batch["batch_key"], 2)
        record_template_progress(batch["batch_key"], 1, "failed", "Photo service unavailable.")
        progress = manual_batch_progress(batch["batch_key"])
        self.assertEqual((progress["state"], progress["ready"], progress["failed"]), ("partial", 1, 1))
        self.assertEqual(progress["results"], [{"id": first.pk, "number": 1}])
        self.assertIn("Photo service unavailable.", progress["errors"])
        self.saved(batch, 1)  # A successful recovery wins over a stale failure marker.
        self.assertEqual(manual_batch_progress(batch["batch_key"])["state"], "complete")

    @patch("contents.tasks.run_daily_warmup_template_task.delay", side_effect=ConnectionError("private broker address"))
    def test_queue_failure_is_visible_and_allows_retry(self, enqueue):
        response = self.client.post(self.run_url, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["progress"]["state"], "failed")
        self.assertNotIn("private broker", response.content.decode())
        self.assertIsNone(cache.get(COOLDOWN_KEY))

    @patch("contents.tasks.generate_warmup_template_task.apply_async")
    def test_scheduler_uses_submitted_count_and_reports_partial_dispatch(self, enqueue):
        batch = create_manual_batch(self.config)
        self.config.daily_warmup_template_count = 9
        self.config.save()
        enqueue.side_effect = [None, ConnectionError("private")]
        with self.assertRaises(ConnectionError):
            run_daily_warmup_template_task.run(force=True, batch_key=batch["batch_key"])
        self.assertEqual(enqueue.call_count, 2)
        progress = manual_batch_progress(batch["batch_key"])
        self.assertEqual((progress["total"], progress["failed"], progress["pending"]), (2, 1, 1))
        self.saved(batch)
        self.assertEqual(manual_batch_progress(batch["batch_key"])["state"], "partial")

    def test_worker_tracks_saved_output_without_ai_or_delivery(self):
        self.config.daily_warmup_template_count = 1
        batch = create_manual_batch(self.config)
        record_batch_dispatch(batch["batch_key"], 1)
        photo = {**SAMPLE_PHOTO, "id": "1018", "provider": "picsum"}
        with patch("contents.core_services.warmup_templates._get_remote_photo", return_value=photo), patch(
            "contents.core_services.ai.client.responses.create", side_effect=AssertionError("No AI calls allowed")
        ):
            result = generate_warmup_template_task.run(batch["run_date"], 0, batch["batch_key"])
        self.assertEqual(manual_batch_progress(batch["batch_key"])["state"], "complete")
        self.assertIn('width="400"', Content.objects.get(pk=result["content_id"]).generated_content)
        self.assertFalse(AIUsageLog.objects.exists())
        self.assertFalse(ContentDelivery.objects.exists())

    def test_terminal_worker_failure_is_visible(self):
        self.config.daily_warmup_template_count = 1
        batch = create_manual_batch(self.config)
        record_batch_dispatch(batch["batch_key"], 1)
        with patch("contents.tasks.generate_warmup_template", side_effect=WarmupTemplateError("No eligible photo.")):
            with self.assertRaises(WarmupTemplateError):
                generate_warmup_template_task.run(batch["run_date"], 0, batch["batch_key"])
        progress = manual_batch_progress(batch["batch_key"])
        self.assertEqual(progress["state"], "failed")
        self.assertEqual(progress["errors"], ["No eligible photo."])

    def test_delayed_expired_and_permission_states_do_not_claim_success(self):
        batch = create_manual_batch(self.config)
        batch["created_at"] -= 400
        cache.set(batch_cache_key(batch["batch_key"]), batch)
        self.assertEqual(manual_batch_progress(batch["batch_key"])["state"], "delayed")
        self.assertEqual(self.client.get(self.status_url, {"batch": "../../other"}).status_code, 404)
        self.assertEqual(self.client.post(self.status_url).status_code, 405)
        viewer = get_user_model().objects.create_user("unprivileged", is_staff=True)
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(self.status_url, {"batch": batch["batch_key"]}).status_code, 403)
        cache.delete(batch_cache_key(batch["batch_key"]))
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.status_url, {"batch": batch["batch_key"]}).status_code, 404)

    def test_today_counter_and_latest_preview_exclude_standard_content(self):
        template = Content.objects.create(title="Template", content_type="warmup_template")
        Content.objects.create(title="Newer regular content", content_type="standard")
        page = self.client.get(reverse("admin:contents_warmuptemplategenerationsettings_change", args=[self.config.pk]))
        status = page.context_data["cg_template_status"]
        self.assertEqual(status["today_count"], 1)
        self.assertIn(f"/{template.pk}/", status["latest_url"])
