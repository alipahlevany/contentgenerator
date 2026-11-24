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
