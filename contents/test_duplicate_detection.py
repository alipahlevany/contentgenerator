from django.test import TestCase

from contents.core_services.duplicate import is_duplicate_content
from contents.models import Content


class DuplicateDetectionTests(TestCase):
    def create_content(self, *, title, body, content_type="standard"):
        duplicate, _, content_hash = is_duplicate_content(
            title,
            body,
            content_type=content_type,
        )
        self.assertFalse(duplicate)

        return Content.objects.create(
            title=title,
            content_type=content_type,
            prompt="Prompt",
            generated_content=body,
            content_hash=content_hash,
            status="generated",
        )

    def test_same_title_with_different_body_is_not_duplicate(self):
        self.create_content(
            title="Warm Email Greeting",
            body="A warm and useful first greeting.",
            content_type="greeting",
        )

        duplicate, reason, _ = is_duplicate_content(
            "Warm Email Greeting",
            "A completely different and useful second greeting.",
            content_type="greeting",
        )

        self.assertFalse(duplicate)
        self.assertIsNone(reason)

    def test_same_normalized_body_in_same_type_is_duplicate(self):
        self.create_content(
            title="First title",
            body="A genuinely useful piece of content.",
        )

        duplicate, reason, _ = is_duplicate_content(
            "Another title",
            "  A genuinely USEFUL piece of   content.  ",
            content_type="standard",
        )

        self.assertTrue(duplicate)
        self.assertEqual(reason, "duplicate content")

    def test_identical_body_in_different_types_is_not_duplicate(self):
        self.create_content(
            title="Standard title",
            body="Shared wording for separate content products.",
            content_type="standard",
        )

        duplicate, reason, _ = is_duplicate_content(
            "Email Reply",
            "Shared wording for separate content products.",
            content_type="email_reply",
        )

        self.assertFalse(duplicate)
        self.assertIsNone(reason)
