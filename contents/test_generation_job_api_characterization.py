from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from rest_framework.test import APIClient

from contents.models import (
    Audience,
    ContentRule,
    ExternalClient,
    GenerationJob,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)
from contents.serializers import GenerationJobCreateSerializer


class GenerationJobAPICharacterizationTests(TestCase):
    job_fields = {
        "id",
        "count",
        "delay_seconds",
        "languages",
        "topics",
        "audiences",
        "goals",
        "rules",
        "prompt_templates",
        "generated_count",
        "skipped_count",
        "current_step",
        "progress_percent",
        "status",
        "error_message",
        "created_at",
        "updated_at",
    }

    @classmethod
    def setUpTestData(cls):
        cls.active_client = ExternalClient.objects.create(
            name="Generation client",
            code="generation-client",
            api_key="generation-api-key",
            is_active=True,
        )
        cls.inactive_client = ExternalClient.objects.create(
            name="Inactive generation client",
            code="inactive-generation-client",
            api_key="inactive-generation-api-key",
            is_active=False,
        )

        cls.language_one = Language.objects.create(name="English", code="en")
        cls.language_two = Language.objects.create(name="French", code="fr")
        cls.inactive_language = Language.objects.create(
            name="Inactive Language",
            code="xx",
            is_active=False,
        )
        cls.topic_one = Topic.objects.create(name="Technology")
        cls.topic_two = Topic.objects.create(name="Travel")
        cls.inactive_topic = Topic.objects.create(
            name="Inactive Topic",
            is_active=False,
        )
        cls.audience_one = Audience.objects.create(name="Developers")
        cls.audience_two = Audience.objects.create(name="Managers")
        cls.inactive_audience = Audience.objects.create(
            name="Inactive Audience",
            is_active=False,
        )
        cls.goal_one = Goal.objects.create(name="Education")
        cls.goal_two = Goal.objects.create(name="Promotion")
        cls.inactive_goal = Goal.objects.create(
            name="Inactive Goal",
            is_active=False,
        )
        cls.rule_one = ContentRule.objects.create(
            name="Rule One",
            prompt_text="Rule one text",
        )
        cls.rule_two = ContentRule.objects.create(
            name="Rule Two",
            prompt_text="Rule two text",
        )
        cls.inactive_rule = ContentRule.objects.create(
            name="Inactive Rule",
            prompt_text="Inactive text",
            is_active=False,
        )
        cls.template_one = PromptTemplate.objects.create(
            name="Template One",
            system_prompt="System one",
            user_prompt_template="User one",
        )
        cls.template_two = PromptTemplate.objects.create(
            name="Template Two",
            system_prompt="System two",
            user_prompt_template="User two",
        )
        cls.inactive_template = PromptTemplate.objects.create(
            name="Inactive Template",
            system_prompt="Inactive system",
            user_prompt_template="Inactive user",
            is_active=False,
        )

    def setUp(self):
        self.api = APIClient()
        self.list_url = reverse("contents:api-generation-job-list-create")

    def headers(self, api_key=None):
        if api_key is None:
            return {}
        return {"HTTP_X_API_KEY": api_key}

    def get_list(self, api_key=None):
        return self.api.get(self.list_url, **self.headers(api_key))

    def create_via_api(self, payload=None, api_key=None):
        if api_key is None:
            api_key = self.active_client.api_key
        return self.api.post(
            self.list_url,
            payload or {},
            format="json",
            **self.headers(api_key),
        )

    def get_detail(self, job_id, api_key=None):
        if api_key is None:
            api_key = self.active_client.api_key
        return self.api.get(
            reverse("contents:api-generation-job-detail", kwargs={"pk": job_id}),
            **self.headers(api_key),
        )

    def post_start(self, job_id, api_key=None):
        if api_key is None:
            api_key = self.active_client.api_key
        return self.api.post(
            reverse("contents:api-generation-job-start", kwargs={"job_id": job_id}),
            format="json",
            **self.headers(api_key),
        )

    def post_stop(self, job_id, api_key=None):
        if api_key is None:
            api_key = self.active_client.api_key
        return self.api.post(
            reverse("contents:api-generation-job-stop", kwargs={"job_id": job_id}),
            format="json",
            **self.headers(api_key),
        )

    def explicit_payload(self, **overrides):
        payload = {
            "count": 10,
            "delay_seconds": 2.5,
            "languages": [self.language_two.id, self.language_one.id],
            "topics": [self.topic_two.id, self.topic_one.id],
            "audiences": [self.audience_two.id, self.audience_one.id],
            "goals": [self.goal_two.id, self.goal_one.id],
            "rules": [self.rule_two.id, self.rule_one.id],
            "prompt_templates": [self.template_two.id, self.template_one.id],
        }
        payload.update(overrides)
        return payload

    def assert_forbidden(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {"detail": "Authentication credentials were not provided."},
        )

    def test_exact_generation_job_routes_and_names(self):
        routes = (
            (
                "contents:api-generation-job-list-create",
                {},
                "/api/v1/generation-jobs/",
                "api-generation-job-list-create",
            ),
            (
                "contents:api-generation-job-detail",
                {"pk": 17},
                "/api/v1/generation-jobs/17/",
                "api-generation-job-detail",
            ),
            (
                "contents:api-generation-job-start",
                {"job_id": 17},
                "/api/v1/generation-jobs/17/start/",
                "api-generation-job-start",
            ),
            (
                "contents:api-generation-job-stop",
                {"job_id": 17},
                "/api/v1/generation-jobs/17/stop/",
                "api-generation-job-stop",
            ),
        )
        for name, kwargs, expected_path, expected_url_name in routes:
            with self.subTest(name=name):
                path = reverse(name, kwargs=kwargs)
                self.assertEqual(path, expected_path)
                match = resolve(path)
                self.assertEqual(match.namespace, "contents")
                self.assertEqual(match.url_name, expected_url_name)

    def test_generation_job_import_compatibility(self):
        from contents.serializers import (
            GenerationJobActionResponseSerializer,
            GenerationJobCreateSerializer,
            GenerationJobSerializer,
        )
        from contents.views import (
            GenerationJobDetailAPIView,
            GenerationJobListCreateAPIView,
            GenerationJobStartAPIView,
            GenerationJobStopAPIView,
        )

        self.assertTrue(
            all(
                (
                    GenerationJobActionResponseSerializer,
                    GenerationJobCreateSerializer,
                    GenerationJobSerializer,
                    GenerationJobDetailAPIView,
                    GenerationJobListCreateAPIView,
                    GenerationJobStartAPIView,
                    GenerationJobStopAPIView,
                )
            )
        )

    def test_all_generation_job_endpoints_reject_invalid_authentication(self):
        job = GenerationJob.objects.create()
        requests = (
            lambda key: self.get_list(key),
            lambda key: self.create_via_api({}, key),
            lambda key: self.get_detail(job.id, key),
            lambda key: self.post_start(job.id, key),
            lambda key: self.post_stop(job.id, key),
        )
        keys = ("", "invalid-api-key", self.inactive_client.api_key)

        for request_call in requests:
            for key in keys:
                with self.subTest(request=request_call, key=key):
                    response = request_call(key)
                    self.assert_forbidden(response)

    def test_list_exact_fields_newest_first_progress_and_selections(self):
        explicit = GenerationJob.objects.create(
            external_client=self.active_client,
            count=8,
            delay_seconds=2.5,
            generated_count=3,
            skipped_count=1,
            current_step=4,
            status="running",
            error_message="Current warning",
        )
        explicit.languages.set([self.language_two, self.language_one])
        explicit.topics.set([self.topic_two, self.topic_one])
        explicit.audiences.set([self.audience_two, self.audience_one])
        explicit.goals.set([self.goal_two, self.goal_one])
        explicit.rules.set([self.rule_two, self.rule_one])
        explicit.prompt_templates.set([self.template_two, self.template_one])
        all_job = GenerationJob.objects.create(
            external_client=self.active_client,
            count=0,
            use_all_languages=True,
            use_all_topics=True,
            use_all_audiences=True,
            use_all_goals=True,
            use_all_rules=True,
            use_all_prompt_templates=True,
        )

        response = self.get_list(self.active_client.api_key)

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], [all_job.id, explicit.id])
        for item in response.json():
            self.assertEqual(set(item), self.job_fields)
        all_item, explicit_item = response.json()
        for field in (
            "languages", "topics", "audiences", "goals", "rules", "prompt_templates"
        ):
            self.assertEqual(all_item[field], "all")
        self.assertEqual(all_item["progress_percent"], 0)
        self.assertEqual(explicit_item["progress_percent"], 37)
        self.assertEqual(explicit_item["languages"], [self.language_one.id, self.language_two.id])
        self.assertEqual(explicit_item["topics"], [self.topic_one.id, self.topic_two.id])
        self.assertEqual(explicit_item["audiences"], [self.audience_one.id, self.audience_two.id])
        self.assertEqual(explicit_item["goals"], [self.goal_one.id, self.goal_two.id])
        self.assertEqual(explicit_item["rules"], [self.rule_one.id, self.rule_two.id])
        self.assertEqual(
            explicit_item["prompt_templates"],
            [self.template_one.id, self.template_two.id],
        )

    def test_list_empty_and_inactive_explicit_relations_are_returned_as_empty(self):
        job = GenerationJob.objects.create(external_client=self.active_client)
        job.languages.add(self.inactive_language)
        job.topics.add(self.inactive_topic)
        job.audiences.add(self.inactive_audience)
        job.goals.add(self.inactive_goal)
        job.rules.add(self.inactive_rule)
        job.prompt_templates.add(self.inactive_template)

        response = self.get_list(self.active_client.api_key)

        self.assertEqual(response.status_code, 200)
        item = response.json()[0]
        for field in (
            "languages", "topics", "audiences", "goals", "rules", "prompt_templates"
        ):
            self.assertEqual(item[field], [])

    def test_list_limits_results_to_100_newest_jobs(self):
        jobs = [
            GenerationJob.objects.create(
                count=index + 1,
                external_client=self.active_client,
            )
            for index in range(101)
        ]

        response = self.get_list(self.active_client.api_key)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 100)
        self.assertEqual(
            [item["id"] for item in response.json()],
            [job.id for job in reversed(jobs[1:])],
        )

    def test_list_currently_performs_six_selection_queries_per_explicit_job(self):
        GenerationJob.objects.create(external_client=self.active_client)
        GenerationJob.objects.create(external_client=self.active_client)

        with CaptureQueriesContext(connection) as queries:
            response = self.get_list(self.active_client.api_key)

        self.assertEqual(response.status_code, 200)
        selection_queries = [
            query["sql"]
            for query in queries.captured_queries
            if "contents_generationjob_" in query["sql"]
        ]
        job_queries = [
            query["sql"]
            for query in queries.captured_queries
            if 'FROM "contents_generationjob"' in query["sql"]
            and "contents_generationjob_" not in query["sql"]
        ]
        self.assertEqual(len(job_queries), 1)
        self.assertEqual(len(selection_queries), 12)

    def test_create_serializer_exact_defaults(self):
        serializer = GenerationJobCreateSerializer(data={})

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["count"], 1)
        self.assertEqual(serializer.validated_data["delay_seconds"], 1.0)
        for field in (
            "languages", "topics", "audiences", "goals", "rules", "prompt_templates"
        ):
            self.assertEqual(serializer.validated_data[field], "all")

    def test_create_count_and_delay_exact_validation_limits(self):
        invalid_cases = (
            ({"count": 0}, {"count": ["Ensure this value is greater than or equal to 1."]}),
            (
                {"count": 10001},
                {"count": ["Ensure this value is less than or equal to 10000."]},
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
        for payload, expected in invalid_cases:
            with self.subTest(payload=payload):
                response = self.create_via_api(payload)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), expected)

        for payload in ({"count": 1}, {"count": 10000}, {"delay_seconds": 0}, {"delay_seconds": 60}):
            serializer = GenerationJobCreateSerializer(data=payload)
            with self.subTest(payload=payload):
                self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_create_normalizes_duplicate_and_numeric_string_ids(self):
        payload = self.explicit_payload(
            languages=[str(self.language_two.id), self.language_one.id, self.language_two.id],
            rules=[str(self.rule_two.id), self.rule_one.id, self.rule_two.id],
        )

        with patch("contents.views.run_generation_job_task.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.create_via_api(payload)

        self.assertEqual(response.status_code, 201)
        job = GenerationJob.objects.get()
        self.assertEqual(list(job.languages.order_by("id")), [self.language_one, self.language_two])
        self.assertEqual(list(job.rules.order_by("id")), [self.rule_one, self.rule_two])
        delay.assert_called_once_with(job.id)

    def test_create_all_sets_exact_flags_and_initial_state_after_commit(self):
        with patch("contents.views.run_generation_job_task.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.create_via_api({})
                delay.assert_not_called()

        self.assertEqual(response.status_code, 201)
        job = GenerationJob.objects.get()
        delay.assert_called_once_with(job.id)
        self.assertEqual(response.json()["message"], f"Generation job #{job.id} created and started.")
        self.assertEqual(set(response.json()), {"message", "job"})
        self.assertEqual(set(response.json()["job"]), self.job_fields)
        self.assertEqual(job.count, 1)
        self.assertEqual(job.delay_seconds, 1.0)
        self.assertEqual(job.status, "pending")
        self.assertFalse(job.should_stop)
        self.assertEqual(job.error_message, "")
        self.assertEqual(job.generated_count, 0)
        self.assertEqual(job.skipped_count, 0)
        self.assertEqual(job.current_step, 0)
        for field in (
            "use_all_languages", "use_all_topics", "use_all_audiences",
            "use_all_goals", "use_all_rules", "use_all_prompt_templates",
        ):
            self.assertTrue(getattr(job, field))

    def test_create_explicit_sets_flags_relations_and_exact_response(self):
        with patch("contents.views.run_generation_job_task.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.create_via_api(self.explicit_payload())

        self.assertEqual(response.status_code, 201)
        job = GenerationJob.objects.get()
        delay.assert_called_once_with(job.id)
        for field in (
            "use_all_languages", "use_all_topics", "use_all_audiences",
            "use_all_goals", "use_all_rules", "use_all_prompt_templates",
        ):
            self.assertFalse(getattr(job, field))
        relations = (
            (job.languages, [self.language_one.id, self.language_two.id]),
            (job.topics, [self.topic_one.id, self.topic_two.id]),
            (job.audiences, [self.audience_one.id, self.audience_two.id]),
            (job.goals, [self.goal_one.id, self.goal_two.id]),
            (job.rules, [self.rule_one.id, self.rule_two.id]),
            (job.prompt_templates, [self.template_one.id, self.template_two.id]),
        )
        for relation, expected_ids in relations:
            self.assertEqual(list(relation.order_by("id").values_list("id", flat=True)), expected_ids)
        self.assertEqual(response.json()["job"]["languages"], [self.language_one.id, self.language_two.id])

    def test_create_rules_empty_is_allowed_but_required_selections_are_not(self):
        with patch("contents.views.run_generation_job_task.delay"):
            response = self.create_via_api(self.explicit_payload(rules=[]))
        self.assertEqual(response.status_code, 201)
        job = GenerationJob.objects.get()
        self.assertFalse(job.use_all_rules)
        self.assertEqual(list(job.rules.all()), [])

        required_fields = (
            "languages", "topics", "audiences", "goals", "prompt_templates"
        )
        for field in required_fields:
            GenerationJob.objects.all().delete()
            with self.subTest(field=field):
                response = self.create_via_api(self.explicit_payload(**{field: []}))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json(),
                    {
                        field: [
                            f"{field} cannot be empty. Use \"all\" or provide at least one active ID."
                        ]
                    },
                )

    def test_create_inactive_and_nonexistent_selection_errors_are_exact(self):
        cases = (
            ("languages", self.inactive_language.id),
            ("topics", self.inactive_topic.id),
            ("audiences", self.inactive_audience.id),
            ("goals", self.inactive_goal.id),
            ("rules", self.inactive_rule.id),
            ("prompt_templates", self.inactive_template.id),
            ("prompt_templates", 999999),
        )
        for field, item_id in cases:
            with self.subTest(field=field, item_id=item_id):
                response = self.create_via_api(self.explicit_payload(**{field: [item_id]}))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json(),
                    {field: [f"These IDs do not exist or are inactive: {item_id}"]},
                )

    def test_detail_exact_fields_all_explicit_progress_and_not_found(self):
        all_job = GenerationJob.objects.create(
            external_client=self.active_client,
            count=4,
            generated_count=5,
            use_all_languages=True,
            use_all_topics=True,
            use_all_audiences=True,
            use_all_goals=True,
            use_all_rules=True,
            use_all_prompt_templates=True,
        )
        explicit = GenerationJob.objects.create(
            count=3,
            generated_count=1,
            external_client=self.active_client,
        )
        explicit.languages.add(self.language_one)
        explicit.rules.add(self.rule_one)

        all_response = self.get_detail(all_job.id)
        explicit_response = self.get_detail(explicit.id)
        missing_response = self.get_detail(999999)

        self.assertEqual(all_response.status_code, 200)
        self.assertEqual(set(all_response.json()), self.job_fields)
        self.assertEqual(all_response.json()["progress_percent"], 100)
        self.assertEqual(all_response.json()["languages"], "all")
        self.assertEqual(explicit_response.status_code, 200)
        self.assertEqual(explicit_response.json()["progress_percent"], 33)
        self.assertEqual(explicit_response.json()["languages"], [self.language_one.id])
        self.assertEqual(explicit_response.json()["topics"], [])
        self.assertEqual(explicit_response.json()["rules"], [self.rule_one.id])
        self.assertEqual(missing_response.status_code, 404)
        self.assertEqual(missing_response.json(), {"detail": "No GenerationJob matches the given query."})

    def test_detail_and_action_authentication_are_exact(self):
        job = GenerationJob.objects.create()
        for request_call in (
            lambda key: self.get_detail(job.id, key),
            lambda key: self.post_start(job.id, key),
            lambda key: self.post_stop(job.id, key),
        ):
            for key in ("", "invalid", self.inactive_client.api_key):
                response = request_call(key)
                self.assert_forbidden(response)

    def test_start_allowed_states_preserve_progress_and_dispatch_after_commit(self):
        cases = (
            ("pending", 0, 0, 0, "started"),
            ("stopped", 2, 1, 3, "resumed"),
            ("failed", 1, 0, 1, "resumed"),
            ("completed", 1, 0, 1, "resumed"),
        )
        for index, (initial_status, generated, skipped, step, action) in enumerate(cases):
            job = GenerationJob.objects.create(
                external_client=self.active_client,
                count=10,
                status=initial_status,
                generated_count=generated,
                skipped_count=skipped,
                current_step=step,
                should_stop=True,
                error_message="Previous error",
            )
            with self.subTest(initial_status=initial_status):
                with patch("contents.views.run_generation_job_task.delay") as delay:
                    with self.captureOnCommitCallbacks(execute=True):
                        response = self.post_start(job.id)
                        delay.assert_not_called()
                self.assertEqual(response.status_code, 200)
                delay.assert_called_once_with(job.id)
                job.refresh_from_db()
                self.assertEqual(job.status, "running")
                self.assertFalse(job.should_stop)
                self.assertEqual(job.error_message, "")
                self.assertEqual(job.generated_count, generated)
                self.assertEqual(job.skipped_count, skipped)
                self.assertEqual(job.current_step, step)
                self.assertEqual(
                    response.json()["message"],
                    f"Generation job #{job.id} {action}.",
                )

    def test_start_rejects_running_and_target_reached_without_dispatch(self):
        running = GenerationJob.objects.create(
            count=10,
            status="running",
            external_client=self.active_client,
        )
        reached = GenerationJob.objects.create(
            external_client=self.active_client,
            count=10,
            generated_count=10,
            status="stopped",
        )
        completed = GenerationJob.objects.create(
            external_client=self.active_client,
            count=10,
            generated_count=10,
            status="completed",
        )

        with patch("contents.views.run_generation_job_task.delay") as delay:
            running_response = self.post_start(running.id)
            reached_response = self.post_start(reached.id)
            completed_response = self.post_start(completed.id)

        delay.assert_not_called()
        self.assertEqual(running_response.status_code, 400)
        self.assertEqual(
            running_response.json(),
            {"detail": f"Job #{running.id} is already running."},
        )
        for job, response in ((reached, reached_response), (completed, completed_response)):
            self.assertEqual(response.status_code, 400)
            self.assertEqual(
                response.json(),
                {"detail": f"Job #{job.id} is already completed (10/10)."},
            )

    def test_start_and_stop_missing_jobs_return_exact_404(self):
        start = self.post_start(999999)
        stop = self.post_stop(999999)
        self.assertEqual(start.status_code, 404)
        self.assertEqual(
            start.json(),
            {"detail": "No GenerationJob matches the given query."},
        )
        self.assertEqual(stop.status_code, 404)
        self.assertEqual(
            stop.json(),
            {"detail": "No GenerationJob matches the given query."},
        )

    def test_stop_pending_and_running_jobs_sets_exact_state_without_dispatch(self):
        for initial_status in ("pending", "running"):
            job = GenerationJob.objects.create(
                external_client=self.active_client,
                count=10,
                status=initial_status,
                should_stop=False,
                error_message="",
                generated_count=2,
                skipped_count=1,
                current_step=3,
            )
            with self.subTest(initial_status=initial_status):
                with patch("contents.views.run_generation_job_task.delay") as delay:
                    response = self.post_stop(job.id)
                delay.assert_not_called()
                self.assertEqual(response.status_code, 200)
                job.refresh_from_db()
                self.assertTrue(job.should_stop)
                self.assertEqual(job.status, "stopped")
                self.assertEqual(job.error_message, "Job stopped by external API.")
                self.assertEqual(job.generated_count, 2)
                self.assertEqual(job.skipped_count, 1)
                self.assertEqual(job.current_step, 3)
                self.assertEqual(
                    response.json()["message"],
                    f"Generation job #{job.id} stopped.",
                )

    def test_stop_rejects_stopped_completed_and_failed_without_changes(self):
        for initial_status in ("stopped", "completed", "failed"):
            job = GenerationJob.objects.create(
                external_client=self.active_client,
                status=initial_status,
                should_stop=False,
                error_message="Existing error",
            )
            with self.subTest(initial_status=initial_status):
                with patch("contents.views.run_generation_job_task.delay") as delay:
                    response = self.post_stop(job.id)
                delay.assert_not_called()
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json(),
                    {"detail": f"Job #{job.id} is not pending or running."},
                )
                job.refresh_from_db()
                self.assertEqual(job.status, initial_status)
                self.assertFalse(job.should_stop)
                self.assertEqual(job.error_message, "Existing error")
