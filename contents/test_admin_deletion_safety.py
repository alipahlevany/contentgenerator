from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from contents.models import Content, GenerationJob, GenerationJobLog, Greeting


class AdminDeletionSafetyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="deletion-safety-admin",
            email="admin@example.com",
            password="test-password",
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_job_delete_confirmation_explains_content_retention(self):
        job = GenerationJob.objects.create(status="completed")
        GenerationJobLog.objects.create(
            job=job,
            level="success",
            message="Completed",
        )

        response = self.client.get(
            reverse("admin:contents_generationjob_delete", args=(job.pk,))
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Generated content is safe")
        self.assertContains(response, "Generation job logs")

    def test_admin_job_delete_preserves_linked_content(self):
        job = GenerationJob.objects.create(status="completed")
        content = Content.objects.create(
            title="Generated output",
            content_type="greeting",
            generation_job=job,
            prompt="Prompt",
            generated_content="Hello there",
        )

        response = self.client.post(
            reverse("admin:contents_generationjob_delete", args=(job.pk,)),
            {"post": "yes"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(GenerationJob.objects.filter(pk=job.pk).exists())
        content.refresh_from_db()
        self.assertIsNone(content.generation_job_id)

    def test_risky_bulk_delete_actions_are_unavailable(self):
        request = RequestFactory().get("/admin/")
        request.user = self.user

        job_actions = admin.site._registry[GenerationJob].get_actions(request)
        greeting_actions = admin.site._registry[Greeting].get_actions(request)

        self.assertNotIn("delete_selected", job_actions)
        self.assertNotIn("delete_selected", greeting_actions)
