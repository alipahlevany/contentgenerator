from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from contents.openai_usage import get_openai_usage


NOW = datetime(2026, 11, 1, 22, 30, tzinfo=timezone.utc)
TODAY = NOW.replace(hour=0, minute=0)
ISOLATED_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def bucket(day=TODAY, input_tokens=1000, output_tokens=200, cached=400):
    return {"object": "bucket", "start_time": int(day.timestamp()),
            "end_time": int((day + timedelta(days=1)).timestamp()), "results": [{
                "object": "organization.usage.completions.result", "input_tokens": input_tokens,
                "output_tokens": output_tokens, "input_cached_tokens": cached, "num_model_requests": 5,
            }]}


def page(*buckets, more=False, cursor=None):
    return {"object": "page", "data": list(buckets), "has_more": more, "next_page": cursor}


@override_settings(CACHES=ISOLATED_CACHE, OPENAI_ADMIN_KEY="test-admin-credential", OPENAI_USAGE_PROJECT_IDS=())
class OpenAIUsageTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.now = patch("contents.openai_usage.timezone.now", return_value=NOW)
        self.now.start()
        self.addCleanup(self.now.stop)
        self.requests = []
        self.responses = [httpx.Response(200, json=page(bucket()))]
        real_client = httpx.Client

        def respond(request):
            self.requests.append(request)
            result = self.responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        self.client = patch("contents.openai_usage.httpx.Client", side_effect=lambda **kwargs:
                            real_client(transport=httpx.MockTransport(respond), **kwargs))
        self.client.start()
        self.addCleanup(self.client.stop)

    @override_settings(OPENAI_ADMIN_KEY="", OPENAI_API_KEY="ordinary-generation-key")
    def test_missing_admin_key_never_uses_generation_key_or_returns_zero(self):
        result = get_openai_usage()
        self.assertEqual(result["status"], "not_configured")
        self.assertIsNone(result["totals"])
        self.assertFalse(self.requests)

    @override_settings(TIME_ZONE="Asia/Tehran")
    def test_official_total_uses_utc_and_counts_cache_once(self):
        result = get_openai_usage()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["totals"], {"input": 1000, "output": 200, "cached": 400, "tokens": 1200, "requests": 5})
        self.assertEqual(result["today_tokens"], 1200)
        self.assertEqual(result["end_date"], "2026-11-01")  # Already Nov 2 in Tehran.
        request = self.requests[0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.url.host, "api.openai.com")
        self.assertEqual(request.url.path, "/v1/organization/usage/completions")
        self.assertEqual(request.headers["authorization"], "Bearer test-admin-credential")
        self.assertEqual(int(request.url.params["start_time"]), int((TODAY-timedelta(days=6)).timestamp()))
        self.assertEqual(int(request.url.params["end_time"]), int(NOW.timestamp()))
        self.assertNotIn("test-admin-credential", str(result))

    def test_all_pages_and_days_are_aggregated_before_publishing(self):
        self.responses = [httpx.Response(200, json=page(bucket(TODAY-timedelta(days=1)), more=True, cursor="next")),
                          httpx.Response(200, json=page(bucket()))]
        result = get_openai_usage()
        self.assertEqual(result["totals"]["tokens"], 2400)
        self.assertEqual(result["today_tokens"], 1200)
        self.assertEqual(self.requests[1].url.params["page"], "next")

    def test_later_page_failure_does_not_publish_partial_total(self):
        self.responses = [httpx.Response(200, json=page(bucket(), more=True, cursor="next")),
                          httpx.Response(500)]
        self.assertIsNone(get_openai_usage()["totals"])

    def test_repeated_cursor_or_bucket_is_not_double_counted(self):
        self.responses = [httpx.Response(200, json=page(bucket(), more=True, cursor="next")),
                          httpx.Response(200, json=page(bucket(), more=True, cursor="next"))]
        self.assertEqual(get_openai_usage()["status"], "unavailable")
        self.assertEqual(len(self.requests), 2)

    def test_empty_successful_response_is_a_real_reported_zero(self):
        self.responses = [httpx.Response(200, json=page())]
        result = get_openai_usage()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["totals"]["tokens"], 0)

    def test_invalid_and_incomplete_payloads_never_look_like_zero(self):
        invalid_bucket = bucket()
        invalid_bucket["results"][0]["input_tokens"] = -1
        for payload in ({}, [], {"data": [], "has_more": True}, page(invalid_bucket),
                        page(bucket(TODAY+timedelta(days=1)))):
            with self.subTest(payload=payload):
                cache.clear()
                self.responses = [httpx.Response(200, json=payload)]
                self.assertIsNone(get_openai_usage()["totals"])

    def test_errors_are_safe_cached_and_do_not_retry_inside_request(self):
        for code, expected in ((401, "access_denied"), (403, "access_denied"), (429, "rate_limited"),
                               (500, "unavailable"), (302, "unavailable")):
            with self.subTest(code=code):
                cache.clear()
                self.responses = [httpx.Response(code, text="private provider error", headers={"Location": "https://example.com"})]
                count = len(self.requests)
                result = get_openai_usage()
                self.assertEqual(result["status"], expected)
                self.assertEqual(get_openai_usage(), result)
                self.assertEqual(len(self.requests), count+1)
                self.assertNotIn("private provider error", str(result))

    def test_timeout_is_safe_and_does_not_return_fabricated_total(self):
        self.responses = [httpx.ReadTimeout("private request detail")]
        result = get_openai_usage()
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["totals"])
        self.assertNotIn("private request detail", str(result))

    def test_pagination_and_time_budget_are_bounded(self):
        self.responses = [httpx.Response(200, json=page(more=True, cursor=f"next-{i}")) for i in range(8)]
        self.assertIsNone(get_openai_usage()["totals"])
        self.assertEqual(len(self.requests), 8)
        cache.clear()
        with patch("contents.openai_usage.time.monotonic", side_effect=[0, 10]):
            self.assertEqual(get_openai_usage()["status"], "unavailable")
        self.assertEqual(len(self.requests), 8)

    def test_invalid_json_does_not_break_the_dashboard_endpoint(self):
        self.responses = [httpx.Response(200, text="not JSON")]
        self.assertEqual(get_openai_usage()["status"], "unavailable")

    def test_cache_avoids_repeated_network_calls(self):
        first = get_openai_usage()
        self.assertEqual(get_openai_usage(), first)
        self.assertEqual(len(self.requests), 1)

    def test_cache_is_partitioned_by_period_scope_key_and_utc_date(self):
        get_openai_usage()
        for changes, days in (({}, 30), ({"OPENAI_USAGE_PROJECT_IDS": ("proj_one", "proj_two")}, 7),
                              ({"OPENAI_ADMIN_KEY": "rotated-key"}, 7)):
            self.responses = [httpx.Response(200, json=page())]
            with self.settings(**changes):
                result = get_openai_usage(days)
                self.assertEqual(result["totals"]["tokens"], 0)
        self.assertEqual(self.requests[2].url.params.get_list("project_ids[]"), ["proj_one", "proj_two"])
        self.responses = [httpx.Response(200, json=page())]
        with patch("contents.openai_usage.timezone.now", return_value=NOW+timedelta(days=1)):
            self.assertEqual(get_openai_usage()["totals"]["tokens"], 0)
        self.assertEqual(len(self.requests), 5)

    def _expire_fresh_copy(self):
        original_get = cache.get
        return patch.object(cache, "get", side_effect=lambda key, *args, **kwargs:
                            original_get(key, *args, **kwargs) if key.endswith(":last") else None)

    def test_failure_keeps_last_success_marked_stale_with_original_timestamp(self):
        first = get_openai_usage()
        self.responses = [httpx.Response(503)]
        with self._expire_fresh_copy():
            result = get_openai_usage()
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["totals"], first["totals"])
        self.assertEqual(result["fetched_at"], first["fetched_at"])

    def test_auth_failure_discards_previous_success(self):
        get_openai_usage()
        self.responses = [httpx.Response(401)]
        with self._expire_fresh_copy():
            result = get_openai_usage()
        self.assertEqual(result["status"], "access_denied")
        self.assertIsNone(result["totals"])

    def test_concurrent_refresh_does_not_issue_another_provider_request(self):
        with patch.object(cache, "add", return_value=False):
            self.assertEqual(get_openai_usage()["status"], "loading")
        self.assertFalse(self.requests)

    def test_invalid_period_is_normalized(self):
        self.assertEqual(get_openai_usage("unlimited")["period_days"], 7)


@override_settings(CACHES=ISOLATED_CACHE, SECURE_SSL_REDIRECT=False, OPENAI_ADMIN_KEY="")
class OpenAIUsageAccessTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="usage-admin", is_staff=True)
        self.url = "/dashboard/openai-usage/"

    def test_account_usage_is_only_exposed_to_active_superusers(self):
        with patch("contents.openai_usage._fetch_usage") as fetch:
            self.assertEqual(self.client.get(self.url).status_code, 302)
            self.client.force_login(self.user)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertNotContains(self.client.get("/admin/"), 'id="account-usage"')
            self.user.is_superuser = True
            self.user.save(update_fields=["is_superuser"])
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "not_configured")
            self.assertEqual(response["Cache-Control"], "private, no-store")
            self.assertEqual(self.client.post(self.url).status_code, 405)
            self.assertContains(self.client.get("/admin/"), 'id="account-usage"')
            self.user.is_active = False
            self.user.save(update_fields=["is_active"])
            self.assertEqual(self.client.get(self.url).status_code, 302)
            fetch.assert_not_called()

    @override_settings(OPENAI_ADMIN_KEY="sensitive-admin-key")
    def test_dashboard_html_does_not_fetch_provider_or_render_credential(self):
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        self.client.force_login(self.user)
        with patch("contents.openai_usage._fetch_usage") as fetch:
            response = self.client.get("/admin/")
            fetch.assert_not_called()
        self.assertContains(response, "OpenAI Usage")
        self.assertNotContains(response, "sensitive-admin-key")
