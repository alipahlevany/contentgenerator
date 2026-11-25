from django.test import SimpleTestCase

from contents.templatetags.admin_groups import grouped_generation_apps


def model(object_name, admin_url=None):
    return {
        "object_name": object_name,
        "name": object_name,
        "admin_url": admin_url or f"/admin/contents/{object_name.lower()}/",
        "perms": {"add": True, "change": True, "view": True},
    }


class AdminNavigationGroupsTests(SimpleTestCase):
    def setUp(self):
        self.apps = [
            {
                "app_label": "contents",
                "name": "Contents",
                "app_url": "/admin/contents/",
                "has_module_perms": True,
                "models": [
                    model("Greeting"),
                    model("GreetingGenerationSettings"),
                    model("EmailReply"),
                    model("ReplyGenerationSettings"),
                    model("ReplyContentExport"),
                    model("Content"),
                    model("StandardGenerationSettings"),
                    model("ContentExport"),
                    model("GenerationJob"),
                    model("GenerationJobLog"),
                    model("WarmupTemplate"),
                ],
            },
            {
                "app_label": "auth",
                "name": "Authentication and Authorization",
                "app_url": "/admin/auth/",
                "has_module_perms": True,
                "models": [model("User")],
            },
        ]

    def test_related_models_are_grouped_and_filtered_links_are_added(self):
        grouped = grouped_generation_apps(self.apps)
        self.assertEqual(
            [app["name"] for app in grouped],
            ["Greeting", "Replies", "Standard", "Shared generation tools", "Authentication and Authorization"],
        )
        self.assertEqual(
            [item["name"] for item in grouped[0]["models"]],
            ["Greetings", "Greeting settings", "Greeting generation jobs", "Greeting export history"],
        )
        self.assertEqual(
            [item["name"] for item in grouped[1]["models"]],
            ["Generated replies", "Reply settings", "Reply export history", "Reply generation jobs"],
        )
        self.assertEqual(
            [item["name"] for item in grouped[2]["models"]],
            ["Standard content", "Standard settings", "Standard generation jobs", "Standard export history"],
        )
        self.assertIn(
            "generation_type__exact=greeting",
            grouped[0]["models"][2]["admin_url"],
        )
        self.assertIn(
            "content__content_type__exact=standard",
            grouped[2]["models"][3]["admin_url"],
        )

    def test_source_app_list_is_not_mutated(self):
        original_names = [item["name"] for item in self.apps[0]["models"]]
        grouped_generation_apps(self.apps)
        self.assertEqual(
            [item["name"] for item in self.apps[0]["models"]],
            original_names,
        )

    def test_missing_contents_app_leaves_other_apps_unchanged(self):
        auth_apps = [self.apps[1]]
        self.assertEqual(grouped_generation_apps(auth_apps), auth_apps)
