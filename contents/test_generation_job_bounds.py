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
                    "contents.services.get_app_settings",
                    return_value=self.settings(),
                )
            )

            stack.enter_context(
                patch(
                    "contents.services.get_job_generation_pool",
                    return_value=(
                        [choice[0]],
                        [choice[1]],
                        [choice[2]],
                        [choice[3]],
                        [choice[4]],
                        [],
                    ),
                )
            )

            stack.enter_context(
                patch(
                    "contents.services.intelligent_generation_choice",
                    return_value=choice,
                )
            )

            stack.enter_context(
                patch(
                    "contents.services.weighted_sample",
                    return_value=[],
                )
            )

            stack.enter_context(
                patch(
                    "contents.services.get_generator",
                    return_value=fake_generator,
                )
            )

            stack.enter_context(
                patch(
                    "contents.services.generate_content",
                    side_effect=generated,
                )
            )

            if blocked_keyword_results is None:
                stack.enter_context(
                    patch(
                        "contents.services.contains_blocked_keyword",
                        return_value=(False, None),
                    )
                )
            else:
                stack.enter_context(
                    patch(
                        "contents.services.contains_blocked_keyword",
                        side_effect=blocked_keyword_results,
                    )
                )

            stack.enter_context(
                patch(
                    "contents.services.remove_blocked_keywords",
                    return_value=cleaned_content,
                )
            )

            stack.enter_context(
                patch(
                    "contents.services.is_duplicate_content",
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
                    "contents.services.log_job"
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

    def test_runtime_limit_fails_without_losing_partial_progress(self):
        job = GenerationJob.objects.create(
            count=5,
            generated_count=2,
        )

        choice = self.choice()

        with patch(
            "contents.services.get_app_settings",
            return_value=self.settings(runtime=1),
        ), patch(
            "contents.services.get_job_generation_pool",
            return_value=(
                [choice[0]],
                [choice[1]],
                [choice[2]],
                [choice[3]],
                [choice[4]],
                [],
            ),
        ), patch(
            "contents.services.time.monotonic",
            side_effect=[0, 2],
        ), patch(
            "contents.services.log_job"
        ):
            run_generation_job(job.pk)

        job.refresh_from_db()

        self.assertEqual(job.status, "failed")
        self.assertEqual(job.generated_count, 2)
        self.assertEqual(job.attempted_count, 0)
        self.assertIn("runtime limit", job.error_message)

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