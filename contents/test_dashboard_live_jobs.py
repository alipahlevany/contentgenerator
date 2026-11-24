from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from contents.models import GenerationJob


class DashboardLiveJobsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('overview-admin', 'admin@example.com', 'test-password')
        self.client.force_login(self.user)
        self.url = reverse('dashboard-live-jobs')

    def test_active_jobs_are_bounded_and_running_has_priority(self):
        for _ in range(7):
            GenerationJob.objects.create(count=10, status='pending')
        active = GenerationJob.objects.create(count=10, status='running', generated_count=4)
        GenerationJob.objects.create(count=10, status='completed', generated_count=10)
        response = self.client.get(self.url)
        data = response.json()
        self.assertEqual(data['total'], 8)
        self.assertEqual(len(data['jobs']), 6)
        self.assertEqual(data['jobs'][0]['id'], active.pk)
        self.assertEqual(data['jobs'][0]['generated_count'], 4)
        self.assertIn('no-store', response['Cache-Control'])

    def test_requires_job_permission(self):
        self.user.is_superuser = False
        self.user.save()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_overview_renders_launchers_and_live_panel(self):
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'id="live-runs-body"')
        self.assertContains(response, 'generation_type=email_reply')
        self.assertContains(response, 'Your content, in motion')
