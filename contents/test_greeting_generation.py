from unittest.mock import patch

from django.test import TestCase

from contents.core_services.dataset_resolver import DatasetResolver
from contents.core_services.datasets.job_pool_v2 import (
    get_job_generation_pool_v2,
)
from contents.core_services.generators.factory import get_generator
from contents.models import (
    Content,
    GenerationJob,
    GenerationType,
    GenerationTypeDataset,
    Language,
)


class GreetingGenerationTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.language = Language.objects.create(
            name="English",
            code="en",
            is_active=True,
        )

        cls.job = GenerationJob.objects.create(
            generation_type="greeting",
            count=1,
            delay_seconds=0,
            use_all_languages=True,
        )

    def test_greeting_generation_type_exists(self):
        generation_type = GenerationType.objects.get(
            key="greeting",
        )

        self.assertTrue(generation_type.is_active)

        links = (
            GenerationTypeDataset.objects
            .filter(generation_type=generation_type)
            .select_related("dataset_category")
        )

        self.assertEqual(links.count(), 1)

        link = links.get()

        self.assertEqual(
            link.dataset_category.key,
            "language",
        )
        self.assertTrue(link.is_required)

    def test_factory_returns_greeting_generator(self):
        generator = get_generator("greeting")

        self.assertEqual(
            generator.__class__.__name__,
            "GreetingGenerator",
        )

    def test_greeting_pool_contains_only_language(self):
        pool = get_job_generation_pool_v2(
            self.job
        )

        self.assertEqual(
            set(pool.keys()),
            {"language"},
        )

        self.assertEqual(
            pool["language"]["items"],
            [self.language],
        )

        self.assertTrue(
            pool["language"]["required"]
        )

    def test_dataset_resolver_returns_language_only_context(self):
        generator = get_generator("greeting")

        context = DatasetResolver.resolve(
            job=self.job,
            generator=generator,
            random_module=__import__("random"),
        )

        self.assertEqual(
            context["language"],
            self.language,
        )

        self.assertIsNone(
            context["topic"]
        )
        self.assertIsNone(
            context["audience"]
        )
        self.assertIsNone(
            context["goal"]
        )
        self.assertIsNone(
            context["prompt_template"]
        )

        self.assertEqual(
            context["selected_rules"],
            [],
        )

    def test_greeting_prompt_is_language_specific(self):
        generator = get_generator("greeting")

        prompt_data = generator.build_prompt_data(
            app_settings=None,
            language=self.language,
            topic=None,
            audience=None,
            goal=None,
            prompt_template=None,
            selected_rules=[],
        )

        self.assertIn(
            "English",
            prompt_data["user_prompt"],
        )

        self.assertIn(
            "greeting",
            prompt_data["system_prompt"].lower(),
        )

    def test_greeting_extract_output_accepts_valid_text(self):
        generator = get_generator("greeting")

        title, body = generator.extract_output(
            "Hello, hope you're having a great day!",
            "Greeting Test",
        )

        self.assertEqual(
            title,
            "Greeting Test",
        )

        self.assertEqual(
            body,
            "Hello, hope you're having a great day!",
        )

    @patch(
        "contents.core_services.generation.job_service.generate_content"
    )
    def test_full_greeting_generation_job_completes(
        self,
        mock_generate_content,
    ):
        mock_generate_content.return_value = (
            "Hello, hope you're doing well today!"
        )

        from contents.services import run_generation_job

        run_generation_job(
            self.job.pk
        )

        self.job.refresh_from_db()

        self.assertEqual(
            self.job.status,
            "completed",
        )

        self.assertEqual(
            self.job.generated_count,
            1,
        )

        content = Content.objects.get(
            content_type="greeting",
            language=self.language,
        )

        self.assertEqual(
            content.content_type,
            "greeting",
        )

        self.assertEqual(
            content.language,
            self.language,
        )

        self.assertIsNone(
            content.topic
        )

        self.assertIsNone(
            content.audience
        )

        self.assertIsNone(
            content.goal
        )

        self.assertIsNone(
            content.prompt_template
        )
