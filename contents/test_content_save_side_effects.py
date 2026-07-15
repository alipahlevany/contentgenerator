from unittest.mock import patch

from django.test import TestCase

from contents.models import Content, Topic


class ContentSaveSideEffectTests(TestCase):
    def test_creating_content_does_not_queue_external_delivery(self):
        with patch("contents.tasks.send_model_data_to_api.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                content = Content.objects.create(
                    title="Created content",
                    prompt="Prompt",
                    generated_content="Body",
                    content_hash="created-hash",
                    status="generated",
                )

        self.assertIsNotNone(content.pk)
        delay.assert_not_called()

    def test_updating_content_does_not_queue_external_delivery(self):
        content = Content.objects.create(
            title="Original",
            prompt="Prompt",
            content_hash="update-hash",
        )

        with patch("contents.tasks.send_model_data_to_api.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                content.title = "Updated"
                content.save(update_fields=["title", "updated_at"])

        delay.assert_not_called()
        content.refresh_from_db()
        self.assertEqual(content.title, "Updated")

    def test_generation_shaped_content_can_still_be_persisted(self):
        topic = Topic.objects.create(name="Generation Topic")

        with patch("contents.tasks.send_model_data_to_api.delay") as delay:
            content = Content.objects.create(
                title="Generated title",
                topic=topic,
                prompt="Rendered generation prompt",
                generated_content="Generated body",
                content_hash="generation-hash",
                status="generated",
            )

        delay.assert_not_called()
        self.assertEqual(content.status, "generated")
        self.assertEqual(content.topic, topic)

    def test_duplicate_hash_storage_behavior_is_unchanged(self):
        first = Content.objects.create(
            title="First",
            prompt="First prompt",
            content_hash="same-hash",
            status="generated",
        )
        second = Content.objects.create(
            title="Second",
            prompt="Second prompt",
            content_hash="same-hash",
            status="generated",
        )

        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(
            Content.objects.filter(content_hash="same-hash").count(),
            2,
        )
