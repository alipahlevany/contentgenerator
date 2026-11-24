import csv
import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from contents.admin.content import EmailReplyAdmin
from contents.models import Content


class ReplyAdminExportTests(SimpleTestCase):
    def setUp(self):
        self.admin = EmailReplyAdmin(model=Mock(), admin_site=Mock())
        self.reply = SimpleNamespace(
            id=17,
            title="=unsafe title",
            language=SimpleNamespace(code="en"),
            generated_content="Hello, friend.\nHow are you?",
            status="generated",
            generation_job_id=8,
            created_at=datetime(2026, 11, 24, tzinfo=timezone.utc),
        )
        self.queryset = Mock()
        self.queryset.select_related.return_value.order_by.return_value.iterator.return_value = iter([self.reply])

    def test_csv_download_preserves_multiline_reply_and_escapes_formula(self):
        response = self.admin.download_replies_csv(None, self.queryset)
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(rows[0]["title"], "'=unsafe title")
        self.assertEqual(rows[0]["body"], "Hello, friend.\nHow are you?")
        self.assertEqual(rows[0]["language"], "en")

    def test_json_download_contains_selected_reply(self):
        response = self.admin.download_replies_json(None, self.queryset)
        rows = json.loads(response.content)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], 17)
        self.assertEqual(rows[0]["body"], "Hello, friend.\nHow are you?")


class ReplyAdminActionTests(TestCase):
    def test_csv_action_downloads_only_selected_replies(self):
        staff = get_user_model().objects.create_superuser(
            username="export-admin", email="admin@example.com", password="test-password"
        )
        self.client.force_login(staff)
        selected = Content.objects.create(
            title="Selected", content_type="email_reply", prompt="prompt",
            generated_content="Selected reply", status="generated",
        )
        Content.objects.create(
            title="Other", content_type="email_reply", prompt="prompt",
            generated_content="Other reply", status="generated",
        )
        response = self.client.post(
            reverse("admin:contents_emailreply_changelist"),
            {"action": "download_replies_csv", "_selected_action": [selected.pk], "index": 0},
        )
        self.assertEqual(response.status_code, 200)
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual([row["body"] for row in rows], ["Selected reply"])
