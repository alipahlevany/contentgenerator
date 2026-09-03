from django.test import SimpleTestCase

from config.celery import app


class CeleryRouteTests(SimpleTestCase):
    def test_admin_generation_tasks_use_consumed_generation_queue(self):
        expected_generation_tasks = {
            "contents.tasks.run_generation_job_task",
            "contents.tasks.run_daily_generation_task",
            "contents.tasks.run_daily_reply_generation_task",
            "contents.tasks.run_daily_greeting_generation_task",
            "contents.tasks.recover_stuck_generation_jobs",
        }

        for task_name in expected_generation_tasks:
            with self.subTest(task_name=task_name):
                self.assertEqual(
                    app.conf.task_routes[task_name]["queue"],
                    "generation",
                )
