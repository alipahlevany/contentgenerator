from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from contents.models import GenerationJob


class JobLiveProgressTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='live-admin', email='live@example.com', password='test-password'
        )
        self.client.force_login(self.user)
        self.job = GenerationJob.objects.create(count=10, generation_type='email_reply')
        self.url = reverse('admin:contents_generationjob_progress')

    def test_poll_reflects_committed_progress_and_completion(self):
        GenerationJob.objects.filter(pk=self.job.pk).update(
            generated_count=4, skipped_count=2, status='running', error_message='<script>bad</script>'
        )
        response = self.client.get(self.url, {'ids': self.job.pk})
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        row = response.json()['jobs'][0]
        self.assertEqual(row['values']['generated_count'], 4)
        self.assertEqual(row['values']['remaining_display'], 6)
        self.assertIn('40%', row['html']['progress_bar'])
        self.assertIn('Stop', row['html']['job_actions'])
        GenerationJob.objects.filter(pk=self.job.pk).update(generated_count=10, status='completed')
        row = self.client.get(self.url, {'ids': self.job.pk}).json()['jobs'][0]
        self.assertIn('100%', row['html']['progress_bar'])
        self.assertIn('View run', row['html']['job_actions'])

    def test_permissions_and_input_limits(self):
        for ids in ('', 'x', ','.join(['1'] * 101), '9' * 30):
            self.assertEqual(self.client.get(self.url, {'ids': ids}).status_code, 400)
        self.user.is_superuser = False
        self.user.save()
        self.assertEqual(self.client.get(self.url, {'ids': self.job.pk}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url, {'ids': self.job.pk}).status_code, 302)

    def test_list_and_detail_include_polling_marker(self):
        for name, args in [('changelist', []), ('change', [self.job.pk])]:
            response = self.client.get(reverse('admin:contents_generationjob_' + name, args=args))
            self.assertContains(response, 'data-progress-url=')
            self.assertContains(response, 'generation_jobs.js?v=20261124-live-progress')
