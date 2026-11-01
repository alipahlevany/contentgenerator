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

        self.assertIn(
            "Aim for 20 to 26 words",
            prompt_data["system_prompt"],
        )

        self.assertIn(
            "Avoid tired formulas",
            prompt_data["system_prompt"],
        )
        self.assertEqual(
            prompt_data["fallback_title"],
            "Greeting",
        )

    def test_greeting_prompt_varies_creative_direction(self):
        generator = get_generator("greeting")

        first = generator.build_prompt_data(
            app_settings=None,
            language=self.language,
            topic=None,
            audience=None,
            goal=None,
            prompt_template=None,
            selected_rules=[],
            variation_key=1,
        )
        second = generator.build_prompt_data(
            app_settings=None,
            language=self.language,
            topic=None,
            audience=None,
            goal=None,
            prompt_template=None,
            selected_rules=[],
            variation_key=2,
        )

        self.assertNotEqual(
            first["user_prompt"],
            second["user_prompt"],
        )

    def test_same_tone_varies_meaning_and_sentence_structure(self):
        generator = get_generator("greeting")
        # Previously every sixth seed selected the same vague direction.
        keys = [0, 6, 6 * len(generator.THEMES)]
        prompts = []
        for key in keys:
            prompts.append(generator.build_prompt_data(
                app_settings=None, language=self.language, topic=None,
                audience=None, goal=None, prompt_template=None,
                selected_rules=[], variation_key=key,
            )["user_prompt"])
        directions = [generator.writing_direction(key) for key in keys]
        self.assertNotEqual(directions[0][0], directions[1][0])
        self.assertNotEqual(directions[0][1], directions[2][1])
        for prompt, (theme, structure) in zip(prompts, directions):
            self.assertIn(theme, prompt)
            self.assertIn(structure, prompt)

    @patch("contents.core_services.generation.job_service.generate_content")
    def test_duplicate_greeting_stays_rejected_and_informs_retry(self, generate):
        from contents.services import run_generation_job
        duplicate = (
            "It is good to connect with you, and I welcome the chance "
            "to share a few thoughts in this message."
        )
        fresh = (
            "A warm hello as we begin this exchange; may these few lines "
            "offer a thoughtful and welcoming place to start."
        )
        self.job.count = 2
        self.job.save(update_fields=["count"])
        generate.side_effect = [duplicate, duplicate, fresh]
        run_generation_job(self.job.pk)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "completed")
        self.assertEqual(self.job.generated_count, 2)
        self.assertEqual(self.job.duplicate_count, 1)
        self.assertEqual(self.job.attempted_count, 3)
        self.assertEqual(Content.objects.filter(generation_job=self.job).count(), 2)
        retry_prompt = generate.call_args_list[2].kwargs["user_prompt"]
        self.assertIn(duplicate, retry_prompt)
        self.assertIn("English", retry_prompt)

    def test_greeting_extract_output_cleans_safe_wrappers(self):
        generator = get_generator("greeting")

        title, body = generator.extract_output(
            'Greeting: "It is genuinely good to connect with you; '
            'wishing you a calm, productive moment as we begin our '
            'conversation today."',
            "Warm Greeting Test",
        )

        self.assertEqual(
            title,
            "It is genuinely good to connect with…",
        )
        self.assertEqual(
            body,
            (
                "It is genuinely good to connect with you; wishing you a "
                "calm, productive moment as we begin our conversation today."
            ),
        )

    def test_greeting_extract_output_accepts_valid_text(self):
        generator = get_generator("greeting")

        title, body = generator.extract_output(
            "Hello, I hope you're having a wonderful day and everything is going smoothly for you!",
            "Warm Greeting Test",
        )

        self.assertEqual(
            title,
            "Hello, I hope you're having a wonderful…",
        )

        self.assertEqual(
            body,
            "Hello, I hope you're having a wonderful day and everything is going smoothly for you!",
        )

    @patch(
        "contents.core_services.generation.job_service.generate_content"
    )
    def test_full_greeting_generation_job_completes(
        self,
        mock_generate_content,
    ):
        mock_generate_content.return_value = (
            "Hello, I hope you're doing well today and having a pleasant start to your week!"
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

        self.assertEqual(
            content.title,
            "Hello, I hope you're doing well today…",
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

    @patch(
        "contents.core_services.generation.job_service.generate_content"
    )
    def test_too_long_greeting_is_retried_without_failing_job(
        self,
        mock_generate_content,
    ):
        mock_generate_content.side_effect = [
            "word " * 51,
            "Hello, I hope you're doing well today and having a pleasant start to your week!",
        ]

        from contents.services import run_generation_job

        run_generation_job(self.job.pk)

        self.job.refresh_from_db()

        self.assertEqual(self.job.status, "completed")
        self.assertEqual(self.job.generated_count, 1)
        self.assertEqual(self.job.attempted_count, 2)
        self.assertEqual(self.job.failed_count, 1)
        self.assertTrue(
            self.job.logs.filter(message="Greeting output is too long.").exists()
        )

    def test_compact_languages_keep_complete_short_greetings(self):
        from contents.core_services.generators.base import GeneratorOutputError
        generator = get_generator("greeting")
        compact = "Merhaba, size içten selamlarımı iletiyor, işlerinizin yolunda gitmesini ve keyifli anlar yaşamanızı diliyorum."
        self.assertEqual(len(compact.split()), 13)
        turkish = Language(code="tr-TR", name="Turkish")
        _, body = generator.extract_output(compact, "Greeting", language=turkish)
        self.assertEqual(body, compact)
        with self.assertRaises(GeneratorOutputError):
            generator.extract_output(compact, "Greeting", language=self.language)
        with self.assertRaises(GeneratorOutputError):
            generator.extract_output("Merhaba, iyi dileklerimle.", "Greeting", language=turkish)
        with self.assertRaises(GeneratorOutputError):
            generator.extract_output("word " * 31, "Greeting", language=turkish)

    @patch("contents.core_services.generation.job_service.generate_content")
    def test_job_passes_selected_language_to_length_validation(self, generate):
        from contents.services import run_generation_job
        self.language.is_active = False
        self.language.save(update_fields=["is_active"])
        turkish = Language.objects.create(code="tr", name="Turkish", is_active=True)
        generate.return_value = "Merhaba, size içten selamlarımı iletiyor, işlerinizin yolunda gitmesini ve keyifli anlar yaşamanızı diliyorum."
        run_generation_job(self.job.pk)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "completed")
        self.assertEqual(self.job.generated_count, 1)
        self.assertEqual(self.job.skipped_count, 0)
        content = Content.objects.get(generation_job=self.job)
        self.assertEqual(content.language, turkish)
        self.assertEqual(content.generated_content, generate.return_value)
