import random
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, SimpleTestCase

from contents.core_services.dataset_manager import should_run_dataset_refill
from contents.core_services.generation_outcome import handle_generation_failure
from contents.core_services.intelligence_scheduler import maybe_run_intelligence_optimization
from contents.core_services.scoring import calculate_generation_score
from contents.core_services.selector import intelligent_choice, intelligent_generation_choice, weighted_choice
from contents.models import Audience, DatasetPerformance, GenerationJob, GenerationPattern, Goal, Language, PromptTemplate, Topic


class GenerationSelectionEfficiencyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.languages = [Language.objects.create(name='English', code='en')]
        cls.templates = [PromptTemplate.objects.create(name='Template', system_prompt='System', user_prompt_template='User')]
        cls.topics = [Topic.objects.create(name=f'Topic {i}', weight=i + 1) for i in range(4)]
        cls.audiences = [Audience.objects.create(name=f'Audience {i}', weight=i + 1) for i in range(3)]
        cls.goals = [Goal.objects.create(name=f'Goal {i}', weight=i + 1) for i in range(3)]
        for kind, items in [('topic', cls.topics), ('audience', cls.audiences), ('goal', cls.goals)]:
            for i, item in enumerate(items[:2]):
                DatasetPerformance.objects.create(item_type=kind, item_id=item.pk, quality_score=[0, 65][i])
        for quality in [10, 95]:
            GenerationPattern.objects.create(language=cls.languages[0], topic=cls.topics[0],
                audience=cls.audiences[0], goal=cls.goals[0], prompt_template=cls.templates[0],
                quality_score=quality, confidence=70)

    def kwargs(self):
        return dict(languages=self.languages, topics=self.topics, audiences=self.audiences,
                    goals=self.goals, prompt_templates=self.templates)

    def legacy_selection(self, sample_size=25):
        candidates, scores = [], []
        for _ in range(sample_size):
            candidate = (weighted_choice(self.languages), intelligent_choice(self.topics),
                         intelligent_choice(self.audiences), intelligent_choice(self.goals),
                         weighted_choice(self.templates))
            candidates.append(candidate)
            scores.append(calculate_generation_score(*candidate))
        return random.choices(candidates, weights=scores, k=1)[0]

    def test_selection_preserves_existing_weighted_behavior(self):
        for seed in range(8):
            with self.subTest(seed=seed):
                random.seed(seed)
                expected = self.legacy_selection()
                random.seed(seed)
                actual = intelligent_generation_choice(**self.kwargs())
                self.assertEqual(actual, expected)

    def test_query_count_stays_bounded_as_pool_grows(self):
        with self.assertNumQueries(2):
            intelligent_generation_choice(**self.kwargs())
        topics = self.topics + Topic.objects.bulk_create([
            Topic(name=f'Additional topic {i}') for i in range(150)
        ])
        args = self.kwargs()
        args['topics'] = topics
        with self.assertNumQueries(2):
            choice = intelligent_generation_choice(**args)
        self.assertIn(choice[1], topics)

    def test_quality_changes_are_visible_on_next_selection(self):
        args = self.kwargs()
        with patch('contents.core_services.selector.random.choices', side_effect=lambda items, **kw: [items[0]]) as choose:
            intelligent_generation_choice(**args)
            old_weights = list(choose.call_args_list[1].kwargs['weights'])
            DatasetPerformance.objects.filter(item_type='topic', item_id=self.topics[0].pk).update(quality_score=100)
            choose.reset_mock()
            intelligent_generation_choice(**args)
            new_weights = choose.call_args_list[1].kwargs['weights']
        self.assertGreater(new_weights[0], old_weights[0])


class GenerationMaintenanceEfficiencyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    @patch('contents.core_services.intelligence_scheduler.optimize_dataset_weights')
    def test_weight_updates_run_once_per_fifty_events(self, optimize):
        for _ in range(49):
            self.assertFalse(maybe_run_intelligence_optimization())
        optimize.assert_not_called()
        self.assertTrue(maybe_run_intelligence_optimization())
        for _ in range(50):
            maybe_run_intelligence_optimization()
        self.assertEqual(optimize.call_count, 2)

    def test_refill_uses_duplicate_count_and_reserves_once(self):
        settings = SimpleNamespace(auto_refill_enabled=True, auto_refill_skip_threshold=50)
        job = SimpleNamespace(id=999, skipped_count=50, duplicate_count=0)
        self.assertFalse(should_run_dataset_refill(job, settings))
        job.skipped_count, job.duplicate_count = 70, 50
        self.assertTrue(should_run_dataset_refill(job, settings))
        self.assertFalse(should_run_dataset_refill(job, settings))

    @patch('contents.core_services.generation_outcome.maybe_run_intelligence_optimization')
    @patch('contents.core_services.generation_outcome.record_generation_event')
    @patch('contents.core_services.generation_outcome.run_dataset_refill')
    def test_format_and_api_errors_do_not_purchase_new_datasets(self, refill, _event, _optimize):
        job = GenerationJob.objects.create(generation_type='standard')
        for kind in ['failed', 'empty']:
            handle_generation_failure(job, None, 'error', None, None, None, None, None,
                                      'Invalid output', failure_kind=kind)
        refill.assert_not_called()
        handle_generation_failure(job, None, 'duplicate', None, None, None, None, None,
                                  'Duplicate', failure_kind='duplicate')
        refill.assert_called_once()
