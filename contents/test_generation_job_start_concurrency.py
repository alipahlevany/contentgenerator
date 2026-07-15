from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock, local
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.urls import reverse

from rest_framework.test import APIClient

from contents.models import ExternalClient, GenerationJob


class GenerationJobStartConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.client_record = ExternalClient.objects.create(
            name="Concurrent generation client",
            code="concurrent-generation-client",
            api_key="concurrent-generation-api-key",
            is_active=True,
        )

    def _run_concurrent_requests(self, job, actions):
        request_barrier = Barrier(len(actions), timeout=10)
        results = []
        result_lock = Lock()
        save_order = []
        thread_context = local()
        original_save = GenerationJob.save

        def tracked_save(instance, *args, **kwargs):
            result = original_save(instance, *args, **kwargs)
            action = getattr(thread_context, "action", None)
            if instance.pk == job.id and action is not None:
                with result_lock:
                    save_order.append(action)
            return result

        def worker(action):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    backend_pid = cursor.fetchone()[0]

                thread_context.action = action
                request_barrier.wait()
                api = APIClient()
                url = reverse(
                    f"contents:api-generation-job-{action}",
                    kwargs={"job_id": job.id},
                )
                response = api.post(
                    url,
                    format="json",
                    HTTP_X_API_KEY=self.client_record.api_key,
                )
                result = {
                    "action": action,
                    "backend_pid": backend_pid,
                    "status_code": response.status_code,
                    "body": response.json(),
                }
                with result_lock:
                    results.append(result)
                return result
            finally:
                close_old_connections()

        with patch.object(
            GenerationJob,
            "save",
            new=tracked_save,
        ), patch("contents.views.run_generation_job_task.delay") as delay:
            with ThreadPoolExecutor(max_workers=len(actions)) as executor:
                futures = [executor.submit(worker, action) for action in actions]
                for future in futures:
                    future.result(timeout=15)

        return results, delay, save_order

    def test_database_is_postgresql(self):
        self.assertEqual(connection.vendor, "postgresql")

    def test_two_simultaneous_starts_allow_one_claim_and_one_dispatch(self):
        job = GenerationJob.objects.create(
            count=10,
            status="pending",
            should_stop=False,
        )

        results, delay, save_order = self._run_concurrent_requests(
            job,
            ["start", "start"],
        )

        self.assertEqual(len({result["backend_pid"] for result in results}), 2)
        self.assertEqual(sorted(result["status_code"] for result in results), [200, 400])
        successful = next(result for result in results if result["status_code"] == 200)
        rejected = next(result for result in results if result["status_code"] == 400)
        self.assertEqual(successful["body"]["message"], f"Generation job #{job.id} started.")
        self.assertEqual(rejected["body"], {"detail": f"Job #{job.id} is already running."})
        delay.assert_called_once_with(job.id)
        self.assertEqual(save_order, ["start"])
        job.refresh_from_db()
        self.assertEqual(job.status, "running")
        self.assertFalse(job.should_stop)
        self.assertEqual(job.error_message, "")

    def test_two_simultaneous_resumes_allow_one_claim_and_one_dispatch(self):
        job = GenerationJob.objects.create(
            count=10,
            status="stopped",
            should_stop=True,
            generated_count=3,
            skipped_count=2,
            current_step=5,
            error_message="Previously stopped",
        )

        results, delay, save_order = self._run_concurrent_requests(
            job,
            ["start", "start"],
        )

        self.assertEqual(len({result["backend_pid"] for result in results}), 2)
        self.assertEqual(sorted(result["status_code"] for result in results), [200, 400])
        successful = next(result for result in results if result["status_code"] == 200)
        rejected = next(result for result in results if result["status_code"] == 400)
        self.assertEqual(successful["body"]["message"], f"Generation job #{job.id} resumed.")
        self.assertEqual(rejected["body"], {"detail": f"Job #{job.id} is already running."})
        delay.assert_called_once_with(job.id)
        self.assertEqual(save_order, ["start"])
        job.refresh_from_db()
        self.assertEqual(job.status, "running")
        self.assertFalse(job.should_stop)
        self.assertEqual(job.error_message, "")
        self.assertEqual(job.generated_count, 3)
        self.assertEqual(job.skipped_count, 2)
        self.assertEqual(job.current_step, 5)

    def test_two_simultaneous_stops_serialize_without_dispatch(self):
        job = GenerationJob.objects.create(
            count=10,
            status="running",
            should_stop=False,
            generated_count=3,
            skipped_count=2,
            current_step=5,
        )

        results, delay, save_order = self._run_concurrent_requests(
            job,
            ["stop", "stop"],
        )

        self.assertEqual(len({result["backend_pid"] for result in results}), 2)
        self.assertEqual(sorted(result["status_code"] for result in results), [200, 400])
        successful = next(result for result in results if result["status_code"] == 200)
        rejected = next(result for result in results if result["status_code"] == 400)
        self.assertEqual(successful["body"]["message"], f"Generation job #{job.id} stopped.")
        self.assertEqual(
            rejected["body"],
            {"detail": f"Job #{job.id} is not pending or running."},
        )
        delay.assert_not_called()
        self.assertEqual(save_order, ["stop"])
        job.refresh_from_db()
        self.assertEqual(job.status, "stopped")
        self.assertTrue(job.should_stop)
        self.assertEqual(job.error_message, "Job stopped by external API.")
        self.assertEqual(job.generated_count, 3)
        self.assertEqual(job.skipped_count, 2)
        self.assertEqual(job.current_step, 5)

    def test_two_simultaneous_starts_at_target_are_both_rejected(self):
        job = GenerationJob.objects.create(
            count=10,
            status="stopped",
            generated_count=10,
            current_step=10,
        )

        results, delay, save_order = self._run_concurrent_requests(
            job,
            ["start", "start"],
        )

        self.assertEqual(len({result["backend_pid"] for result in results}), 2)
        self.assertEqual([result["status_code"] for result in results], [400, 400])
        self.assertEqual(
            [result["body"] for result in results],
            [
                {"detail": f"Job #{job.id} is already completed (10/10)."},
                {"detail": f"Job #{job.id} is already completed (10/10)."},
            ],
        )
        delay.assert_not_called()
        self.assertEqual(save_order, [])
        job.refresh_from_db()
        self.assertEqual(job.status, "stopped")
        self.assertEqual(job.generated_count, 10)

    def test_simultaneous_start_and_stop_follow_lock_order(self):
        job = GenerationJob.objects.create(
            count=10,
            status="pending",
            should_stop=False,
        )

        results, delay, save_order = self._run_concurrent_requests(
            job,
            ["start", "stop"],
        )

        self.assertEqual(len({result["backend_pid"] for result in results}), 2)
        by_action = {result["action"]: result for result in results}
        self.assertEqual(by_action["start"]["status_code"], 200)
        self.assertEqual(
            by_action["start"]["body"]["message"],
            f"Generation job #{job.id} started.",
        )
        self.assertEqual(by_action["stop"]["status_code"], 200)
        self.assertEqual(
            by_action["stop"]["body"]["message"],
            f"Generation job #{job.id} stopped.",
        )
        delay.assert_called_once_with(job.id)
        self.assertEqual(set(save_order), {"start", "stop"})
        self.assertEqual(len(save_order), 2)
        job.refresh_from_db()
        if save_order[-1] == "start":
            self.assertEqual(job.status, "running")
            self.assertFalse(job.should_stop)
            self.assertEqual(job.error_message, "")
        else:
            self.assertEqual(job.status, "stopped")
            self.assertTrue(job.should_stop)
            self.assertEqual(job.error_message, "Job stopped by external API.")
