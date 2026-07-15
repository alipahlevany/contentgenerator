from django.contrib import admin
from django.contrib.auth.hashers import check_password
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from rest_framework.test import APIClient

from contents.admin.external_client import ExternalClientAdmin
from contents.models import ExternalClient


class ExternalClientAPIKeySecurityTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.client_record, self.raw_key = ExternalClient.create_with_api_key(
            name="Hashed client",
            code="hashed-client",
        )

    def request(self, key):
        return self.api.get(
            "/api/v1/datasets/",
            HTTP_X_API_KEY=key,
        )

    def test_new_key_authenticates_and_database_stores_only_hash(self):
        response = self.request(self.raw_key)
        self.client_record.refresh_from_db()
        _, prefix, secret = self.raw_key.split("_", 2)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client_record.api_key_prefix, prefix)
        self.assertIsNone(self.client_record.api_key)
        self.assertNotIn(secret, self.client_record.api_key_hash)
        self.assertNotIn(self.raw_key, self.client_record.api_key_hash)
        self.assertTrue(check_password(secret, self.client_record.api_key_hash))

    def test_authentication_uses_prefix_lookup_without_querying_raw_secret(self):
        _, prefix, secret = self.raw_key.split("_", 2)
        with CaptureQueriesContext(connection) as queries:
            response = self.request(self.raw_key)

        sql = " ".join(query["sql"] for query in queries)
        self.assertEqual(response.status_code, 200)
        self.assertIn(prefix, sql)
        self.assertNotIn(secret, sql)
        self.assertNotIn(self.raw_key, sql)

    def test_wrong_secret_and_invalid_prefix_are_rejected(self):
        _, prefix, _ = self.raw_key.split("_", 2)

        for key in (
            f"cg_{prefix}_wrong-secret",
            "cg_unknownprefix_wrong-secret",
        ):
            with self.subTest(key=key):
                response = self.request(key)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(
                    response.json(),
                    {"detail": "Authentication credentials were not provided."},
                )

    def test_inactive_hashed_client_is_rejected(self):
        self.client_record.is_active = False
        self.client_record.save(update_fields=["is_active", "updated_at"])

        self.assertEqual(self.request(self.raw_key).status_code, 403)

    def test_rotation_invalidates_old_key_and_returns_new_key_once(self):
        old_key = self.raw_key
        new_key = self.client_record.rotate_api_key()

        self.assertEqual(self.request(old_key).status_code, 403)
        self.assertEqual(self.request(new_key).status_code, 200)
        self.client_record.refresh_from_db()
        self.assertFalse(hasattr(self.client_record, "raw_api_key"))
        self.assertNotEqual(new_key, self.client_record.api_key_hash)
        self.assertNotIn(new_key, repr(self.client_record.__dict__))

    def test_legacy_plaintext_key_remains_compatible(self):
        legacy = ExternalClient.objects.create(
            name="Legacy client",
            code="legacy-client",
            api_key="legacy-plaintext-key",
        )

        response = self.request(legacy.api_key)

        self.assertEqual(response.status_code, 200)
        legacy.refresh_from_db()
        self.assertEqual(legacy.api_key, "legacy-plaintext-key")
        self.assertFalse(legacy.api_key_hash)

    def test_raw_key_is_not_exposed_by_string_or_admin_display(self):
        model_admin = ExternalClientAdmin(ExternalClient, admin.site)
        display = str(model_admin.api_key_identifier(self.client_record))

        self.assertEqual(str(self.client_record), "Hashed client")
        self.assertNotIn(self.raw_key, str(self.client_record))
        self.assertNotIn(self.raw_key, display)
        self.assertNotIn(self.client_record.api_key_hash, display)
        self.assertIn(self.client_record.api_key_prefix, display)

    def test_multiple_new_clients_can_have_no_legacy_plaintext_key(self):
        second, second_key = ExternalClient.create_with_api_key(
            name="Second hashed client",
            code="second-hashed-client",
        )

        self.assertIsNone(self.client_record.api_key)
        self.assertIsNone(second.api_key)
        self.assertNotEqual(self.raw_key, second_key)
