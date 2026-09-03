from django.test import SimpleTestCase

from config.celery import app


class CeleryRouteTests(SimpleTestCase):
    def test_admin_generation_tasks_use_dedicated_generation_queues(self):
        expected_routes = {
            "contents.tasks.run_generation_job_task": "generation_standard",
            "contents.tasks.run_daily_generation_task": "generation_standard",
            "contents.tasks.run_daily_reply_generation_task": "generation_reply",
            "contents.tasks.run_daily_greeting_generation_task": "generation_greeting",
            "contents.tasks.recover_stuck_generation_jobs": "generation_standard",
        }

        for task_name, queue in expected_routes.items():
            with self.subTest(task_name=task_name):
                self.assertEqual(
                    app.conf.task_routes[task_name]["queue"],
                    queue,
                )
