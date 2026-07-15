from unittest.mock import patch

from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import resolve, reverse
from django.utils import timezone

from rest_framework.test import APIClient, APIRequestFactory

from contents.models import (
    Audience,
    Content,
    ContentExport,
    ContentRule,
    ExternalClient,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)
from contents.serializers import ContentExportRequestSerializer
from contents.views import ContentExportAPIView


class ExportFixtureMixin:
    @classmethod
    def create_reference_data(cls):
        cls.language = Language.objects.create(name="English", code="en")
        cls.other_language = Language.objects.create(name="French", code="fr")
        cls.inactive_language = Language.objects.create(
            name="Inactive Language",
            code="xx",
            is_active=False,
        )
        cls.topic = Topic.objects.create(name="Technology")
        cls.other_topic = Topic.objects.create(name="Travel")
        cls.audience = Audience.objects.create(name="Developers")
        cls.other_audience = Audience.objects.create(name="Managers")
        cls.goal = Goal.objects.create(name="Education")
        cls.other_goal = Goal.objects.create(name="Promotion")
        cls.template = PromptTemplate.objects.create(
            name="Standard Template",
            system_prompt="System",
            user_prompt_template="User",
        )
        cls.other_template = PromptTemplate.objects.create(
            name="Other Template",
            system_prompt="Other system",
            user_prompt_template="Other user",
        )
        cls.rule_one = ContentRule.objects.create(
            name="Rule One",
            prompt_text="First rule",
        )
        cls.rule_two = ContentRule.objects.create(
            name="Rule Two",
            prompt_text="Second rule",
        )
        cls.inactive_rule = ContentRule.objects.create(
            name="Inactive Rule",
            prompt_text="Inactive",
            is_active=False,
        )

    def create_client(self, suffix, active=True):
        return ExternalClient.objects.create(
            name=f"Client {suffix}",
            code=f"client-{suffix}",
            api_key=f"api-key-{suffix}",
            is_active=active,
        )

    def create_content(self, **overrides):
        sequence = Content.objects.count() + 1
        values = {
            "title": f"Content {sequence}",
            "language": self.language,
            "topic": self.topic,
            "audience": self.audience,
            "goal": self.goal,
            "prompt_template": self.template,
            "prompt": f"Prompt {sequence}",
            "generated_content": f"Body {sequence}",
            "content_hash": f"hash-{sequence}",
            "status": "generated",
        }
        values.update(overrides)
        return Content.objects.create(**values)


class ContentExportAPICharacterizationTests(ExportFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_reference_data()
        cls.client_a = ExternalClient.objects.create(
            name="Client A",
            code="client-a",
            api_key="api-key-a",
            is_active=True,
        )
        cls.client_b = ExternalClient.objects.create(
            name="Client B",
            code="client-b",
            api_key="api-key-b",
            is_active=True,
        )
        cls.inactive_client = ExternalClient.objects.create(
            name="Inactive Client",
            code="inactive-client",
            api_key="inactive-api-key",
            is_active=False,
        )

    def setUp(self):
        self.api = APIClient()
        self.url = reverse("contents:api-content-export")

    def export(self, payload=None, client=None, api_key=None):
        if api_key is None and client is not None:
            api_key = client.api_key
        headers = {} if api_key is None else {"HTTP_X_API_KEY": api_key}
        return self.api.post(self.url, payload or {}, format="json", **headers)

    def all_payload(self, **overrides):
        payload = {
            "count": 100,
            "delay_seconds": 0,
            "languages": "all",
            "topics": "all",
            "audiences": "all",
            "goals": "all",
            "rules": "all",
            "prompt_templates": "all",
        }
        payload.update(overrides)
        return payload

    def assert_forbidden(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {"detail": "Authentication credentials were not provided."},
        )

    def test_exact_export_url_and_url_name(self):
        self.assertEqual(self.url, "/api/v1/contents/export/")
        match = resolve(self.url)
        self.assertEqual(match.namespace, "contents")
        self.assertEqual(match.url_name, "api-content-export")

    def test_missing_invalid_and_inactive_api_keys_are_forbidden(self):
        responses = (
            self.export(),
            self.export(api_key="invalid-api-key"),
            self.export(api_key=self.inactive_client.api_key),
        )
        for response in responses:
            self.assert_forbidden(response)

    def test_valid_key_uses_request_client_identity(self):
        content = self.create_content()

        response = self.export({"count": 1}, client=self.client_a)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["client"], self.client_a.code)
        ledger = ContentExport.objects.get(content=content)
        self.assertEqual(ledger.client, self.client_a)

    def test_request_defaults_and_delay_seconds_compatibility(self):
        serializer = ContentExportRequestSerializer(data={})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data,
            {
                "count": 1,
                "delay_seconds": 0.0,
                "languages": "all",
                "topics": "all",
                "audiences": "all",
                "goals": "all",
                "rules": "all",
                "prompt_templates": "all",
            },
        )

        content = self.create_content()
        response = self.export(
            {"count": 1, "delay_seconds": 60},
            client=self.client_a,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["id"], content.id)

    def test_count_minimum_maximum_and_delay_validation_errors(self):
        cases = (
            (
                {"count": 0},
                {"count": ["Ensure this value is greater than or equal to 1."]},
            ),
            (
                {"count": 1001},
                {"count": ["Ensure this value is less than or equal to 1000."]},
            ),
            (
                {"delay_seconds": -1},
                {"delay_seconds": ["Ensure this value is greater than or equal to 0."]},
            ),
            (
                {"delay_seconds": 61},
                {"delay_seconds": ["Ensure this value is less than or equal to 60."]},
            ),
        )
        for payload, expected in cases:
            with self.subTest(payload=payload):
                response = self.export(payload, client=self.client_a)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), expected)

    def test_count_accepts_exact_minimum_and_maximum(self):
        for count in (1, 1000):
            serializer = ContentExportRequestSerializer(data={"count": count})
            self.assertTrue(serializer.is_valid(), serializer.errors)
            self.assertEqual(serializer.validated_data["count"], count)

    def test_explicit_duplicate_and_numeric_string_ids_are_normalized(self):
        payload = self.all_payload(
            languages=[str(self.language.id), self.language.id, str(self.language.id)],
            rules=[str(self.rule_one.id), self.rule_one.id, self.rule_two.id],
        )
        serializer = ContentExportRequestSerializer(data=payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["languages"], [self.language.id])
        self.assertEqual(
            serializer.validated_data["rules"],
            [self.rule_one.id, self.rule_two.id],
        )

    def test_empty_required_selections_return_exact_errors(self):
        required_fields = (
            "languages",
            "topics",
            "audiences",
            "goals",
            "prompt_templates",
        )
        for field in required_fields:
            with self.subTest(field=field):
                response = self.export(
                    self.all_payload(**{field: []}),
                    client=self.client_a,
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json(),
                    {field: ["Use \"all\" or provide at least one ID."]},
                )

    def test_inactive_and_nonexistent_ids_return_exact_errors(self):
        cases = (
            (
                {"languages": [self.inactive_language.id]},
                {"languages": [
                    f"These IDs do not exist or are inactive: {self.inactive_language.id}"
                ]},
            ),
            (
                {"topics": [999999]},
                {"topics": ["These IDs do not exist or are inactive: 999999"]},
            ),
            (
                {"rules": [self.inactive_rule.id]},
                {"rules": [
                    f"These IDs do not exist or are inactive: {self.inactive_rule.id}"
                ]},
            ),
        )
        for overrides, expected in cases:
            with self.subTest(overrides=overrides):
                response = self.export(
                    self.all_payload(**overrides),
                    client=self.client_a,
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), expected)

    def test_rules_all_and_empty_list_apply_no_rule_filter(self):
        without_rules = self.create_content(title="Without rules")
        with_rules = self.create_content(title="With rules")
        with_rules.rules.add(self.rule_one)

        all_response = self.export(
            self.all_payload(rules="all"),
            client=self.client_a,
        )
        empty_response = self.export(
            self.all_payload(rules=[]),
            client=self.client_b,
        )

        expected_ids = [without_rules.id, with_rules.id]
        self.assertEqual(
            [item["id"] for item in all_response.json()["items"]],
            expected_ids,
        )
        self.assertEqual(
            [item["id"] for item in empty_response.json()["items"]],
            expected_ids,
        )

    def test_only_generated_contents_are_eligible_and_order_is_ascending_id(self):
        first = self.create_content(title="First")
        self.create_content(title="Draft", status="draft")
        third = self.create_content(title="Third")
        self.create_content(title="Published", status="published")

        response = self.export(self.all_payload(), client=self.client_a)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()["items"]],
            [first.id, third.id],
        )

    def test_each_foreign_key_filter_selects_only_matching_content(self):
        matching = self.create_content(title="Matching")
        alternatives = {
            "languages": ("language", self.language.id, self.other_language),
            "topics": ("topic", self.topic.id, self.other_topic),
            "audiences": ("audience", self.audience.id, self.other_audience),
            "goals": ("goal", self.goal.id, self.other_goal),
            "prompt_templates": (
                "prompt_template",
                self.template.id,
                self.other_template,
            ),
        }

        for index, (request_field, config) in enumerate(alternatives.items()):
            model_field, selected_id, other_object = config
            nonmatching = self.create_content(
                title=f"Nonmatching {request_field}",
                **{model_field: other_object},
            )
            client = self.create_client(f"filter-{index}")
            response = self.export(
                self.all_payload(**{request_field: [selected_id]}),
                client=client,
            )
            with self.subTest(request_field=request_field):
                self.assertEqual(response.status_code, 200)
                returned_ids = [item["id"] for item in response.json()["items"]]
                self.assertIn(matching.id, returned_ids)
                self.assertNotIn(nonmatching.id, returned_ids)

    def test_rules_filter_matches_any_selected_rule_and_does_not_duplicate_items(self):
        rule_one_only = self.create_content(title="Rule one")
        rule_one_only.rules.add(self.rule_one)
        both_rules = self.create_content(title="Both rules")
        both_rules.rules.set([self.rule_one, self.rule_two])
        no_rules = self.create_content(title="No rules")

        serializer = ContentExportRequestSerializer(
            data=self.all_payload(rules=[self.rule_one.id, self.rule_two.id])
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        queryset = ContentExportAPIView()._build_queryset(
            serializer.validated_data,
            self.client_a,
        )

        returned_ids = list(queryset.values_list("id", flat=True))
        self.assertEqual(returned_ids, [rule_one_only.id, both_rules.id])
        self.assertEqual(returned_ids.count(both_rules.id), 1)
        self.assertNotIn(no_rules.id, returned_ids)

    def test_null_related_fields_are_eligible_with_all_filters(self):
        content = self.create_content(
            language=None,
            topic=None,
            audience=None,
            goal=None,
            prompt_template=None,
        )

        response = self.export(self.all_payload(), client=self.client_a)

        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertEqual(item["id"], content.id)
        for field in ("language", "topic", "audience", "goal", "prompt_template"):
            self.assertIsNone(item[field])

    def test_successful_export_is_client_specific(self):
        content = self.create_content()

        first = self.export({"count": 1}, client=self.client_a)
        same_client = self.export({"count": 1}, client=self.client_a)
        other_client = self.export({"count": 1}, client=self.client_b)

        self.assertEqual(first.json()["exported"], 1)
        self.assertEqual(same_client.json()["exported"], 0)
        self.assertEqual(other_client.json()["exported"], 1)
        self.assertEqual(other_client.json()["items"][0]["id"], content.id)

    def test_pending_and_failed_ledgers_are_reused_as_successful_exports(self):
        pending_content = self.create_content(title="Pending ledger")
        failed_content = self.create_content(title="Failed ledger")
        pending_export = ContentExport.objects.create(
            content=pending_content,
            client=self.client_a,
            content_hash=pending_content.content_hash,
            status="pending",
            error_message="Pending error",
        )
        failed_export = ContentExport.objects.create(
            content=failed_content,
            client=self.client_a,
            content_hash=failed_content.content_hash,
            status="failed",
            error_message="Failed error",
        )

        response = self.export({"count": 2}, client=self.client_a)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()["items"]],
            [pending_content.id, failed_content.id],
        )
        pending_export.refresh_from_db()
        failed_export.refresh_from_db()
        for export in (pending_export, failed_export):
            self.assertEqual(export.status, "success")
            self.assertIsNotNone(export.exported_at)
            self.assertEqual(export.error_message, "")
        self.assertEqual(ContentExport.objects.count(), 2)

    def test_changed_content_hash_is_exportable_as_a_new_version(self):
        content = self.create_content(content_hash="version-one")
        first = self.export({"count": 1}, client=self.client_a)
        self.assertEqual(first.json()["exported"], 1)

        content.content_hash = "version-two"
        content.save(update_fields=["content_hash", "updated_at"])
        second = self.export({"count": 1}, client=self.client_a)

        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["exported"], 1)
        self.assertEqual(
            list(
                ContentExport.objects.filter(content=content)
                .order_by("created_at")
                .values_list("content_hash", flat=True)
            ),
            ["version-one", "version-two"],
        )

    def test_response_and_success_ledger_have_exact_current_structure(self):
        content = self.create_content(
            title="Exported title",
            prompt="Exported prompt",
            generated_content="Exported body",
            content_hash="exported-hash",
        )
        content.rules.set([self.rule_one, self.rule_two])

        response = self.export({"count": 1}, client=self.client_a)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(set(data), {"client", "requested", "exported", "remaining", "items"})
        self.assertEqual(data["client"], self.client_a.code)
        self.assertEqual(data["requested"], 1)
        self.assertEqual(data["exported"], 1)
        self.assertEqual(data["remaining"], 0)
        self.assertEqual(len(data["items"]), 1)
        item = data["items"][0]
        self.assertEqual(
            set(item),
            {
                "id", "title", "generated_content", "prompt", "content_hash",
                "language", "topic", "audience", "goal", "prompt_template",
                "rules", "status", "created_at", "updated_at",
            },
        )
        self.assertEqual(item["id"], content.id)
        self.assertEqual(item["language"], {"id": self.language.id, "name": "English", "code": "en"})
        self.assertEqual(item["topic"], {"id": self.topic.id, "name": "Technology"})
        self.assertEqual(item["audience"], {"id": self.audience.id, "name": "Developers"})
        self.assertEqual(item["goal"], {"id": self.goal.id, "name": "Education"})
        self.assertEqual(
            item["prompt_template"],
            {"id": self.template.id, "name": "Standard Template"},
        )
        self.assertEqual(
            item["rules"],
            [
                {"id": self.rule_one.id, "name": "Rule One"},
                {"id": self.rule_two.id, "name": "Rule Two"},
            ],
        )
        ledger = ContentExport.objects.get(content=content, client=self.client_a)
        self.assertEqual(ledger.status, "success")
        self.assertEqual(ledger.content_hash, content.content_hash)
        self.assertIsNotNone(ledger.exported_at)

    def test_fewer_available_empty_and_remaining_counts(self):
        first = self.create_content()
        second = self.create_content()

        partial = self.export({"count": 1}, client=self.client_a)
        fewer = self.export({"count": 5}, client=self.client_a)
        empty = self.export({"count": 5}, client=self.client_a)

        self.assertEqual(partial.json()["requested"], 1)
        self.assertEqual(partial.json()["exported"], 1)
        self.assertEqual(partial.json()["remaining"], 1)
        self.assertEqual(partial.json()["items"][0]["id"], first.id)
        self.assertEqual(fewer.json()["requested"], 5)
        self.assertEqual(fewer.json()["exported"], 1)
        self.assertEqual(fewer.json()["remaining"], 0)
        self.assertEqual(fewer.json()["items"][0]["id"], second.id)
        self.assertEqual(
            empty.json(),
            {
                "client": self.client_a.code,
                "requested": 5,
                "exported": 0,
                "remaining": 0,
                "items": [],
            },
        )


class ContentExportTransactionCharacterizationTests(
    ExportFixtureMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self):
        self.delivery_patcher = patch("contents.tasks.send_model_data_to_api.delay")
        self.delivery_patcher.start()
        self.addCleanup(self.delivery_patcher.stop)
        self.create_reference_data()
        self.client_record = self.create_client("transaction")
        self.api = APIClient()
        self.url = reverse("contents:api-content-export")

    def test_database_is_postgresql_for_transaction_characterization(self):
        self.assertEqual(connection.vendor, "postgresql")

    def test_unique_content_client_hash_constraint_raises_integrity_error(self):
        content = self.create_content()
        values = {
            "content": content,
            "client": self.client_record,
            "content_hash": content.content_hash,
            "status": "success",
            "exported_at": timezone.now(),
        }
        ContentExport.objects.create(**values)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ContentExport.objects.create(**values)

    def test_unexplained_collision_is_not_swallowed_and_outer_transaction_recovers(self):
        self.create_content()
        original_create = ContentExport.objects.create

        def create_then_collide(**kwargs):
            original_create(**kwargs)
            return original_create(**kwargs)

        with patch.object(
            ContentExport.objects,
            "create",
            side_effect=create_then_collide,
        ):
            with self.assertRaises(IntegrityError):
                self.api.post(
                    self.url,
                    {"count": 1},
                    format="json",
                    HTTP_X_API_KEY=self.client_record.api_key,
                )

        self.assertEqual(ContentExport.objects.count(), 0)

    def test_explicit_rules_endpoint_exports_on_postgresql(self):
        content = self.create_content()
        content.rules.add(self.rule_one)

        response = self.api.post(
            self.url,
            {
                "count": 1,
                "rules": [self.rule_one.id],
            },
            format="json",
            HTTP_X_API_KEY=self.client_record.api_key,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["exported"], 1)
        self.assertEqual(response.json()["items"][0]["id"], content.id)
        self.assertEqual(ContentExport.objects.count(), 1)
