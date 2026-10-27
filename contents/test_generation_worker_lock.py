from concurrent.futures import ThreadPoolExecutor
from threading import Event

from django.db import close_old_connections
from django.test import TransactionTestCase

from contents.core_services.generation.lock import generation_job_lock


class GenerationWorkerLockTests(TransactionTestCase):
    def test_second_worker_cannot_claim_same_job_but_other_jobs_continue(self):
        acquired = Event()
        release = Event()

        def first_worker():
            close_old_connections()
            try:
                with generation_job_lock(987654) as claimed:
                    self.assertTrue(claimed)
                    acquired.set()
                    self.assertTrue(release.wait(timeout=10))
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(first_worker)
            try:
                self.assertTrue(acquired.wait(timeout=10))
                with generation_job_lock(987654) as claimed:
                    self.assertFalse(claimed)
                with generation_job_lock(987655) as claimed:
                    self.assertTrue(claimed)
            finally:
                release.set()
            future.result(timeout=10)
        with generation_job_lock(987654) as claimed:
            self.assertTrue(claimed)

    def test_worker_error_releases_claim(self):
        with self.assertRaises(ValueError):
            with generation_job_lock(987654):
                raise ValueError("worker failed")
        with generation_job_lock(987654) as claimed:
            self.assertTrue(claimed)
