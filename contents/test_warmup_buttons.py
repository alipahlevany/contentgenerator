"""Exercise the catalogue, transactional rotation, retries, and concurrent workers."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from html.parser import HTMLParser
from threading import Barrier
from unittest.mock import patch

from django.core.cache import cache
from django.db import OperationalError, close_old_connections
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings

from contents.admin.warmup_template import SAMPLE_PHOTO
from contents.core_services.warmup_buttons import BUTTON_BANK_VERSION, BUTTON_LABELS
from contents.core_services.warmup_articles import choose_article
from contents.core_services.warmup_template_renderer import render_warmup_html, validate_warmup_html
from contents.core_services.warmup_templates import generate_warmup_template
from contents.models import Content, WarmupButtonRotation

DAY = date(2026, 11, 18)
PHOTO = {**SAMPLE_PHOTO, "id": "1018", "provider": "picsum"}
LOCAL_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


class ButtonCatalogueTests(SimpleTestCase):
    def test_all_thousand_are_distinct_readable_and_render_as_plain_text(self):
        self.assertEqual(len(BUTTON_LABELS), 1000)
        self.assertEqual(len({label.casefold() for label in BUTTON_LABELS}), 1000)
        for index, label in enumerate(BUTTON_LABELS):
            with self.subTest(index=index):
                self.assertTrue(label.isascii())
                self.assertLessEqual(len(label), 64)
                self.assertEqual(label, label.strip())
                self.assertNotRegex(label, r"[\d<>\n{}]")
                markup = render_warmup_html(PHOTO, DAY, index, button_label=label)
                validate_warmup_html(markup, PHOTO)
                self.assertEqual(markup.count("<a "), 2)
                self.assertNotIn(PHOTO["photo_page"], markup)
                self.assertIn("Photo by", markup)
                self.assertEqual(markup.count("{{content}}"), 1)

    def test_existing_saved_template_with_credit_link_remains_readable(self):
        markup = render_warmup_html(PHOTO, DAY, 0)
        credit = f'Photo by {PHOTO["photographer"]} on {PHOTO["credit_source"]}'
        legacy = markup.replace(credit, f'<a href="{PHOTO["photo_page"]}">{credit}</a>')
        self.assertEqual(validate_warmup_html(legacy), legacy)


@override_settings(CACHES=LOCAL_CACHE)
class ButtonRotationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.photo_patch = patch("contents.core_services.warmup_templates._get_remote_photo", return_value=PHOTO)
        self.photo_patch.start()
        self.addCleanup(self.photo_patch.stop)
        article_patch = patch("contents.core_services.warmup_templates.choose_article", return_value="https://medium.com/test/story-123")
        article_patch.start()
        self.addCleanup(article_patch.stop)

    def test_full_cycle_survives_cache_reset_and_changes_of_batch(self):
        ids = []
        with patch("contents.core_services.ai.client.responses.create") as ai:
            for index in range(1001):
                if index == 497:
                    cache.clear()
                content = generate_warmup_template(DAY, index % 100, f"cycle-{index // 100}")
                ids.append(content.prompt.split("Button label: ")[1].split(".")[0])
            ai.assert_not_called()
        self.assertEqual(len(set(ids[:1000])), 1000)
        self.assertEqual(ids[0], ids[1000])
        self.assertEqual(WarmupButtonRotation.objects.get().next_position, 1001)

    def test_retry_and_duplicate_slot_do_not_consume_a_label(self):
        WarmupButtonRotation.objects.create(bank_version=BUTTON_BANK_VERSION, next_position=42)
        with patch("contents.core_services.warmup_templates.Content.objects.create", side_effect=OperationalError("test save failure")):
            with self.assertRaises(OperationalError):
                generate_warmup_template(DAY, 0, "retry-button")
        self.assertEqual(WarmupButtonRotation.objects.get().next_position, 42)
        saved = generate_warmup_template(DAY, 0, "retry-button")
        cache.clear()
        repeated = generate_warmup_template(DAY, 0, "retry-button")
        self.assertEqual(saved.pk, repeated.pk)
        self.assertIn("english-v1:0042", saved.prompt)
        self.assertEqual(WarmupButtonRotation.objects.get().next_position, 43)

    def test_new_templates_save_different_article_links(self):
        urls = ["https://medium.com/test/story-a", "https://medium.com/test/story-b"]
        with patch("contents.core_services.warmup_templates.choose_article", wraps=choose_article), patch("contents.core_services.warmup_articles._feed_stories", return_value=urls), self.settings(WARMUP_TEMPLATE_ARTICLE_TOPICS=("technology",)):
            first = generate_warmup_template(DAY, 0, "article-links")
            second = generate_warmup_template(DAY, 1, "article-links")
        links = [next(url for url in urls if url in item.generated_content) for item in (first, second)]
        self.assertNotEqual(*links)
        for item, url in zip((first, second), links):
            self.assertEqual(item.generated_content.count(url), 2)
            self.assertIn(f"Article URL: {url}\n", item.prompt)


@override_settings(CACHES=LOCAL_CACHE)
class ConcurrentButtonRotationTests(TransactionTestCase):
    def test_two_workers_create_distinct_labels_even_when_cursor_is_new(self):
        cache.clear()
        self.addCleanup(cache.clear)
        barrier = Barrier(2)

        def photo(*args):
            barrier.wait(timeout=10)
            return PHOTO

        def generate(index):
            close_old_connections()
            try:
                return generate_warmup_template(DAY, index, "parallel-buttons").prompt
            finally:
                close_old_connections()

        with patch("contents.core_services.warmup_templates.choose_article", return_value="https://medium.com/test/story-123"), patch("contents.core_services.warmup_templates._get_remote_photo", side_effect=photo):
            with ThreadPoolExecutor(max_workers=2) as pool:
                prompts = list(pool.map(generate, (0, 1)))
        self.assertEqual(len(set(prompts)), 2)
        self.assertEqual(Content.objects.filter(content_type="warmup_template").count(), 2)
        self.assertEqual(WarmupButtonRotation.objects.get().next_position, 2)
