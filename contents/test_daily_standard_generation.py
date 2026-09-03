from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase

from contents.models import AppSettings, GenerationJob
from contents.tasks import run_daily_generation_task


class DailyStandardGenerationTaskTests(TestCase):

    def setUp(self):
        cache.clear()

        self.settings = AppSettings.objects.create(
            auto_daily_generation_enabled=True,
            daily_generation_count=5,
            daily_generation_delay_seconds=0.5,
            daily_generation_hour=0,
            daily_generation_minute=0,
            is_active=True,
        )

    @patch("contents.tasks.run_generation_job_task.delay")
    def test_force_creates_and_queues_standard_job(
        self,
        mock_delay,
    ):
        mock_delay.return_value = Mock(id="task-123")

        result = run_daily_generation_task(force=True)

        job = GenerationJob.objects.get(
            generation_type="standard"
        )

        self.assertEqual(job.count, 5)
        self.assertEqual(job.delay_seconds, 0.5)
        mock_delay.assert_called_once_with(job.id)
        self.assertIn(f"#{job.id}", result)

    @patch("contents.tasks.run_generation_job_task.delay")
    def test_active_greeting_job_does_not_block_standard_job(
        self,
        mock_delay,
    ):
        mock_delay.return_value = Mock(id="task-123")

        GenerationJob.objects.create(
            generation_type="greeting",
            status="running",
        )

        result = run_daily_generation_task(force=True)

        standard_job = GenerationJob.objects.get(
            generation_type="standard"
        )

        mock_delay.assert_called_once_with(standard_job.id)
        self.assertIn(f"#{standard_job.id}", result)

    @patch("contents.tasks.run_generation_job_task.delay")
    def test_active_standard_job_blocks_new_standard_job(
        self,
        mock_delay,
    ):
        GenerationJob.objects.create(
            generation_type="standard",
            status="running",
        )

        result = run_daily_generation_task(force=True)

        self.assertEqual(
            result,
            (
                "Another standard generation job is already "
                "pending or running."
            ),
        )
        mock_delay.assert_not_called()
