from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from contents.models import ExternalClient


class KeyReplacementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('key-admin', 'admin@example.com', 'test-password')
        self.client.force_login(self.user)
        self.target, self.old = ExternalClient.create_with_api_key(name='Zharik', code='zharik')
        self.other, self.other_key = ExternalClient.create_with_api_key(name='Hub', code='hub')
        self.url = reverse('admin:contents_externalclient_replace_api_key', args=[self.target.pk])

    def test_get_does_not_rotate_and_confirm_rotates_only_target(self):
        old_hash = self.target.api_key_hash
        page = self.client.get(self.url)
        self.assertContains(page, 'Replace key &amp; show new key')
        self.target.refresh_from_db()
        self.assertEqual(self.target.api_key_hash, old_hash)
        response = self.client.post(self.url, {'confirmation': page.context_data['confirmation']})
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        new = response.context_data['api_key']
        self.target.refresh_from_db()
        self.assertTrue(self.target.matches_api_key_secret(new.split('_', 2)[2]))
        self.assertFalse(self.target.matches_api_key_secret(self.old.split('_', 2)[2]))
        self.other.refresh_from_db()
        self.assertTrue(self.other.matches_api_key_secret(self.other_key.split('_', 2)[2]))
        replay = self.client.post(self.url, {'confirmation': page.context_data['confirmation']})
        self.assertEqual(replay.status_code, 403)
        self.assertEqual(self.client.post(self.url, {}).status_code, 403)

    def test_permissions_and_csrf_required(self):
        staff = get_user_model().objects.create_user('viewer', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.user)
        self.assertEqual(csrf.post(self.url, {}).status_code, 403)
