"""Missing/ambiguous active pointers must never reuse or publish cache entries."""
from datetime import date
from unittest import TestCase
from unittest.mock import Mock, patch

from chatbot.context_cache import ContextRevision, fill_context_cache


class ContextCachePolicyScopeTests(TestCase):
    def test_missing_or_multiple_active_policy_pointers_block_background_fill(self):
        session = {'uid': 'synthetic-student', 'cohort': 'cohort_34'}
        day = date(2026, 10, 12)
        for count in (0, 2):
            with self.subTest(active_policy_count=count):
                revision = ContextRevision(1, 34, 'cohort_34', 'shared-revision',
                                           'attendance-revision', count)
                loader = Mock()
                with patch('chatbot.context_cache.redis_backoff_active', return_value=False), \
                     patch('chatbot.context_cache.read_revision', return_value=revision) as read, \
                     patch('chatbot.context_cache.redis_client') as redis:
                    result = fill_context_cache(session, loader=loader, today=day,
                                                 include_record_details=True)
                self.assertFalse(result)
                loader.assert_not_called()
                read.assert_called_once_with(session, include_attendance=True)
                redis.assert_not_called()
