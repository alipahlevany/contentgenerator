from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.db import close_old_connections, transaction
from django.test import RequestFactory, TransactionTestCase
from django.utils import timezone

from contents.admin.generation_job import GenerationJobAdmin
from contents.core_services.generation.job_service import _persist_generated_content
from contents.core_services.generation.lock import generation_job_lock
from contents.core_services.generation_jobs.actions import start_generation_job
from contents.core_services.job_health import MAX_AUTOMATIC_RECOVERIES, recover_stuck_jobs
from contents.models import Content, ContentDelivery, ExternalClient, GenerationJob
from contents.services import run_generation_job
from contents.tasks import run_generation_job_task


class GenerationRecoveryTests(TransactionTestCase):
    def stale_job(self, minutes=10, **kwargs):
        values = dict(status="running", count=10, generated_count=4,
                      attempted_count=6, skipped_count=2, current_step=6,
                      last_attempt_at=timezone.now()-timedelta(minutes=minutes))
        values.update(kwargs)
        job = GenerationJob.objects.create(**values)
        GenerationJob.objects.filter(pk=job.pk).update(updated_at=timezone.now()-timedelta(minutes=minutes))
        return job

    @patch("contents.tasks.queue_generation_job")
    def test_interrupted_job_is_queued_once_with_progress_preserved(self, queue):
        job = self.stale_job(generation_type="greeting")
        self.assertEqual(recover_stuck_jobs(), 1)
        self.assertEqual(recover_stuck_jobs(), 0)
        queue.assert_called_once_with(job.pk, "greeting", auto_resume=True)
        job.refresh_from_db()
        self.assertEqual((job.status, job.recovery_count), ("pending", 1))
        self.assertEqual((job.generated_count, job.attempted_count, job.skipped_count, job.current_step), (4, 6, 2, 6))

    @patch("contents.tasks.queue_generation_job")
    def test_slow_live_worker_is_untouched_until_it_releases_ownership(self, queue):
        job = self.stale_job()
        ready, release = Event(), Event()

        def worker():
            close_old_connections()
            try:
                with generation_job_lock(job.pk) as acquired:
                    self.assertTrue(acquired)
                    ready.set()
                    self.assertTrue(release.wait(10))
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker)
            try:
                self.assertTrue(ready.wait(10))
                self.assertEqual(recover_stuck_jobs(), 0)
                job.refresh_from_db()
                self.assertEqual(job.status, "running")
                queue.assert_not_called()
            finally:
                release.set()
            future.result(timeout=10)
        self.assertEqual(recover_stuck_jobs(), 1)

    @patch("contents.tasks.queue_generation_job")
    def test_concurrent_monitors_dispatch_once(self, queue):
        self.stale_job()

        def monitor():
            close_old_connections()
            try:
                return recover_stuck_jobs()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(monitor) for _ in range(2)]
            self.assertEqual(sum(f.result(timeout=10) for f in futures), 1)
        self.assertEqual(queue.call_count, 1)

    @patch("contents.tasks.queue_generation_job")
    def test_stopped_failed_drafts_and_recent_jobs_are_not_started(self, queue):
        self.stale_job(status="stopped")
        self.stale_job(status="failed")
        self.stale_job(should_stop=True)
        self.stale_job(minutes=1)
        self.stale_job(minutes=90, status="pending", last_attempt_at=None, generated_count=0)
        self.stale_job(minutes=10, status="pending")
        self.assertEqual(recover_stuck_jobs(), 0)
        queue.assert_not_called()

    @patch("contents.tasks.queue_generation_job")
    def test_lost_continuation_is_repaired_after_pending_grace_period(self, queue):
        job = self.stale_job(minutes=61, status="pending")
        self.assertEqual(recover_stuck_jobs(), 1)
        queue.assert_called_once_with(job.pk, "standard", auto_resume=True)

    @patch("contents.tasks.queue_generation_job")
    def test_finished_work_is_completed_without_another_generation(self, queue):
        job = self.stale_job(generated_count=10)
        self.assertEqual(recover_stuck_jobs(), 0)
        job.refresh_from_db()
        self.assertEqual(job.status, "completed")
        queue.assert_not_called()

    @patch("contents.tasks.queue_generation_job")
    def test_recovery_budget_is_bounded_and_failed_job_stays_failed(self, queue):
        job = self.stale_job(recovery_count=MAX_AUTOMATIC_RECOVERIES)
        self.assertEqual(recover_stuck_jobs(), 0)
        job.refresh_from_db()
        self.assertEqual((job.status, job.generated_count), ("failed", 4))
        with patch("contents.core_services.generation.job_service.generate_content") as generate:
            run_generation_job(job.pk)
            generate.assert_not_called()
        queue.assert_not_called()

    @patch("contents.tasks.queue_generation_job")
    def test_broker_failure_preserves_recoverable_state_and_other_jobs_continue(self, queue):
        first, second = self.stale_job(), self.stale_job()
        queue.side_effect = [RuntimeError("broker unavailable"), None]
        with self.assertLogs("contents.core_services.job_health", level="ERROR"):
            self.assertEqual(recover_stuck_jobs(), 1)
        first.refresh_from_db()
        self.assertEqual((first.status, first.recovery_count, first.generated_count), ("pending", 1, 4))
        GenerationJob.objects.filter(pk=first.pk).update(updated_at=timezone.now()-timedelta(minutes=61))
        queue.reset_mock(side_effect=True)
        self.assertEqual(recover_stuck_jobs(), 1)
        queue.assert_called_once_with(first.pk, "standard", auto_resume=True)

    @patch("contents.tasks.run_generation_job")
    @patch("contents.tasks.queue_generation_job")
    def test_user_stop_after_recovery_is_respected_by_queued_task(self, queue, run):
        job = self.stale_job()
        recover_stuck_jobs()
        GenerationJob.objects.filter(pk=job.pk).update(status="stopped", should_stop=True)
        run_generation_job_task.run(job.pk, auto_resume=True)
        run.assert_not_called()

    @patch("contents.core_services.generation_jobs.actions.queue_generation_job")
    def test_explicit_api_resume_resets_recovery_budget_only(self, queue):
        client = ExternalClient.objects.create(name="Recovery API", code="recovery-api")
        job = self.stale_job(status="failed", external_client=client, recovery_count=3)
        result = start_generation_job(job_id=job.pk, external_client=client)
        self.assertTrue(result.success)
        job.refresh_from_db()
        self.assertEqual((job.recovery_count, job.generated_count, job.attempted_count), (0, 4, 6))
        queue.assert_called_once_with(job.pk, "standard")

    @patch("contents.admin.generation_job.queue_generation_job")
    def test_explicit_admin_resume_resets_recovery_budget(self, queue):
        job = self.stale_job(status="failed", recovery_count=3)
        model_admin = GenerationJobAdmin(GenerationJob, AdminSite())
        with patch.object(model_admin, "message_user"):
            model_admin.start_job(RequestFactory().get("/"), job.pk)
        job.refresh_from_db()
        self.assertEqual((job.recovery_count, job.generated_count), (0, 4))
        queue.assert_called_once_with(job.pk, "standard")


class GenerationPersistenceTests(TransactionTestCase):
    def persist(self, job):
        return _persist_generated_content(job=job, title="Recovery test", content_body="Unique body",
            language=None, topic=None, audience=None, goal=None, prompt_template=None,
            selected_rules=[], user_prompt="Test", fingerprint="test-fingerprint")

    def test_interruption_rolls_back_output_counter_and_delivery_together(self):
        job = GenerationJob.objects.create(count=2, generated_count=1)
        client = ExternalClient.objects.create(name="Recovery delivery", code="recovery-delivery")
        dispatched = []

        def queue(content):
            ContentDelivery.objects.create(content=content, client=client, destination_url="https://example.com")
            transaction.on_commit(lambda: dispatched.append(content.pk))

        with patch("contents.core_services.generation.job_service.queue_content_deliveries", side_effect=queue), patch(
            "contents.core_services.generation.job_service.handle_generation_success", side_effect=SystemExit("interrupted")
        ):
            with self.assertRaises(SystemExit):
                self.persist(job)
        job.refresh_from_db()
        self.assertEqual(job.generated_count, 1)
        self.assertFalse(Content.objects.filter(generation_job=job).exists())
        self.assertFalse(ContentDelivery.objects.exists())
        self.assertEqual(dispatched, [])

    def test_success_commits_output_and_progress_before_delivery_dispatch(self):
        job = GenerationJob.objects.create(count=2, generated_count=1)
        observed = []

        def queue(content):
            transaction.on_commit(lambda: observed.append((
                Content.objects.filter(pk=content.pk).exists(),
                GenerationJob.objects.get(pk=job.pk).generated_count,
            )))

        with patch("contents.core_services.generation.job_service.queue_content_deliveries", side_effect=queue), patch(
            "contents.core_services.generation.job_service.handle_generation_success"
        ):
            result = self.persist(job)
        self.assertTrue(result.created)
        self.assertEqual(observed, [(True, 2)])
