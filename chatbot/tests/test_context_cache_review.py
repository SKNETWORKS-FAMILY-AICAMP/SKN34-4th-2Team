"""Independent review: prompt equivalence and cross-user cache isolation."""
from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta
from unittest import TestCase
from unittest.mock import Mock, patch

from chatbot import context_cache as cache
from chatbot.context_builder import build_answer_context
from chatbot.tests.context_optimization_fixtures import fixture


class MemoryRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, **kwargs):
        self.values[key] = value
        return True


class ContextCacheReviewTests(TestCase):
    day = date(2026, 10, 10)

    def setUp(self):
        self.client = MemoryRedis()
        self.session = {'uid': 'review-a', 'cohort': 'cohort_34'}
        self.revision = cache.ContextRevision(1, 34, 'cohort_34', 'source-v1', 'attendance-a', 1)
        self.patchers = [
            patch.object(cache, 'redis_client', return_value=self.client),
            patch.object(cache, 'redis_backoff_active', return_value=False),
            patch('chatbot.warmup.schedule_warmup', return_value='accepted'),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def fill(self, context, session=None, personal=True):
        return cache.fill_context_cache(session or self.session,
            loader=Mock(return_value=deepcopy(context)), today=self.day,
            include_attendance=personal, include_record_details=personal)

    def read(self, loader, session=None, personal=True, day=None):
        return cache.load_cached_context(session or self.session, loader=loader,
            today=day or self.day, include_attendance=personal,
            include_record_details=personal)

    def test_80_90_and_missing_records_preserve_entire_answer_context(self):
        for threshold, conversion, missing in [(80, 3, False), (90, 2, False), (80, 3, True)]:
            with self.subTest(threshold=threshold, missing=missing):
                state = fixture(threshold, conversion, missing)
                session = {'uid': 'review-a', 'cohort': state['cohort']}
                revision = replace(self.revision, cohort_code=state['cohort'],
                    shared_revision=f'policy-{threshold}-{missing}')
                expected = build_answer_context(unit_period_context=state['unit_period_context'],
                    student_context=state['student_context'], documents=state['documents'],
                    mode='legacy', cohort=state['cohort']).text
                actual = deepcopy(state)
                with patch.object(cache, 'read_revision', return_value=revision):
                    for personal in (False, True):
                        source = (state['student_context']['data']['student_attendance']['unit_period_context']
                                  if personal else state['unit_period_context'])
                        self.assertTrue(self.fill(source, session=session, personal=personal))
                        loader = Mock(side_effect=AssertionError('Hit must not recalculate'))
                        value = self.read(loader, session=session, personal=personal)
                        self.assertEqual(value, source)
                        if personal:
                            actual['student_context']['data']['student_attendance']['unit_period_context'] = value
                        else:
                            actual['unit_period_context'] = value
                observed = build_answer_context(unit_period_context=actual['unit_period_context'],
                    student_context=actual['student_context'], documents=actual['documents'],
                    mode='legacy', cohort=actual['cohort']).text
                self.assertEqual(expected, observed)

    def test_shared_reused_across_students_but_personal_pointer_cannot_be_swapped(self):
        state = fixture()
        shared = state['unit_period_context']
        private = state['student_context']['data']['student_attendance']['unit_period_context']
        other = {'uid': 'review-b', 'cohort': 'cohort_34'}
        with patch.object(cache, 'read_revision', return_value=self.revision):
            self.assertTrue(self.fill(shared, personal=False))
            self.assertTrue(self.fill(private))
        with patch.object(cache, 'read_revision', return_value=replace(self.revision, user_id=2, attendance_revision='attendance-b')):
            self.assertEqual(self.read(Mock(side_effect=AssertionError('shared miss')), session=other, personal=False), shared)
            # Even an accidentally copied alias cannot authorize another user's body.
            a = cache.ready_pointer_key(self.session, self.day, include_attendance=True, include_record_details=True)
            b = cache.ready_pointer_key(other, self.day, include_attendance=True, include_record_details=True)
            self.client.values[b] = self.client.values[a]
            loader = Mock(return_value={'fresh-student-b': True})
            self.assertEqual(self.read(loader, session=other), {'fresh-student-b': True})
            loader.assert_called_once()
        shared_alias = cache.ready_pointer_key(self.session, self.day, include_attendance=False, include_record_details=False)
        self.assertNotIn(b'user_id', self.client.values[shared_alias])
        self.assertNotIn(b'attendance_revision', self.client.values[shared_alias])

    def test_revision_race_never_publishes_and_revoked_hit_never_falls_back(self):
        source = fixture()['unit_period_context']
        with patch.object(cache, 'read_revision', side_effect=[self.revision, replace(self.revision, shared_revision='changed')]):
            self.assertFalse(self.fill(source, personal=False))
        self.assertEqual(self.client.values, {})
        with patch.object(cache, 'read_revision', return_value=self.revision):
            self.assertTrue(self.fill(source, personal=False))
        loader = Mock(side_effect=AssertionError('Revoked user must not read'))
        with patch.object(cache, 'read_revision', side_effect=cache.RevisionDenied('revoked')):
            self.assertIn('unavailable_reason', self.read(loader, personal=False))
        loader.assert_not_called()

    def test_hit_copy_isolation_and_new_day_miss_do_not_add_database_work(self):
        source = fixture()['unit_period_context']
        with patch.object(cache, 'read_revision', return_value=self.revision):
            self.assertTrue(self.fill(source, personal=False))
            result = self.read(Mock(side_effect=AssertionError('unexpected miss')), personal=False)
            result['policy_calculation']['status'] = 'tampered-client-copy'
            again = self.read(Mock(side_effect=AssertionError('unexpected miss')), personal=False)
            self.assertEqual(again, source)
        with patch.object(cache, 'read_revision', side_effect=AssertionError('Empty cache adds no revision query')):
            loader = Mock(return_value={'new-day': True})
            self.assertEqual(self.read(loader, personal=False, day=self.day + timedelta(days=1)), {'new-day': True})
            loader.assert_called_once()
