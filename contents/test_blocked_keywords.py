from unittest.mock import patch

from django.test import SimpleTestCase

from contents.core_services.pipeline.blocked_keywords import (
    contains_blocked_keyword,
    remove_blocked_keywords,
)


@patch(
    'contents.core_services.pipeline.blocked_keywords.get_blocked_keywords',
    return_value=['scam', 'meth', 'porn', 'isis', 'sex', 'c++'],
)
class BlockedKeywordTests(SimpleTestCase):
    def test_normal_words_are_not_matched_or_damaged(self, _keywords):
        text = 'Something thoughtful from Sussex: uno scambio, odporny, crisis.'
        self.assertEqual(contains_blocked_keyword(text), (False, None))
        self.assertEqual(remove_blocked_keywords(text), text)

    def test_whole_keywords_are_still_blocked_next_to_punctuation(self, _keywords):
        for text in ['SCAM!', '(meth)', 'sex,', 'porn\n', 'isis?', 'c++.']:
            with self.subTest(text=text):
                self.assertTrue(contains_blocked_keyword(text)[0])
                cleaned = remove_blocked_keywords(text)
                self.assertEqual(contains_blocked_keyword(cleaned), (False, None))
                self.assertNotIn('\\1', cleaned)

    def test_unicode_letters_are_word_boundaries_not_ascii_only(self, _keywords):
        text = 'émeth methé ژmeth methژ'
        self.assertEqual(contains_blocked_keyword(text), (False, None))
        self.assertEqual(remove_blocked_keywords(text), text)

    def test_cleanup_preserves_letters_and_newlines(self, _keywords):
        self.assertEqual(
            remove_blocked_keywords('Start scam , letter\t\ttext ( meth )!\n\n\nNext.'),
            'Start, letter text ()!\n\nNext.',
        )

    def test_empty_keywords_are_ignored(self, keywords):
        keywords.return_value = ['', '  ']
        self.assertEqual(contains_blocked_keyword('Hello'), (False, None))
        self.assertEqual(remove_blocked_keywords('Hello'), 'Hello')
