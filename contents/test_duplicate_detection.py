from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from contents.core_services.duplicate import (
    is_duplicate_content,
    make_content_hash,
)


class DuplicateDetectionTests(SimpleTestCase):
    def duplicate_query(self, objects_all, *, exists):
        scoped_query = MagicMock()
        hash_query = MagicMock()
        hash_query.exists.return_value = exists
        scoped_query.filter.return_value = hash_query
        objects_all.return_value.filter.return_value = scoped_query

        return scoped_query, hash_query

    @patch("contents.core_services.duplicate.Content.objects.all")
    def test_same_title_with_different_body_is_not_duplicate(
        self,
        objects_all,
    ):
        scoped_query, hash_query = self.duplicate_query(
            objects_all,
            exists=False,
        )

        duplicate, reason, content_hash = is_duplicate_content(
            "Warm Email Greeting",
            "A completely different and useful greeting.",
            content_type="greeting",
        )

        self.assertFalse(duplicate)
        self.assertIsNone(reason)
        objects_all.return_value.filter.assert_called_once_with(
            content_type="greeting"
        )
        hash_query.exists.assert_called_once_with()
        scoped_query.filter.assert_called_once_with(
            content_hash=content_hash
        )

    @patch("contents.core_services.duplicate.Content.objects.all")
    def test_same_normalized_body_in_same_type_is_duplicate(
        self,
        objects_all,
    ):
        self.duplicate_query(objects_all, exists=True)
        body = "  A genuinely USEFUL piece of   content.  "

        duplicate, reason, content_hash = is_duplicate_content(
            "Another title",
            body,
            content_type="standard",
        )

        self.assertTrue(duplicate)
        self.assertEqual(reason, "duplicate content")
        self.assertEqual(content_hash, make_content_hash(body))

    @patch("contents.core_services.duplicate.Content.objects.all")
    def test_duplicate_lookup_is_scoped_to_requested_content_type(
        self,
        objects_all,
    ):
        self.duplicate_query(objects_all, exists=False)

        duplicate, reason, _ = is_duplicate_content(
            "Email Reply",
            "Shared wording for separate content products.",
            content_type="email_reply",
        )

        self.assertFalse(duplicate)
        self.assertIsNone(reason)
        objects_all.return_value.filter.assert_called_once_with(
            content_type="email_reply"
        )
