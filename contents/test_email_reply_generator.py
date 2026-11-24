from django.test import SimpleTestCase

from contents.core_services.generators.base import GeneratorOutputError
from contents.core_services.generators.email_reply import EmailReplyGenerator


class EmailReplyGeneratorTests(SimpleTestCase):
    def test_valid_placeholder_is_preserved(self):
        title, body = EmailReplyGenerator().extract_output(
            "Hello [[first_name]], thank you for writing.", "Reply"
        )
        self.assertEqual(title, "Reply")
        self.assertIn("[[first_name]]", body)

    def test_malformed_placeholder_is_rejected(self):
        for body in ("Hello [[first_name", "Hello first_name]]", "Hello [[name]] and [[other"):
            with self.subTest(body=body), self.assertRaises(GeneratorOutputError):
                EmailReplyGenerator().extract_output(body, "Reply")

    def test_prompt_keeps_constraints_and_retry_guidance_separate(self):
        generator = EmailReplyGenerator()
        kwargs = dict(app_settings=None, language="English", topic=None,
                      audience=None, goal=None, prompt_template=None,
                      selected_rules=[], variation_key=123)
        initial = generator.build_prompt_data(**kwargs)
        retried = generator.build_prompt_data(
            **dict(kwargs, variation_key=456), retry_feedback="Use complete placeholders."
        )
        self.assertEqual(initial["system_prompt"], retried["system_prompt"])
        for token in generator.ALLOWED_PLACEHOLDERS:
            self.assertIn(token, initial["system_prompt"])
        self.assertIn("40-120 words", initial["system_prompt"])
        self.assertIn("50-70", initial["system_prompt"])
        self.assertIn("English", initial["user_prompt"])
        self.assertIn("456", retried["user_prompt"])
        self.assertIn("Use complete placeholders.", retried["user_prompt"])
        self.assertNotIn("Use complete placeholders.", initial["system_prompt"])

    def test_unknown_placeholder_is_rejected(self):
        with self.assertRaises(GeneratorOutputError):
            EmailReplyGenerator().extract_output("Hi [[customer_id]].", "Reply")
