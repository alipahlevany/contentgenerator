from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from contents.models import AppSettings, GenerationJob
from contents.tasks import run_daily_greeting_generation_task


class DailyGreetingGenerationTaskTests(TestCase):

    def setUp(self):
        cache.clear()

        self.settings = AppSettings.objects.create(
            auto_daily_greeting_generation_enabled=True,
            daily_greeting_generation_count=7,
            daily_greeting_generation_delay_seconds=0.5,
            daily_greeting_generation_hour=0,
            daily_greeting_generation_minute=0,
            is_active=True,
        )

    @patch("contents.tasks.run_generation_job_task.delay")
    def test_force_creates_and_queues_greeting_job(
        self,
        mock_delay,
    ):
        mock_delay.return_value = Mock(id="task-123")

        result = run_daily_greeting_generation_task(
            force=True
        )

        job = GenerationJob.objects.get(
            generation_type="greeting"
        )

        self.assertEqual(job.count, 7)
        self.assertEqual(job.delay_seconds, 0.5)

        mock_delay.assert_called_once_with(job.id)

        self.assertIn(
            f"#{job.id}",
            result,
        )

        self.settings.refresh_from_db()

        self.assertEqual(
            self.settings.last_daily_greeting_generation_date,
            timezone.localdate(),
        )

    @patch("contents.tasks.run_generation_job_task.delay")
    def test_disabled_task_does_not_create_job(
        self,
        mock_delay,
    ):
        self.settings.auto_daily_greeting_generation_enabled = False
        self.settings.save(
            update_fields=[
                "auto_daily_greeting_generation_enabled"
            ]
        )

        result = run_daily_greeting_generation_task(
            force=False
        )

        self.assertEqual(
            result,
            "Daily greeting generation is disabled.",
        )

        self.assertFalse(
            GenerationJob.objects.filter(
                generation_type="greeting"
            ).exists()
        )

        mock_delay.assert_not_called()

    @patch("contents.tasks.run_generation_job_task.delay")
    def test_same_day_generation_is_not_repeated(
        self,
        mock_delay,
    ):
        self.settings.last_daily_greeting_generation_date = (
            timezone.localdate()
        )
        self.settings.save(
            update_fields=[
                "last_daily_greeting_generation_date"
            ]
        )

        result = run_daily_greeting_generation_task(
            force=False
        )

        self.assertEqual(
            result,
            "Daily greeting generation already ran today.",
        )

        self.assertFalse(
            GenerationJob.objects.filter(
                generation_type="greeting"
            ).exists()
        )

        mock_delay.assert_not_called()

    @patch("contents.tasks.run_generation_job_task.delay")
    def test_active_greeting_job_blocks_new_daily_job(
        self,
        mock_delay,
    ):
        GenerationJob.objects.create(
            generation_type="greeting",
            status="running",
            count=2,
        )

        result = run_daily_greeting_generation_task(
            force=True
        )

        self.assertIn(
            "already pending or running",
            result,
        )

        self.assertEqual(
            GenerationJob.objects.filter(
                generation_type="greeting"
            ).count(),
            1,
        )

        mock_delay.assert_not_called()

    @patch("contents.tasks.run_generation_job_task.delay")
    def test_standard_job_does_not_block_greeting_job(
        self,
        mock_delay,
    ):
        mock_delay.return_value = Mock(id="task-456")

        GenerationJob.objects.create(
            generation_type="standard",
            status="running",
            count=2,
        )

        result = run_daily_greeting_generation_task(
            force=True
        )

        self.assertIn(
            "created and started",
            result,
        )

        greeting_job = GenerationJob.objects.get(
            generation_type="greeting"
        )

        mock_delay.assert_called_once_with(
            greeting_job.id
        )

    @patch("contents.tasks.run_generation_job_task.delay")
    def test_force_ignores_enabled_and_last_run_checks(
        self,
        mock_delay,
    ):
        mock_delay.return_value = Mock(id="task-force")

        self.settings.auto_daily_greeting_generation_enabled = False
        self.settings.last_daily_greeting_generation_date = (
            timezone.localdate()
        )
        self.settings.save(
            update_fields=[
                "auto_daily_greeting_generation_enabled",
                "last_daily_greeting_generation_date",
            ]
        )

        result = run_daily_greeting_generation_task(
            force=True
        )

        self.assertIn(
            "created and started",
            result,
        )

        job = GenerationJob.objects.get(
            generation_type="greeting"
        )

        mock_delay.assert_called_once_with(
            job.id
        )
