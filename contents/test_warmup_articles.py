"""Validate Medium RSS selection and recent-link rotation."""

from datetime import date
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from contents.core_services.warmup_articles import _feed_stories, choose_article
from contents.core_services.warmup_template_renderer import WarmupTemplateError


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}, WARMUP_TEMPLATE_ARTICLE_TOPICS=("technology",))
class MediumArticleTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    @patch("contents.core_services.warmup_articles.requests.get")
    def test_feed_accepts_only_medium_story_urls_and_caches_metadata(self, get):
        get.return_value = Mock(content=b"<rss><channel><item><link>https://medium.com/author/story-a?source=rss</link></item><item><link>https://evil.example/story</link></item><item><link>https://medium.com/author/story-a</link></item><item><link>https://medium.com/author/story-b</link></item></channel></rss>")
        self.assertEqual(_feed_stories("technology"), ["https://medium.com/author/story-a", "https://medium.com/author/story-b"])
        self.assertEqual(_feed_stories("technology"), _feed_stories("technology"))
        get.assert_called_once()

    @patch("contents.core_services.warmup_articles._recent_usage", return_value={})
    @patch("contents.core_services.warmup_articles._feed_stories", return_value=["https://medium.com/author/story-a", "https://medium.com/author/story-b"])
    def test_parallel_slots_reserve_distinct_stories(self, _feed, _usage):
        first = choose_article(date(2026, 11, 19), 0)
        second = choose_article(date(2026, 11, 19), 1)
        self.assertNotEqual(first, second)
        with self.assertRaises(WarmupTemplateError):
            choose_article(date(2026, 11, 19), 2)

    @patch("contents.core_services.warmup_articles._recent_usage", return_value={"https://medium.com/author/story-a": 9e12})
    @patch("contents.core_services.warmup_articles._feed_stories", return_value=["https://medium.com/author/story-a", "https://medium.com/author/story-b"])
    def test_older_story_is_reused_only_when_needed(self, _feed, _usage):
        self.assertEqual(choose_article(date(2026, 11, 19), 0), "https://medium.com/author/story-b")
