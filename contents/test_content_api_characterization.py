from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from rest_framework.test import APIClient

from contents.models import (
    Audience,
    Content,
    ContentRule,
    ExternalClient,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)


class ContentAPICharacterizationTests(TestCase):
    list_fields = {
        "id",
        "title",
        "language",
        "topic",
        "audience",
        "goal",
        "prompt_template",
        "status",
        "created_at",
        "updated_at",
    }
    detail_fields = list_fields | {
        "prompt",
        "generated_content",
        "rules",
    }

    @classmethod
    def setUpTestData(cls):
        cls.active_client = ExternalClient.objects.create(
            name="Active content client",
            code="active-content-client",
            api_key="active-content-api-key",
            is_active=True,
        )
        cls.inactive_client = ExternalClient.objects.create(
            name="Inactive content client",
            code="inactive-content-client",
            api_key="inactive-content-api-key",
            is_active=False,
        )
        cls.language = Language.objects.create(
            name="English",
            code="en",
        )
        cls.topic = Topic.objects.create(name="Technology")
        cls.audience = Audience.objects.create(name="Developers")
        cls.goal = Goal.objects.create(name="Education")
        cls.template = PromptTemplate.objects.create(
            name="Standard Template",
            system_prompt="System prompt",
            user_prompt_template="User prompt",
        )
        cls.rule_one = ContentRule.objects.create(
            name="Use examples",
            prompt_text="Include examples.",
        )
        cls.rule_two = ContentRule.objects.create(
            name="Be concise",
            prompt_text="Keep it concise.",
        )

    def setUp(self):
        self.api = APIClient()
        self.list_url = reverse("contents:api-content-list")

    def _headers(self, api_key=None):
        if api_key is None:
            return {}
        return {"HTTP_X_API_KEY": api_key}

    def _create_content(self, **overrides):
        values = {
            "title": "Default title",
            "language": self.language,
            "topic": self.topic,
            "audience": self.audience,
            "goal": self.goal,
            "prompt_template": self.template,
            "prompt": "Default prompt",
            "generated_content": "Default generated body",
            "status": "generated",
        }
        values.update(overrides)
        return Content.objects.create(**values)

    def _get_list(self, api_key=None, data=None):
        return self.api.get(
            self.list_url,
            data or {},
            **self._headers(api_key),
        )

    def _get_detail(self, content_id, api_key=None):
        return self.api.get(
            reverse(
                "contents:api-content-detail",
                kwargs={"pk": content_id},
            ),
            **self._headers(api_key),
        )

    def assert_forbidden_response(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {"detail": "Authentication credentials were not provided."},
        )

    def test_content_urls_have_exact_names_and_routes(self):
        self.assertEqual(self.list_url, "/api/v1/contents/")
        list_match = resolve("/api/v1/contents/")
        self.assertEqual(list_match.namespace, "contents")
        self.assertEqual(list_match.url_name, "api-content-list")

        detail_url = reverse(
            "contents:api-content-detail",
            kwargs={"pk": 17},
        )
        self.assertEqual(detail_url, "/api/v1/contents/17/")
        detail_match = resolve(detail_url)
        self.assertEqual(detail_match.namespace, "contents")
        self.assertEqual(detail_match.url_name, "api-content-detail")
        self.assertEqual(detail_match.kwargs, {"pk": 17})

    def test_content_list_rejects_missing_invalid_and_inactive_keys(self):
        responses = (
            self._get_list(),
            self._get_list("invalid-content-api-key"),
            self._get_list(self.inactive_client.api_key),
        )

        for response in responses:
            self.assert_forbidden_response(response)

    def test_valid_key_returns_exact_list_fields_and_related_names(self):
        content = self._create_content(title="Related content")

        response = self._get_list(self.active_client.api_key)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        item = response.json()[0]
        self.assertEqual(set(item), self.list_fields)
        self.assertNotIn("rules", item)
        self.assertNotIn("prompt", item)
        self.assertNotIn("generated_content", item)
        self.assertEqual(
            item,
            {
                "id": content.id,
                "title": "Related content",
                "language": "English",
                "topic": "Technology",
                "audience": "Developers",
                "goal": "Education",
                "prompt_template": "Standard Template",
                "status": "generated",
                "created_at": content.created_at.isoformat().replace(
                    "+00:00", "Z"
                ),
                "updated_at": content.updated_at.isoformat().replace(
                    "+00:00", "Z"
                ),
            },
        )

    def test_content_list_represents_null_related_fields_as_null(self):
        self._create_content(
            language=None,
            topic=None,
            audience=None,
            goal=None,
            prompt_template=None,
        )

        response = self._get_list(self.active_client.api_key)

        self.assertEqual(response.status_code, 200)
        item = response.json()[0]
        self.assertIsNone(item["language"])
        self.assertIsNone(item["topic"])
        self.assertIsNone(item["audience"])
        self.assertIsNone(item["goal"])
        self.assertIsNone(item["prompt_template"])

    def test_content_list_orders_newest_first(self):
        oldest = self._create_content(title="Oldest")
        middle = self._create_content(title="Middle")
        newest = self._create_content(title="Newest")

        response = self._get_list(self.active_client.api_key)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()],
            [newest.id, middle.id, oldest.id],
        )

    def test_content_list_returns_at_most_100_newest_items(self):
        contents = [
            self._create_content(title=f"Content {index:03d}")
            for index in range(101)
        ]

        response = self._get_list(self.active_client.api_key)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 100)
        self.assertEqual(
            [item["id"] for item in response.json()],
            [content.id for content in reversed(contents[1:])],
        )
        self.assertNotIn(contents[0].id, [item["id"] for item in response.json()])

    def test_content_list_filters_by_exact_status(self):
        generated = self._create_content(title="Generated", status="generated")
        self._create_content(title="Draft", status="draft")
        published = self._create_content(title="Published", status="published")

        generated_response = self._get_list(
            self.active_client.api_key,
            {"status": "generated"},
        )
        published_response = self._get_list(
            self.active_client.api_key,
            {"status": "published"},
        )
        mismatched_case_response = self._get_list(
            self.active_client.api_key,
            {"status": "Generated"},
        )

        self.assertEqual(generated_response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in generated_response.json()],
            [generated.id],
        )
        self.assertEqual(
            [item["id"] for item in published_response.json()],
            [published.id],
        )
        self.assertEqual(mismatched_case_response.status_code, 200)
        self.assertEqual(mismatched_case_response.json(), [])

    def test_content_list_searches_title_prompt_and_generated_content(self):
        title_match = self._create_content(
            title="Unique Needle in Title",
            prompt="Nothing here",
            generated_content="Nothing here either",
        )
        prompt_match = self._create_content(
            title="Prompt match",
            prompt="A UNIQUE NEEDLE appears in the prompt",
            generated_content="Nothing here",
        )
        body_match = self._create_content(
            title="Body match",
            prompt="Nothing here",
            generated_content="The body contains unique needle text",
        )
        self._create_content(
            title="Unrelated",
            prompt="Unrelated",
            generated_content="Unrelated",
        )

        response = self._get_list(
            self.active_client.api_key,
            {"q": "unique needle"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()],
            [body_match.id, prompt_match.id, title_match.id],
        )

    def test_content_list_returns_empty_list_when_search_has_no_matches(self):
        self._create_content()

        response = self._get_list(
            self.active_client.api_key,
            {"q": "definitely absent"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_content_list_uses_one_content_query_with_related_joins(self):
        self._create_content()

        with CaptureQueriesContext(connection) as queries:
            response = self._get_list(self.active_client.api_key)

        self.assertEqual(response.status_code, 200)
        content_queries = [
            query["sql"]
            for query in queries.captured_queries
            if 'FROM "contents_content"' in query["sql"]
        ]
        self.assertEqual(len(content_queries), 1)
        sql = content_queries[0]
        for table in (
            "contents_language",
            "contents_topic",
            "contents_audience",
            "contents_goal",
            "contents_prompttemplate",
        ):
            self.assertIn(f'JOIN "{table}"', sql)

    def test_content_detail_rejects_missing_invalid_and_inactive_keys(self):
        content = self._create_content()
        responses = (
            self._get_detail(content.id),
            self._get_detail(content.id, "invalid-content-api-key"),
            self._get_detail(content.id, self.inactive_client.api_key),
        )

        for response in responses:
            self.assert_forbidden_response(response)

    def test_content_detail_returns_exact_fields_related_names_and_rules(self):
        content = self._create_content(
            title="Detailed content",
            prompt="Detailed prompt",
            generated_content="Detailed generated body",
            status="published",
        )
        content.rules.set([self.rule_one, self.rule_two])

        response = self._get_detail(content.id, self.active_client.api_key)

        self.assertEqual(response.status_code, 200)
        item = response.json()
        self.assertEqual(set(item), self.detail_fields)
        self.assertEqual(
            item,
            {
                "id": content.id,
                "title": "Detailed content",
                "language": "English",
                "topic": "Technology",
                "audience": "Developers",
                "goal": "Education",
                "prompt_template": "Standard Template",
                "status": "published",
                "created_at": content.created_at.isoformat().replace(
                    "+00:00", "Z"
                ),
                "updated_at": content.updated_at.isoformat().replace(
                    "+00:00", "Z"
                ),
                "prompt": "Detailed prompt",
                "generated_content": "Detailed generated body",
                "rules": ["Use examples", "Be concise"],
            },
        )

    def test_content_detail_represents_null_related_fields_and_empty_rules(self):
        content = self._create_content(
            language=None,
            topic=None,
            audience=None,
            goal=None,
            prompt_template=None,
        )

        response = self._get_detail(content.id, self.active_client.api_key)

        self.assertEqual(response.status_code, 200)
        item = response.json()
        self.assertIsNone(item["language"])
        self.assertIsNone(item["topic"])
        self.assertIsNone(item["audience"])
        self.assertIsNone(item["goal"])
        self.assertIsNone(item["prompt_template"])
        self.assertEqual(item["rules"], [])

    def test_content_detail_returns_exact_not_found_response(self):
        response = self._get_detail(999999, self.active_client.api_key)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "No Content matches the given query."})

    def test_content_detail_uses_joined_relations_and_one_rules_prefetch(self):
        content = self._create_content()
        content.rules.set([self.rule_one, self.rule_two])

        with CaptureQueriesContext(connection) as queries:
            response = self._get_detail(content.id, self.active_client.api_key)

        self.assertEqual(response.status_code, 200)
        content_queries = [
            query["sql"]
            for query in queries.captured_queries
            if 'FROM "contents_content"' in query["sql"]
        ]
        rules_queries = [
            query["sql"]
            for query in queries.captured_queries
            if 'FROM "contents_contentrule"' in query["sql"]
        ]
        self.assertEqual(len(content_queries), 1)
        self.assertEqual(len(rules_queries), 1)
        for table in (
            "contents_language",
            "contents_topic",
            "contents_audience",
            "contents_goal",
            "contents_prompttemplate",
        ):
            self.assertIn(f'JOIN "{table}"', content_queries[0])
