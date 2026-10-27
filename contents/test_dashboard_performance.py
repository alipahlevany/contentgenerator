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
