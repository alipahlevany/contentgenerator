"""Keep the minute-by-minute scheduler quiet until a batch is due."""

from datetime import datetime, timezone as datetime_timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from contents.tasks import _record_warmup_template_failure, run_daily_warmup_template_task


class WarmupTemplateSchedulerTests(SimpleTestCase):
    @patch("contents.tasks.AppSettings.objects.filter")
    def test_terminal_error_is_saved_for_admin_visibility(self, filter_query):
        app_settings = SimpleNamespace(save=Mock())
        filter_query.return_value.order_by.return_value.first.return_value = app_settings
        _record_warmup_template_failure(
            "2026-11-16", 2, ValueError("unexpected private detail")
        )
        self.assertIn("2026-11-16 #3", app_settings.last_warmup_template_error)
        self.assertNotIn("private detail", app_settings.last_warmup_template_error)
        self.assertIsNotNone(app_settings.last_warmup_template_error_at)
        app_settings.save.assert_called_once()

    @override_settings(WARMUP_TEMPLATE_PHOTO_PROVIDER="pexels", PEXELS_API_KEY="", OPENAI_API_KEY="test-key")
    @patch("contents.tasks.logger.error")
    @patch("contents.tasks.generate_warmup_template_task.apply_async")
    @patch("contents.tasks.cache.delete")
    @patch("contents.tasks.cache.add", return_value=True)
    @patch("contents.tasks.AppSettings.objects.filter")
    @patch("contents.tasks.timezone.localtime")
    def test_missing_key_is_only_reported_after_scheduled_time(
        self, localtime, filter_query, cache_add, _delete, enqueue, log_error
    ):
        filter_query.return_value.order_by.return_value.first.return_value = SimpleNamespace(
            auto_daily_warmup_template_enabled=True,
            daily_warmup_template_hour=5,
            daily_warmup_template_minute=0,
            last_daily_warmup_template_date=None,
        )
        localtime.return_value = datetime(2026, 11, 16, 4, 59, tzinfo=datetime_timezone.utc)
        result = run_daily_warmup_template_task.run(force=False)
        self.assertIn("time has not arrived", result)
        log_error.assert_not_called()
        enqueue.assert_not_called()
        self.assertEqual(cache_add.call_count, 1)

        cache_add.reset_mock()
        localtime.return_value = datetime(2026, 11, 16, 5, 0, tzinfo=datetime_timezone.utc)
        result = run_daily_warmup_template_task.run(force=False)
        self.assertIn("PEXELS_API_KEY", result)
        log_error.assert_called_once()
        enqueue.assert_not_called()
        self.assertEqual(cache_add.call_count, 2)
