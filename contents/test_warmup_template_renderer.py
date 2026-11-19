"""Focused checks for the email format and its external-asset boundary."""

from datetime import date, timedelta
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings
from django.core.cache import cache

from contents.core_services.warmup_template_renderer import (
    WarmupTemplateError,
    LAYOUT_NAMES,
    render_warmup_html,
    validate_warmup_html,
    DEFAULT_LINK_URL,
    validate_destination_url,
)
from contents.core_services.warmup_templates import (
    _get_remote_photo,
    _recent_photo_ids,
    _get_picsum_photo,
    _picsum_page,
    photo_source_status,
)


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class WarmupTemplateRendererTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    photo = {
        "image_url": "https://images.pexels.com/photos/123/photo-123.jpeg",
        "photo_page": "https://www.pexels.com/photo/example-123/",
        "photographer": "Example Photographer",
        "alt": "A quiet reading corner",
    }
    def test_all_layouts_keep_email_placeholders_and_one_remote_photo(self):
        first_day = date(2026, 11, 16)
        for offset in range(len(LAYOUT_NAMES)):
            with self.subTest(layout=offset):
                day = first_day + timedelta(days=offset)
                markup = render_warmup_html(self.photo, day, 0)
                self.assertEqual(validate_warmup_html(markup, self.photo), markup)
                self.assertEqual(markup.count("{{content}}"), 1)
                self.assertIn('line-height:1.85;text-align:center;', markup)
                self.assertEqual(markup.count("{{unsubscribe}}"), 1)
                self.assertEqual(markup.count("<img "), 1)
                self.assertNotIn(self.photo["photo_page"], markup)
                self.assertIn("Photo by Example Photographer on Pexels", markup)
                self.assertEqual(markup.count("<a "), 2)
                self.assertEqual(markup.count(DEFAULT_LINK_URL), 2)
                self.assertNotIn('href="{{unsubscribe}}"', markup)
                self.assertLess(len(markup.encode("utf-8")), 10_000)
                self.assertNotIn("<h1", markup)
                self.assertNotIn("THE DAILY NOTE", markup)

    def test_melal_slots_and_article_links_are_preserved(self):
        destination = "https://example.com/articles/daily-note?one=1&two=2"
        markup = render_warmup_html(self.photo, date(2026, 11, 17), 0, destination)
        validate_warmup_html(markup, self.photo, destination_url=destination)
        for invalid in (
            markup.replace("{{unsubscribe}}", '<a href="{{unsubscribe}}">Unsubscribe</a>'),
            markup.replace("{{content}}", '<!--{{content}}-->'),
            markup.replace("https://example.com/articles/daily-note", "https://example.com/wrong", 1),
        ):
            with self.assertRaises(WarmupTemplateError):
                validate_warmup_html(invalid, self.photo, destination_url=destination)
        for url in ("javascript:alert(1)", "http://example.com/", "https://user:pass@example.com/", "https://c.mailerever.net/track/example"):
            with self.assertRaises(WarmupTemplateError):
                validate_destination_url(url)

    @patch("contents.core_services.warmup_templates.Content.objects.filter")
    @patch("contents.core_services.warmup_templates.cache.get", return_value={"pexels:123": 1, "pexels:456": 2, "picsum:8": 3})
    def test_recent_photo_ids_use_short_cache(self, _get, filter_query):
        self.assertEqual(_recent_photo_ids(), {"123", "456"})
        filter_query.assert_not_called()

    def test_photo_metadata_is_escaped_and_unapproved_links_are_rejected(self):
        photo = {**self.photo, "photographer": "A <B>", "alt": 'A "quiet" view'}
        markup = render_warmup_html(photo, date(2026, 11, 16), 0)
        self.assertIn("A &lt;B&gt;", markup)
        self.assertIn("A &quot;quiet&quot; view", markup)
        validate_warmup_html(markup, photo)
        with self.assertRaises(WarmupTemplateError):
            validate_warmup_html(markup.replace("{{unsubscribe}}", '<a href="https://example.com/">Credit</a>{{unsubscribe}}'))
        with self.assertRaises(WarmupTemplateError):
            validate_warmup_html(markup.replace("{{content}}", "missing"))

    @override_settings(PEXELS_API_KEY="test-key")
    @patch("contents.core_services.warmup_templates._recent_photo_ids", return_value={"123"})
    @patch("contents.core_services.warmup_templates.cache.add", return_value=True)
    @patch("contents.core_services.warmup_templates.requests.get")
    def test_recent_photo_is_skipped_without_downloading_images(self, get, _reserve, _recent):
        def photo(photo_id):
            return {
                "id": photo_id,
                "src": {"large": f"https://images.pexels.com/photos/{photo_id}/photo.jpeg"},
                "url": f"https://www.pexels.com/photo/example-{photo_id}/",
                "photographer": "Example",
                "alt": "Example image",
            }

        get.side_effect = [
            Mock(status_code=200, json=Mock(return_value={"photos": [photo(123)]})),
            Mock(status_code=200, json=Mock(return_value={"photos": [photo(456)]})),
        ]
        selected = _get_remote_photo(0, date(2026, 11, 16))
        self.assertEqual(selected["id"], "456")
        self.assertEqual(get.call_count, 2)
        _reserve.assert_called_once_with("warmup-photo-reservation:pexels:456", 1, timeout=3600)
        self.assertTrue(all(call.args[0] == "https://api.pexels.com/v1/search" for call in get.call_args_list))

    @override_settings(PEXELS_API_KEY="test-key")
    @patch("contents.core_services.warmup_templates._recent_photo_ids", return_value=set())
    @patch("contents.core_services.warmup_templates.cache.add", return_value=True)
    @patch("contents.core_services.warmup_templates.requests.get")
    def test_invalid_photo_url_is_skipped_before_reservation(self, get, reserve, _recent):
        get.return_value.status_code = 200
        get.return_value.json.return_value = {"photos": [
            {
                "id": 100,
                "src": {"large": "https://untrusted.example/photo.jpeg"},
                "url": "https://www.pexels.com/photo/example-100/",
            },
            {
                "id": 200,
                "src": {"large": "https://images.pexels.com/photos/200/photo.jpeg"},
                "url": "https://www.pexels.com/photo/example-200/",
            },
        ]}
        selected = _get_remote_photo(0, date(2026, 11, 16))
        self.assertEqual(selected["id"], "200")
        reserve.assert_called_once_with("warmup-photo-reservation:pexels:200", 1, timeout=3600)


@override_settings(
    WARMUP_TEMPLATE_PHOTO_PROVIDER="auto", PEXELS_API_KEY="",
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class PicsumPhotoTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def item(self, photo_id):
        return {"id": str(photo_id), "author": "Example Photographer", "width": 3000,
                "height": 2000, "url": f"https://unsplash.com/photos/example-{photo_id}"}

    def test_auto_source_works_without_a_photo_key(self):
        self.assertEqual(photo_source_status()["provider"], "picsum")
        self.assertTrue(photo_source_status()["ready"])
        with self.settings(PEXELS_API_KEY="test-key"):
            self.assertEqual(photo_source_status()["provider"], "pexels")
        with self.settings(WARMUP_TEMPLATE_PHOTO_PROVIDER="pexels"):
            self.assertFalse(photo_source_status()["ready"])
        with self.settings(WARMUP_TEMPLATE_PHOTO_PROVIDER="unknown"):
            self.assertFalse(photo_source_status()["ready"])

    @patch("contents.core_services.warmup_templates.requests.get")
    def test_only_metadata_is_downloaded_and_cached(self, get):
        get.return_value.json.return_value = [self.item(0)]
        self.assertEqual(_picsum_page(1), _picsum_page(1))
        get.assert_called_once()
        self.assertEqual(get.call_args.args[0], "https://picsum.photos/v2/list")

    @patch("contents.core_services.warmup_templates._recent_photo_usage", return_value={})
    @patch("contents.core_services.warmup_templates._picsum_page")
    def test_photo_zero_is_valid_and_all_layouts_accept_picsum(self, page, _history):
        page.return_value = [self.item(0)]
        photo = _get_picsum_photo(0, date(2026, 11, 17))
        self.assertEqual(photo["id"], "0")
        for sequence in range(4):
            markup = render_warmup_html(photo, date(2026, 11, 17), sequence)
            self.assertEqual(validate_warmup_html(markup, photo), markup)
            self.assertIn("Unsplash via Picsum", markup)
            with self.assertRaises(WarmupTemplateError):
                validate_warmup_html(markup.replace(photo["image_url"], "https://picsum.photos/1200/800"))
            with self.assertRaises(WarmupTemplateError):
                validate_warmup_html(markup.replace("{{unsubscribe}}", '<a href="https://www.pexels.com/photo/1/">Credit</a>{{unsubscribe}}'))

    @patch("contents.core_services.warmup_templates._recent_photo_usage", return_value={})
    @patch("contents.core_services.warmup_templates._picsum_page")
    def test_reserved_photo_and_invalid_destinations_are_skipped(self, page, _history):
        cache.add("warmup-photo-reservation:picsum:10", 1, timeout=3600)
        page.return_value = [self.item(10), {**self.item(11), "url": "https://untrusted.example/"}, self.item(12)]
        self.assertEqual(_get_picsum_photo(0, date(2026, 11, 17))["id"], "12")

    @patch("contents.core_services.warmup_templates._recent_photo_usage")
    @patch("contents.core_services.warmup_templates._picsum_page")
    def test_exhausted_catalog_reuses_oldest_but_never_today(self, page, history):
        from django.utils import timezone
        now = timezone.now().timestamp()
        history.return_value = {"picsum:10": now - 2 * 86400, "picsum:11": now - 3 * 86400, "picsum:12": now}
        page.return_value = [self.item(10), self.item(11), self.item(12)]
        self.assertEqual(_get_picsum_photo(0, date(2026, 11, 17))["id"], "11")
        history.return_value = {"picsum:12": now}
        page.return_value = [self.item(12)]
        with self.assertRaises(WarmupTemplateError):
            _get_picsum_photo(1, date(2026, 11, 17))
