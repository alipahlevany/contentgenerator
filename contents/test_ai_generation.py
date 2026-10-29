import importlib
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from django.apps import apps
from django.core.cache import cache
from django.db import connection
from django.test import SimpleTestCase, TestCase
from openai import APIConnectionError, APITimeoutError, AuthenticationError, InternalServerError, NotFoundError, RateLimitError

from contents.core_services.ai import PermanentGenerationError, TransientGenerationError, generate_content
from contents.core_services.cache import APP_SETTINGS_CACHE_KEY, get_app_settings
from contents.models import AppSettings


class AIGenerationTests(SimpleTestCase):
    def setUp(self):
        self.settings_patch = patch(
            "contents.core_services.ai.get_app_settings",
            return_value=SimpleNamespace(
                model_name="gpt-6-luna", max_output_tokens=1200, temperature=1.05,
            ),
        )
        self.app_settings = self.settings_patch.start().return_value
        self.addCleanup(self.settings_patch.stop)
        self.client_patch = patch("contents.core_services.ai.client")
        self.client = self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.client.responses.create.return_value = SimpleNamespace(
            status="completed", output_text="A complete generated response.",
        )
        self.sleep_patch = patch("contents.core_services.ai.sleep_before_retry")
        self.sleep = self.sleep_patch.start()
        self.addCleanup(self.sleep_patch.stop)

    def api_error(self, cls, status, code):
        return cls(
            "API request failed",
            response=httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1/responses")),
            body={"code": code, "message": "API request failed"},
        )

    def test_luna_uses_standard_processing_without_reasoning(self):
        self.assertEqual(generate_content("System", "User"), "A complete generated response.")
        request = self.client.responses.create.call_args.kwargs
        self.assertEqual(request["model"], "gpt-6-luna")
        self.assertEqual(request["service_tier"], "default")
        self.assertEqual(request["reasoning"], {"effort": "none"})
        self.assertEqual(request["temperature"], 1.05)
        self.assertEqual(request["max_output_tokens"], 1200)
        self.assertEqual(request["instructions"], "System")
        self.assertEqual(request["input"], "User")

    def test_custom_legacy_model_keeps_supported_request_parameters(self):
        self.app_settings.model_name = "gpt-4.1"
        generate_content("System", "User")
        request = self.client.responses.create.call_args.kwargs
        self.assertNotIn("reasoning", request)
        self.assertNotIn("service_tier", request)

    def test_temporary_errors_retry_and_return_output(self):
        for error in [
            APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/responses")),
            APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/responses")),
            self.api_error(InternalServerError, 503, "server_error"),
            self.api_error(RateLimitError, 429, "rate_limit_exceeded"),
        ]:
            with self.subTest(error=type(error).__name__):
                self.client.responses.create.reset_mock()
                self.sleep.reset_mock()
                self.client.responses.create.side_effect = [
                    error, SimpleNamespace(status="completed", output_text="Recovered output."),
                ]
                self.assertEqual(generate_content("System", "User"), "Recovered output.")
                self.assertEqual(self.client.responses.create.call_count, 2)
                self.sleep.assert_called_once_with(error, 1)

    def test_temporary_errors_have_a_bounded_attempt_budget(self):
        self.client.responses.create.side_effect = self.api_error(InternalServerError, 503, "server_error")
        with self.assertRaisesRegex(TransientGenerationError, "OpenAI generation failed"):
            generate_content("System", "User")
        self.assertEqual(self.client.responses.create.call_count, 3)
        self.assertEqual(self.sleep.call_count, 2)

    def test_exhausted_timeouts_are_reported_as_transient(self):
        self.client.responses.create.side_effect = APITimeoutError(
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
        )
        with self.assertRaises(TransientGenerationError):
            generate_content("System", "User")
        self.assertEqual(self.client.responses.create.call_count, 3)
        self.assertEqual(self.sleep.call_count, 2)

    def test_permanent_errors_fail_immediately(self):
        for error in [
            self.api_error(NotFoundError, 404, "model_not_found"),
            self.api_error(AuthenticationError, 401, "invalid_api_key"),
            self.api_error(RateLimitError, 429, "insufficient_quota"),
        ]:
            with self.subTest(error=type(error).__name__):
                self.client.responses.create.reset_mock()
                self.client.responses.create.side_effect = error
                with self.assertRaises(PermanentGenerationError):
                    generate_content("System", "User")
                self.client.responses.create.assert_called_once()
                self.sleep.assert_not_called()

    def test_incomplete_or_empty_output_is_never_accepted(self):
        for status, text in [("incomplete", "Truncated text"), ("failed", "Partial"), ("completed", ""), ("completed", "Content:")]:
            with self.subTest(status=status, text=text):
                self.client.responses.create.return_value = SimpleNamespace(status=status, output_text=text)
                with self.assertRaises(RuntimeError):
                    generate_content("System", "User")


class GenerationModelSettingsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_new_settings_and_empty_database_default_to_luna(self):
        self.assertEqual(AppSettings().model_name, "gpt-6-luna")
        self.assertEqual(get_app_settings().model_name, "gpt-6-luna")

    def test_old_cached_model_is_ignored(self):
        AppSettings.objects.create(model_name="gpt-6-luna", is_active=True)
        cache.set("active_app_settings", SimpleNamespace(model_name="gpt-4.1-nano"))
        self.assertEqual(get_app_settings().model_name, "gpt-6-luna")
        self.assertEqual(cache.get(APP_SETTINGS_CACHE_KEY).model_name, "gpt-6-luna")

    def test_migration_updates_legacy_settings_and_preserves_custom_models(self):
        legacy = AppSettings.objects.create(model_name="gpt-4.1-nano")
        default = AppSettings.objects.create(model_name="gpt-4.1-mini")
        custom = AppSettings.objects.create(model_name="gpt-4.1")
        migration = importlib.import_module("contents.migrations.0055_migrate_generation_model_to_luna")
        editor = SimpleNamespace(connection=connection)
        migration.migrate_legacy_models(apps, editor)
        migration.migrate_legacy_models(apps, editor)
        for obj in (legacy, default, custom):
            obj.refresh_from_db()
        self.assertEqual(legacy.model_name, "gpt-6-luna")
        self.assertEqual(default.model_name, "gpt-6-luna")
        self.assertEqual(custom.model_name, "gpt-4.1")
