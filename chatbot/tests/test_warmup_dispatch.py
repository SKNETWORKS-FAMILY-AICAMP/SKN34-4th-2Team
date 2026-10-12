"""Django dispatch helper in isolation: no settings, DB or upstream requests."""
import importlib.util
import os
from pathlib import Path
from threading import BoundedSemaphore, Lock
from unittest import TestCase
from unittest.mock import Mock, patch


_path = Path(__file__).resolve().parents[2] / 'lms_api/lms/chatbot_warmup.py'
_spec = importlib.util.spec_from_file_location('_warmup_dispatch_under_test', _path)
dispatch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dispatch)


class LoginWarmupDispatchTests(TestCase):
    def setUp(self):
        self.jobs = []
        self.executor = Mock()
        self.executor.submit.side_effect = lambda job: self.jobs.append(job)
        self.user = {'firebase_uid': 'synthetic-user', 'role': 'student',
                     'is_active': True, 'must_change_password': False}
        patches = [
            patch.dict(os.environ, {'LMS_CHATBOT_WARMUP': '1', 'CHATBOT_URL': 'http://ai.invalid',
                                    'LMS_AI_SHARED_TOKEN': 'synthetic-token'}),
            patch.object(dispatch, '_executor', return_value=self.executor),
            patch.object(dispatch, '_capacity', BoundedSemaphore(dispatch.MAX_PENDING)),
            patch.object(dispatch, '_pending', set()), patch.object(dispatch, '_recent', {}),
            patch.object(dispatch, '_guard', Lock()),
            patch.object(dispatch.time, 'monotonic', return_value=100),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_login_only_reserves_work_and_dispatches_uid_only_in_worker(self):
        with patch.object(dispatch.urllib.request, 'urlopen') as upstream:
            self.assertTrue(dispatch.dispatch_login_warmup(self.user))
            upstream.assert_not_called()
            self.jobs.pop()()
        request = upstream.call_args.args[0]
        self.assertEqual(request.data, b'{"uid": "synthetic-user"}')
        self.assertTrue(request.full_url.endswith('/api/v1/student-chatbot/warmup'))
        self.assertEqual(upstream.call_args.kwargs['timeout'], dispatch.DISPATCH_TIMEOUT_SECONDS)

    def test_forced_password_inactive_and_nonstudent_never_enqueue(self):
        for values in ({'must_change_password': True}, {'is_active': False}, {'role': 'admin'}):
            self.assertFalse(dispatch.dispatch_login_warmup({**self.user, **values}))
        self.assertFalse(self.jobs)

    def test_off_or_missing_internal_configuration_never_enqueues(self):
        for values in ({'LMS_CHATBOT_WARMUP': '0'}, {'CHATBOT_URL': ''}, {'LMS_AI_SHARED_TOKEN': ''}):
            with patch.dict(os.environ, values):
                self.assertFalse(dispatch.dispatch_login_warmup(self.user))
        self.assertFalse(self.jobs)

    def test_duplicate_cooldown_and_capacity_bound(self):
        self.assertTrue(dispatch.dispatch_login_warmup(self.user))
        self.assertFalse(dispatch.dispatch_login_warmup(self.user))
        with patch.object(dispatch.urllib.request, 'urlopen'):
            self.jobs.pop()()
        self.assertFalse(dispatch.dispatch_login_warmup(self.user))
        dispatch.time.monotonic.return_value = 116
        for number in range(dispatch.MAX_PENDING):
            self.assertTrue(dispatch.dispatch_login_warmup({**self.user, 'firebase_uid': f'next-{number}'}))
        self.assertFalse(dispatch.dispatch_login_warmup({**self.user, 'firebase_uid': 'overflow'}))
        self.assertEqual(len(self.jobs), dispatch.MAX_PENDING)

    def test_dispatch_error_is_isolated_and_releases_capacity(self):
        dispatch.dispatch_login_warmup(self.user)
        with patch.object(dispatch.urllib.request, 'urlopen', side_effect=TimeoutError('synthetic outage')):
            self.jobs.pop()()
        self.assertFalse(dispatch._pending)
        self.assertFalse(dispatch.dispatch_login_warmup(self.user))  # cooldown even after failure
        dispatch.time.monotonic.return_value = 116
        self.assertTrue(dispatch.dispatch_login_warmup(self.user))

    def test_submit_error_releases_capacity_and_allows_retry(self):
        self.executor.submit.side_effect = RuntimeError('synthetic submit failure')
        self.assertFalse(dispatch.dispatch_login_warmup(self.user))
        self.assertFalse(dispatch._pending)
        self.executor.submit.side_effect = lambda job: self.jobs.append(job)
        self.assertTrue(dispatch.dispatch_login_warmup(self.user))
