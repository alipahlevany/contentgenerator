"""Manual template generation should not allow accidental repeat batches."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from contents.models import AppSettings
from contents.core_services.warmup_runs import LATEST_KEY


@override_settings(
    OPENAI_API_KEY="test-openai",
    WARMUP_TEMPLATE_PHOTO_PROVIDER="picsum",
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class WarmupTemplateGenerationButtonTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_superuser("template-admin", password="test-password")
        self.client.force_login(self.user)
        self.settings = AppSettings.objects.create(
            is_active=True, daily_warmup_template_count=3,
            auto_daily_warmup_template_enabled=False,
        )
        self.run_url = reverse("admin:contents_warmuptemplategenerationsettings_run_now")
        self.templates_url = reverse("admin:contents_warmuptemplate_changelist")
        self.settings_url = reverse("admin:contents_warmuptemplategenerationsettings_changelist")
        self.addCleanup(cache.clear)

    def test_both_lists_offer_post_generation_with_saved_count_when_schedule_is_off(self):
        for url, label in [(self.templates_url, "Create 3 templates"), (self.settings_url, "Generate now")]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, label)
                self.assertContains(response, f'method="post" action="{self.run_url}"')
                self.assertContains(response, 'name="csrfmiddlewaretoken"')
                self.assertContains(response, "Daily schedule: off")
                self.assertNotContains(response, 'class="warmup-generate__button" disabled')

    @patch("contents.admin.settings_sections.run_daily_warmup_template_task.delay")
    def test_click_queues_one_forced_batch_and_returns_to_templates(self, enqueue):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.run_url, {"return_to": "templates"})
        self.assertTrue(response["Location"].startswith(self.templates_url + "?batch="))
        enqueue.assert_called_once_with(force=True, batch_key=cache.get(LATEST_KEY))
        self.settings.refresh_from_db()
        self.assertFalse(self.settings.auto_daily_warmup_template_enabled)
        self.assertIsNone(self.settings.last_daily_warmup_template_date)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.run_url, {"return_to": "settings"})
        enqueue.assert_called_once()
        self.assertContains(self.client.get(self.templates_url), 'class="warmup-generate__button" disabled')

    @patch("contents.admin.settings_sections.run_daily_warmup_template_task.delay")
    def test_no_javascript_redirects_to_results_and_ignores_external_return_url(self, enqueue):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.run_url, {"return_to": "https://example.com"})
        self.assertTrue(response["Location"].startswith(self.templates_url + "?batch="))
        enqueue.assert_called_once_with(force=True, batch_key=cache.get(LATEST_KEY))

    @patch("contents.admin.settings_sections.run_daily_warmup_template_task.delay")
    def test_generation_rejects_get_and_missing_csrf(self, enqueue):
        self.assertEqual(self.client.get(self.run_url).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(self.run_url).status_code, 403)
        enqueue.assert_not_called()

    @patch("contents.admin.settings_sections.run_daily_warmup_template_task.delay")
    def test_view_only_user_cannot_generate(self, enqueue):
        viewer = get_user_model().objects.create_user("template-viewer", is_staff=True)
        viewer.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="contents", codename__in=[
                "view_warmuptemplate", "view_warmuptemplategenerationsettings",
            ]
        ))
        self.client.force_login(viewer)
        for url in (self.templates_url, self.settings_url):
            self.assertNotContains(self.client.get(url), f'method="post" action="{self.run_url}"')
        self.assertEqual(self.client.post(self.run_url).status_code, 403)
        enqueue.assert_not_called()

    @override_settings(OPENAI_API_KEY="")
    @patch("contents.admin.settings_sections.run_daily_warmup_template_task.delay")
    def test_empty_templates_can_be_queued_without_an_openai_key(self, enqueue):
        response = self.client.get(self.templates_url)
        self.assertNotContains(response, 'class="warmup-generate__button" disabled')
        self.assertNotContains(response, "OpenAI API key")
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.run_url)
        enqueue.assert_called_once_with(force=True, batch_key=cache.get(LATEST_KEY))

    @override_settings(WARMUP_TEMPLATE_PHOTO_PROVIDER="pexels", PEXELS_API_KEY="")
    @patch("contents.admin.settings_sections.run_daily_warmup_template_task.delay")
    def test_missing_photo_configuration_disables_button_and_blocks_dispatch(self, enqueue):
        response = self.client.get(self.templates_url)
        self.assertContains(response, "Configure PEXELS_API_KEY")
        self.assertContains(response, 'class="warmup-generate__button" disabled')
        self.client.post(self.run_url)
        enqueue.assert_not_called()

    @patch("contents.admin.settings_sections.run_daily_warmup_template_task.delay")
    def test_no_active_settings_disables_button_and_blocks_dispatch(self, enqueue):
        AppSettings.objects.all().update(is_active=False)
        response = self.client.get(self.settings_url)
        self.assertContains(response, "Save active generation settings")
        self.assertContains(response, 'class="warmup-generate__button" disabled')
        self.client.post(self.run_url)
        enqueue.assert_not_called()
