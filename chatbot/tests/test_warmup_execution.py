"""Preparation scheduling contracts; all work/Redis/DB boundaries mocked."""
from datetime import date
from threading import BoundedSemaphore, Lock
from unittest import TestCase
from unittest.mock import Mock, patch

from fastapi import HTTPException
from chatbot import context_cache as cache
from chatbot import warmup
from chatbot.api import WarmupRequest, warmup_chatbot
from chatbot.firebase_student_context import load_unit_period_context


class QueuedExecutor:
    def __init__(self):
        self.jobs = []

    def submit(self, fn):
        self.jobs.append(fn)
        return object()


class WarmupExecutionTests(TestCase):
    def setUp(self):
        self.queue = QueuedExecutor()
        self.client = Mock()
        self.client.set.return_value = True
        self.revision = cache.ContextRevision(1, 34, 'cohort_34', 'shared', 'personal', 1)
        self.session = {'uid': 'synthetic-user', 'cohort': 'cohort_34'}
        patches = [
            patch.object(warmup, 'enabled', return_value=True),
            patch.object(warmup, 'redis_backoff_active', return_value=False),
            patch.object(warmup, '_pending', set()),
            patch.object(warmup, '_guard', Lock()),
            patch.object(warmup, '_capacity', BoundedSemaphore(warmup.MAX_PENDING)),
            patch.object(warmup, '_executor', return_value=self.queue),
            patch.object(warmup, 'read_revision', return_value=self.revision),
            patch.object(warmup, 'redis_client', return_value=self.client),
            patch.object(warmup, 'has_ready_context', return_value=True),
            patch.object(warmup, 'fill_context_cache', return_value=True),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_enqueue_is_nonblocking_and_same_request_is_singleflight(self):
        self.assertEqual(warmup.schedule_warmup(self.session), 'accepted')
        self.assertEqual(warmup.schedule_warmup(self.session), 'pending')
        self.assertEqual(len(self.queue.jobs), 1)
        warmup.read_revision.assert_not_called()
        self.queue.jobs[0]()
        self.assertFalse(warmup._pending)
        warmup.fill_context_cache.assert_not_called()
        self.client.eval.assert_called_once()

    def test_capacity_bounds_queued_jobs_before_any_db_work(self):
        for number in range(warmup.MAX_PENDING):
            self.assertEqual(warmup.schedule_warmup({'uid': f'synthetic-{number}'}), 'accepted')
        self.assertEqual(warmup.schedule_warmup({'uid': 'overflow'}), 'busy')
        self.assertEqual(len(self.queue.jobs), warmup.MAX_PENDING)
        warmup.read_revision.assert_not_called()

    def test_permission_failure_releases_capacity_without_loading_context(self):
        warmup.read_revision.side_effect = cache.RevisionDenied('synthetic denial')
        self.assertEqual(warmup.schedule_warmup(self.session), 'accepted')
        self.queue.jobs.pop()()
        self.assertFalse(warmup._pending)
        warmup.redis_client.assert_not_called()
        warmup.fill_context_cache.assert_not_called()
        self.assertEqual(warmup.schedule_warmup(self.session), 'accepted')

    def test_submit_failure_does_not_leak_capacity(self):
        with patch.object(warmup, '_executor', side_effect=RuntimeError('synthetic failure')):
            self.assertEqual(warmup.schedule_warmup(self.session), 'unavailable')
        self.assertFalse(warmup._pending)
        self.assertEqual(warmup.schedule_warmup(self.session), 'accepted')

    def test_distributed_duplicate_does_not_fill_or_release_another_lock(self):
        self.client.set.return_value = False
        warmup.schedule_warmup(self.session)
        self.queue.jobs.pop()()
        warmup.fill_context_cache.assert_not_called()
        self.client.eval.assert_not_called()
        self.assertFalse(warmup._pending)

    def test_only_missing_shapes_are_background_filled(self):
        warmup.has_ready_context.side_effect = [True, False]
        warmup.schedule_warmup(self.session, today=date(2026, 10, 12))
        self.queue.jobs.pop()()
        warmup.fill_context_cache.assert_called_once()
        kwargs = warmup.fill_context_cache.call_args.kwargs
        self.assertTrue(kwargs['include_attendance'])
        self.assertTrue(kwargs['include_record_details'])
        self.assertEqual(kwargs['today'], date(2026, 10, 12))
        self.assertEqual(kwargs['loader'].keywords['_connection_options'],
                         cache.read_connection_options())

    def test_redis_failure_opens_backoff_and_releases_capacity(self):
        warmup.redis_client.side_effect = TimeoutError('synthetic outage')
        with patch.object(warmup, 'mark_redis_failure') as failure:
            warmup.schedule_warmup(self.session)
            self.queue.jobs.pop()()
        failure.assert_called_once()
        self.assertFalse(warmup._pending)
        warmup.fill_context_cache.assert_not_called()

    def test_off_and_backoff_do_not_start_jobs(self):
        with patch.object(warmup, 'enabled', return_value=False):
            self.assertEqual(warmup.schedule_warmup(self.session), 'disabled')
        with patch.object(warmup, 'redis_backoff_active', return_value=True):
            self.assertEqual(warmup.schedule_warmup(self.session), 'unavailable')
        self.assertFalse(self.queue.jobs)


class WarmupEndpointAndFallbackTests(TestCase):
    def test_foreground_off_and_on_miss_keep_original_connection_options(self):
        session = {'uid': 'synthetic-user', 'cohort': 'cohort_34'}
        # A missing cohort terminates the source path before other DB queries;
        # the connection itself is mocked in both modes.
        for enabled in (False, True):
            with self.subTest(warmup_enabled=enabled), \
                 patch.object(cache, 'enabled', return_value=enabled), \
                 patch.object(cache, 'redis_backoff_active', return_value=False), \
                 patch.object(cache, '_read_ready_candidate', return_value=None), \
                 patch('chatbot.warmup.schedule_warmup', return_value='accepted'), \
                 patch('chatbot.firebase_student_context._cohort_ids', return_value=(None, 'cohort_34')), \
                 patch('chatbot.firebase_student_context._connect') as connect:
                result = load_unit_period_context(session, include_attendance=False)
                self.assertIn('unavailable_reason', result)
                connect.assert_called_once_with()

    def test_internal_token_is_required_before_scheduling(self):
        with patch('chatbot.api.valid_proxy_token', return_value=False), \
             patch('chatbot.warmup.schedule_warmup') as schedule:
            with self.assertRaises(HTTPException) as raised:
                warmup_chatbot(WarmupRequest(uid='synthetic-user'), 'wrong')
        self.assertEqual(raised.exception.status_code, 401)
        schedule.assert_not_called()

    def test_endpoint_enqueues_uid_only_without_db_model_or_loader_work(self):
        with patch('chatbot.api.valid_proxy_token', return_value=True), \
             patch('chatbot.context_cache.enabled', return_value=True), \
             patch('chatbot.context_cache.read_revision') as revision, \
             patch('chatbot.api._ready_chatbot') as bot, \
             patch('chatbot.warmup.schedule_warmup', return_value='accepted') as schedule:
            result = warmup_chatbot(WarmupRequest(uid='synthetic-user'), 'trusted')
        self.assertEqual(result, {'status': 'accepted'})
        schedule.assert_called_once_with({'uid': 'synthetic-user'})
        revision.assert_not_called()
        bot.assert_not_called()

    def test_endpoint_off_does_not_enqueue(self):
        with patch('chatbot.api.valid_proxy_token', return_value=True), \
             patch('chatbot.context_cache.enabled', return_value=False), \
             patch('chatbot.warmup.schedule_warmup') as schedule:
            self.assertEqual(warmup_chatbot(WarmupRequest(uid='synthetic-user'), 'trusted'),
                             {'status': 'disabled'})
        schedule.assert_not_called()

    def test_off_loader_is_exact_original_path(self):
        session = {'uid': 'synthetic-user', 'cohort': 'cohort_34'}
        original = {'synthetic': 'same-result'}
        with patch.object(cache, 'enabled', return_value=False), \
             patch.object(cache, 'load_cached_context') as cached, \
             patch('chatbot.firebase_student_context._load_unit_period_context', return_value=original) as loader:
            result = load_unit_period_context(session, include_attendance=False)
        self.assertIs(result, original)
        cached.assert_not_called()
        loader.assert_called_once_with(session, today=None, include_attendance=False,
                                       include_record_details=False)

    def test_known_redis_outage_skips_extra_fingerprint_and_never_reads_cache(self):
        loader = Mock(return_value={'synthetic': 'fresh-result'})
        with patch.object(cache, 'redis_backoff_active', return_value=True), \
             patch.object(cache, 'read_revision') as revision, \
             patch.object(cache, 'redis_client') as redis, \
             patch('chatbot.warmup.schedule_warmup', return_value='unavailable') as schedule:
            result = cache.load_cached_context({'uid': 'synthetic-user', 'cohort': 'cohort_34'}, loader=loader)
        self.assertEqual(result, {'synthetic': 'fresh-result'})
        loader.assert_called_once()
        revision.assert_not_called()
        redis.assert_not_called()
        schedule.assert_called_once()

    def test_failure_backoff_expires_without_saving_permission_or_context(self):
        with patch.object(cache, '_redis_retry_at', 0), \
             patch.object(cache.time, 'monotonic', return_value=100) as clock:
            cache.mark_redis_failure()
            clock.return_value = 101
            self.assertTrue(cache.redis_backoff_active())
            clock.return_value = 106
            self.assertFalse(cache.redis_backoff_active())
