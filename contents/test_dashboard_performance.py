from datetime import datetime, timedelta, time
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from contents.admin.intelligence_dashboard import get_dashboard_metrics
from contents.models import Content


@override_settings(TIME_ZONE="Asia/Tehran")
class DashboardMetricsTests(TestCase):
    def test_week_and_today_counts_respect_local_midnight(self):
        today = timezone.localdate()
        midnight = timezone.make_aware(datetime.combine(today, time.min))
        entries = [
            (midnight - timedelta(days=6, seconds=1), "standard"),
            (midnight - timedelta(days=6), "standard"),
            (midnight + timedelta(hours=23, minutes=59), "greeting"),
            (midnight + timedelta(days=1), "greeting"),
        ]
        for index, (created_at, kind) in enumerate(entries):
            content = Content.objects.create(title=f"content {index}", generated_content="Body", content_type=kind)
            Content.objects.filter(pk=content.pk).update(created_at=created_at)

        with CaptureQueriesContext(connection) as queries:
            metrics = get_dashboard_metrics()

        self.assertEqual(metrics["content_total"], 4)
        self.assertEqual(metrics["content_this_week"], 2)
        self.assertEqual(metrics["content_today"], 1)
        self.assertEqual(metrics["greeting_total"], 2)
        self.assertEqual(metrics["greetings_this_week"], 1)
        self.assertEqual(metrics["greeting_today"], 1)
        self.assertEqual(sum(metrics["daily_counts"]), 2)
        self.assertLessEqual(len(queries), 12)

    def test_usage_estimate_counts_cached_tokens_and_never_assumes_unknown_prices(self):
        from contents.models import AIUsageLog
        AIUsageLog.objects.create(model_name="gpt-6-luna", generation_type="greeting",
                                  input_tokens=1000, cached_input_tokens=400, output_tokens=200)
        usage = get_dashboard_metrics()["usage"]
        self.assertEqual(usage["requests"], 1)
        self.assertEqual(usage["tokens"], 1200)
        self.assertAlmostEqual(usage["estimated_cost"], 0.000164)
        self.assertEqual(sum(usage["daily_tokens"]), 1200)
        AIUsageLog.objects.create(model_name="unknown-model", input_tokens=100)
        self.assertIsNone(get_dashboard_metrics()["usage"]["estimated_cost"])

    def test_no_usage_is_not_reported_as_zero_dollar_spend(self):
        metrics = get_dashboard_metrics()
        self.assertIsNone(metrics["usage"]["estimated_cost"])
        self.assertIsNone(metrics["greeting_success_rate"])
        self.assertIsNone(metrics["delivery_success_rate"])

    def test_thirty_day_window_includes_older_output_and_excludes_future_output(self):
        today = timezone.localdate()
        midnight = timezone.make_aware(datetime.combine(today, time.min))
        old = Content.objects.create(title="Older greeting", generated_content="Body", content_type="greeting")
        Content.objects.filter(pk=old.pk).update(created_at=midnight-timedelta(days=20))
        self.assertEqual(get_dashboard_metrics(7)["greetings_this_week"], 0)
        monthly = get_dashboard_metrics(30)
        self.assertEqual(monthly["greetings_this_week"], 1)
        self.assertEqual(len(monthly["daily_labels"]), 30)
        self.assertEqual(get_dashboard_metrics(999)["period_days"], 7)
        self.assertEqual(get_dashboard_metrics("invalid")["period_days"], 7)


    def test_daily_tokens_split_streams_and_local_dates_without_double_counting_cache(self):
        from contents.models import AIUsageLog
        today = timezone.localdate()
        midnight = timezone.make_aware(datetime.combine(today, time.min))
        entries = [
            ("greeting", 100, 20, 60, midnight-timedelta(seconds=1), "gpt-6-luna"),
            ("greeting", 30, 10, 10, midnight, "gpt-6-luna"),
            ("greeting", 20, 5, 0, midnight+timedelta(hours=1), "another-model"),
            ("standard", 80, 40, 20, midnight, "gpt-6-luna"),
            ("email_reply", 900, 100, 0, midnight, "gpt-6-luna"),
            ("", 500, 100, 0, midnight, "gpt-6-luna"),
            ("greeting", 11, 4, 0, midnight-timedelta(days=20), "gpt-6-luna"),
            ("greeting", 999, 999, 0, midnight+timedelta(days=1), "gpt-6-luna"),
        ]
        for kind, input_tokens, output_tokens, cached, created_at, model in entries:
            log = AIUsageLog.objects.create(generation_type=kind, model_name=model,
                input_tokens=input_tokens, output_tokens=output_tokens, cached_input_tokens=cached)
            AIUsageLog.objects.filter(pk=log.pk).update(created_at=created_at)
        with CaptureQueriesContext(connection) as queries:
            metrics = get_dashboard_metrics(7)
        self.assertLessEqual(len(queries), 12)
        daily = metrics["usage"]["daily_by_type"]
        self.assertEqual(set(daily), {"greeting", "standard"})
        self.assertEqual(len(daily["greeting"]), len(metrics["daily_labels"]))
        self.assertEqual(daily["greeting"][-2], {"requests": 1, "input": 100, "output": 20, "tokens": 120})
        self.assertEqual(daily["greeting"][-1], {"requests": 2, "input": 50, "output": 15, "tokens": 65})
        self.assertEqual(daily["standard"][-1], {"requests": 1, "input": 80, "output": 40, "tokens": 120})
        self.assertEqual(sum(day["tokens"] for day in daily["greeting"]), 185)
        monthly = get_dashboard_metrics(30)["usage"]["daily_by_type"]
        self.assertEqual(len(monthly["greeting"]), 30)
        self.assertEqual(sum(day["tokens"] for day in monthly["greeting"]), 200)

    def test_days_without_records_are_distinguishable_from_recorded_zero_usage(self):
        from contents.models import AIUsageLog
        AIUsageLog.objects.create(generation_type="greeting", model_name="gpt-6-luna", input_tokens=0, output_tokens=0)
        daily = get_dashboard_metrics()["usage"]["daily_by_type"]
        self.assertEqual(daily["greeting"][-1]["tokens"], 0)
        self.assertEqual(daily["greeting"][-1]["requests"], 1)
        self.assertEqual(daily["greeting"][-2]["requests"], 0)
        self.assertTrue(all(day["requests"] == 0 for day in daily["standard"]))


@override_settings(SECURE_SSL_REDIRECT=False)
class DashboardAccessTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.core.cache import cache
        cache.clear()
        self.user = get_user_model().objects.create_user(username="dashboard-reviewer", password="test-only", is_staff=True)

    def test_metrics_require_active_staff_session(self):
        url = "/dashboard/metrics/"
        self.assertEqual(self.client.get(url).status_code, 302)
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, 302)
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(self.client.post(url).status_code, 405)

    def test_periods_cache_separately_and_second_read_avoids_database_work(self):
        from contents.admin.intelligence_dashboard import cached_dashboard_metrics
        first = cached_dashboard_metrics(7)
        with self.assertNumQueries(0):
            self.assertEqual(cached_dashboard_metrics(7), first)
        self.assertEqual(cached_dashboard_metrics(30)["period_days"], 30)

    def test_dashboard_renders_all_navigation_and_safe_json(self):
        self.client.force_login(self.user)
        Content.objects.create(title="HTML test", generated_content='</script><script>alert("test")</script>', content_type="greeting", status="generated")
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Make every greeting count")
        self.assertContains(response, 'id="dashboard-data"')
        self.assertNotContains(response, '</script><script>alert("test")</script>')
        self.assertContains(response, "csrfmiddlewaretoken")
