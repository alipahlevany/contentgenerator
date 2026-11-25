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
from contents.models import Content, ExternalClient, ContentExport


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
        response = self.admin._csv_response(self.queryset)
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(rows[0]["title"], "'=unsafe title")
        self.assertEqual(rows[0]["body"], "Hello, friend.\nHow are you?")
        self.assertEqual(rows[0]["language"], "en")

    def test_json_download_contains_selected_reply(self):
        response = self.admin._json_response(self.queryset)
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
        recipient = ExternalClient.objects.create(name="Recipient", code="recipient", api_key="test-key")
        response = self.client.post(
            reverse("admin:contents_emailreply_changelist"),
            {"action": "download_replies_csv", "export_client": recipient.pk, "_selected_action": [selected.pk], "index": 0},
        )
        self.assertEqual(response.status_code, 200)
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual([row["body"] for row in rows], ["Selected reply"])

        self.assertEqual(ContentExport.objects.filter(client=recipient, status="success").count(), 1)
        again = self.client.post(
            reverse("admin:contents_emailreply_changelist"),
            {"action": "download_replies_json", "export_client": recipient.pk, "_selected_action": [selected.pk], "index": 0},
        )
        self.assertEqual(again.status_code, 302)
        other = ExternalClient.objects.create(name="Other recipient", code="other-recipient", api_key="test-other")
        different = self.client.post(
            reverse("admin:contents_emailreply_changelist"),
            {"action": "download_replies_json", "export_client": other.pk, "_selected_action": [selected.pk], "index": 0},
        )
        self.assertEqual(json.loads(different.content)[0]["body"], "Selected reply")

    def test_missing_or_invalid_recipient_does_not_record_exports(self):
        user = get_user_model().objects.create_superuser('export-check', 'check@example.com', 'test-password')
        self.client.force_login(user)
        reply = Content.objects.create(title='Reply', prompt='p', content_type='email_reply', generated_content='Body', status='generated')
        for value in ('', 'invalid', '999999'):
            response = self.client.post(reverse('admin:contents_emailreply_changelist'), {
                'action': 'download_replies_csv', 'export_client': value,
                '_selected_action': [reply.pk], 'index': 0,
            })
            self.assertNotIn('Content-Disposition', response)
        self.assertEqual(ContentExport.objects.count(), 0)

    def test_export_prompts_then_creates_named_destination(self):
        user = get_user_model().objects.create_superuser('destination-admin', 'destination@example.com', 'test-password')
        self.client.force_login(user)
        reply = Content.objects.create(title='Reply', prompt='p', content_type='email_reply', generated_content='Body', status='generated')
        url = reverse('admin:contents_emailreply_changelist')
        selection = {'action': 'download_replies_json', '_selected_action': [reply.pk], 'index': 0}
        page = self.client.post(url, selection)
        self.assertContains(page, 'Choose a destination')
        self.assertEqual(ExternalClient.objects.count(), 0)
        response = self.client.post(url, dict(selection, export_client='__new__', export_destination='Customer campaign'))
        self.assertEqual(response['Content-Type'], 'application/json; charset=utf-8')
        client = ExternalClient.objects.get(name='Customer campaign')
        self.assertFalse(client.receives_standard_content)
        self.assertFalse(client.api_key_hash)
        self.assertFalse(client.api_key)
        again = self.client.post(url, dict(selection, export_client='__new__', export_destination='Customer campaign'))
        self.assertEqual(again.status_code, 302)
        self.assertEqual(ExternalClient.objects.count(), 1)
        self.assertEqual(ContentExport.objects.count(), 1)

    def test_export_workspace_excludes_greetings_even_when_posted(self):
        user = get_user_model().objects.create_superuser('isolated', 'isolated@example.com', 'test-password')
        self.client.force_login(user)
        greeting = Content.objects.create(title='Greeting only', content_type='greeting', prompt='p', generated_content='Hello', status='generated')
        reply = Content.objects.create(title='Reply only', content_type='email_reply', prompt='p', generated_content='Reply', status='generated')
        destination = ExternalClient.objects.create(name='Isolated destination', code='isolated-destination')
        url = reverse('admin:contents_emailreply_changelist')
        page = self.client.get(url)
        self.assertContains(page, 'Reply only')
        self.assertNotContains(page, 'Greeting only')
        response = self.client.post(url, {'action': 'download_replies_json', 'index': 0, '_selected_action': [reply.pk, greeting.pk], 'export_client': destination.pk})
        self.assertEqual([row['id'] for row in json.loads(response.content)], [reply.pk])
        self.assertFalse(ContentExport.objects.filter(content=greeting).exists())
        old_page = self.client.get(reverse('admin:contents_emailreply_changelist'))
        self.assertContains(old_page, 'Generated replies')
        self.assertContains(old_page, 'CSV or JSON')
        self.assertContains(old_page, 'Reply export history')
