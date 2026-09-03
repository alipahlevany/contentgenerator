from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase

from contents.models import (
    Audience,
    Content,
    GenerationJob,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)
from contents.services import run_generation_job


class GenerationJobBoundsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.language = Language.objects.create(
            name="English",
            code="en",
        )
        cls.topic = Topic.objects.create(
            name="Topic",
        )
        cls.audience = Audience.objects.create(
            name="Audience",
        )
        cls.goal = Goal.objects.create(
            name="Goal",
        )
        cls.template = PromptTemplate.objects.create(
            name="Template",
            system_prompt="System",
            user_prompt_template="User",
        )

    def settings(self, runtime=3600):
        return SimpleNamespace(
            generation_attempt_multiplier=10,
            generation_minimum_attempts=50,
            generation_max_runtime_seconds=runtime,
        )

    def test_deleting_job_preserves_generated_content_and_greeting(self):
        job = GenerationJob.objects.create(generation_type="greeting")
        content = Content.objects.create(
            title="Standard content",
            content_type="standard",
            generation_job=job,
            prompt="Prompt",
            generated_content="Body",
        )
        greeting = Content.objects.create(
            title="Warm Email Greeting",
            content_type="greeting",
            generation_job=job,
            prompt="Prompt",
            generated_content="Hello, I hope you are doing well today.",
        )

        job.delete()

        self.assertTrue(Content.objects.filter(pk=content.pk).exists())
        self.assertTrue(Content.objects.filter(pk=greeting.pk).exists())
        self.assertIsNone(
            Content.objects.get(pk=content.pk).generation_job_id
        )
        self.assertIsNone(
            Content.objects.get(pk=greeting.pk).generation_job_id
        )

    def choice(self):
        return (
            self.language,
            self.topic,
            self.audience,
            self.goal,
            self.template,
        )

    def create_fake_generator(self):
        fake_generator = Mock()

        fake_generator.build_prompt_data.return_value = {
            "system_prompt": "System",
            "user_prompt": "Prompt",
            "fallback_title": "Title",
        }

        fake_generator.extract_output.return_value = (
            "Title",
            "Body",
        )

        return fake_generator

    def run_with_generation(
        self,
        job,
        generated,
        *,
        blocked_keyword_results=None,
        duplicate_result=(False, "", "hash"),
        cleaned_content="Bad content",
    ):
        choice = self.choice()
        fake_generator = self.create_fake_generator()

        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "contents.core_services.generation.job_service.get_app_settings",
                    return_value=self.settings(),
                )
            )

            stack.enter_context(
                patch(
                    "contents.core_services.generation.job_service.get_job_generation_pool_v2",
                    return_value={
                        "language": {"items": [choice[0]]},
                        "topic": {"items": [choice[1]]},
                        "audience": {"items": [choice[2]]},
                        "goal": {"items": [choice[3]]},
                        "prompt_template": {"items": [choice[4]]},
                        "content_rule": {"items": []},
                    },
                )
            )

            stack.enter_context(
                patch(
                    "contents.core_services.generation.job_service.get_generator",
                    return_value=fake_generator,
                )
            )

            stack.enter_context(
                patch(
                    "contents.core_services.generation.job_service.reserve_generation_context",
                    return_value=SimpleNamespace(
                        acquired=True,
                        context={
                            "language": choice[0],
                            "topic": choice[1],
                            "audience": choice[2],
                            "goal": choice[3],
                            "prompt_template": choice[4],
                            "selected_rules": [],
                        },
                        fingerprint="test-generation-fingerprint",
                        record=None,
                        reason=None,
                        attempts=1,
                    ),
                )
            )

            stack.enter_context(
                patch(
                    "contents.core_services.generation.job_service.generate_content",
                    side_effect=generated,
                )
            )

            if blocked_keyword_results is None:
                stack.enter_context(
                    patch(
                        "contents.core_services.generation.job_service.contains_blocked_keyword",
                        return_value=(False, None),
                    )
                )
            else:
                stack.enter_context(
                    patch(
                        "contents.core_services.generation.job_service.contains_blocked_keyword",
                        side_effect=blocked_keyword_results,
                    )
                )

            stack.enter_context(
                patch(
                    "contents.core_services.generation.job_service.remove_blocked_keywords",
                    return_value=cleaned_content,
                )
            )

            stack.enter_context(
                patch(
                    "contents.core_services.generation.job_service.is_duplicate_content",
                    return_value=duplicate_result,
                )
            )

            stack.enter_context(
                patch(
                    "contents.core_services.generation_outcome."
                    "record_generation_event"
                )
            )

            stack.enter_context(
                patch(
                    "contents.core_services.generation_outcome."
                    "run_dataset_refill"
                )
            )

            stack.enter_context(
                patch(
                    "contents.core_services.generation_outcome."
                    "optimize_dataset_weights"
                )
            )

            stack.enter_context(
                patch(
                    "contents.core_services.generation_outcome.log_job"
                )
            )

            stack.enter_context(
                patch(
                    "contents.core_services.generation.job_service.log_job"
                )
            )

            run_generation_job(job.pk)

    def test_repeated_empty_output_stops_at_attempt_limit(self):
        job = GenerationJob.objects.create(
            count=5,
            max_attempts=2,
        )

        self.run_with_generation(
            job,
            ["", ""],
        )

        job.refresh_from_db()

        self.assertEqual(job.status, "failed")
        self.assertEqual(job.attempted_count, 2)
        self.assertEqual(job.empty_output_count, 2)
        self.assertEqual(job.skipped_count, 2)
        self.assertIn("Attempts: 2/2", job.error_message)

    def test_repeated_generation_errors_increment_failed_count(self):
        job = GenerationJob.objects.create(
            count=5,
            max_attempts=2,
        )

        self.run_with_generation(
            job,
            [
                RuntimeError("temporary"),
                RuntimeError("temporary"),
            ],
        )

        job.refresh_from_db()

        self.assertEqual(job.status, "failed")
        self.assertEqual(job.attempted_count, 2)
        self.assertEqual(job.failed_count, 2)
        self.assertEqual(job.generated_count, 0)

    def test_blocked_keyword_failure_increments_failed_count(self):
        job = GenerationJob.objects.create(
            count=5,
            max_attempts=1,
        )

        self.run_with_generation(
            job,
            ["Bad content"],
            blocked_keyword_results=[
                (True, "bad"),
                (True, "bad"),
            ],
            cleaned_content="Bad content",
        )

        job.refresh_from_db()

        self.assertEqual(job.status, "failed")
        self.assertEqual(job.failed_count, 1)
        self.assertEqual(job.attempted_count, 1)
        self.assertEqual(job.skipped_count, 1)
        self.assertEqual(job.generated_count, 0)

    def test_repeated_duplicates_increment_duplicate_count(self):
        job = GenerationJob.objects.create(
            count=5,
            max_attempts=2,
        )

        self.run_with_generation(
            job,
            [
                "Generated",
                "Generated",
            ],
            duplicate_result=(
                True,
                "duplicate",
                "hash",
            ),
        )

        job.refresh_from_db()

        self.assertEqual(job.status, "failed")
        self.assertEqual(job.duplicate_count, 2)
        self.assertEqual(job.attempted_count, 2)
        self.assertEqual(job.generated_count, 0)

    def test_runtime_limit_pauses_and_resumes_without_losing_progress(self):
        job = GenerationJob.objects.create(
            count=5,
            generated_count=2,
        )

        choice = self.choice()

        with patch(
            "contents.core_services.generation.job_service.get_app_settings",
            return_value=self.settings(runtime=1),
        ), patch(
            "contents.core_services.generation.job_service.get_job_generation_pool_v2",
            return_value={
                "language": {"items": [choice[0]]},
                "topic": {"items": [choice[1]]},
                "audience": {"items": [choice[2]]},
                "goal": {"items": [choice[3]]},
                "prompt_template": {"items": [choice[4]]},
                "content_rule": {"items": []},
            },
        ), patch(
            "contents.core_services.generation.job_service.time.monotonic",
            side_effect=[0, 2],
        ), patch(
            "contents.core_services.generation.job_service.log_job"
        ), patch(
            "contents.tasks.run_generation_job_task.apply_async"
        ) as apply_async:
            run_generation_job(job.pk)

        job.refresh_from_db()

        self.assertEqual(job.status, "pending")
        self.assertEqual(job.generated_count, 2)
        self.assertEqual(job.attempted_count, 0)
        self.assertIn("runtime limit", job.error_message)
        self.assertIn("continuing automatically", job.error_message)
        apply_async.assert_called_once_with(
            args=[job.id],
            kwargs={"auto_resume": True},
            countdown=2,
        )

    def test_normal_generation_still_completes(self):
        job = GenerationJob.objects.create(
            count=1,
            max_attempts=2,
        )

        self.run_with_generation(
            job,
            ["Generated"],
        )

        job.refresh_from_db()

        self.assertEqual(job.status, "completed")
        self.assertEqual(job.generated_count, 1)
        self.assertEqual(job.attempted_count, 1)
        self.assertEqual(job.failed_count, 0)
        self.assertEqual(job.duplicate_count, 0)
        self.assertEqual(job.empty_output_count, 0)
        self.assertEqual(Content.objects.count(), 1)

        content = Content.objects.get()

        self.assertEqual(content.title, "Title")
        self.assertEqual(content.generated_content, "Body")
        self.assertEqual(content.content_hash, "hash")
        self.assertEqual(content.generation_job_id, job.pk)
