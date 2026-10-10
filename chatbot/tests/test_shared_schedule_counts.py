from datetime import date
from unittest import TestCase
from unittest.mock import MagicMock, patch

from chatbot.firebase_student_context import load_unit_period_context
from chatbot.tests.test_active_policy_rules import uploaded


class SharedScheduleCountsTests(TestCase):
    def context(self, labels):
        cursor = MagicMock()
        def execute(sql, params):
            result = MagicMock()
            if 'start_date, end_date' in sql:
                result.fetchone.return_value = {'start_date': date(2026,9,16), 'end_date': date(2026,11,15)}
            elif 'curriculum_sheets' in sql:
                result.fetchone.return_value = {'id': 7} if labels else None
            elif 'curriculum_rows' in sql:
                return [{'date_label': label} for label in labels]
            else:
                raise AssertionError('Unexpected personal-data query')
            return result
        cursor.execute.side_effect = execute
        with patch('chatbot.firebase_student_context._connect') as connect, \
             patch('chatbot.firebase_student_context._cohort_ids', return_value=(1,'cohort_34')), \
             patch('chatbot.active_policy_rules.load_active_snapshot', return_value=uploaded()), \
             patch('chatbot.firebase_student_context._user_id') as user_lookup:
            connect.return_value.__enter__.return_value.cursor.return_value = cursor
            result = load_unit_period_context({'cohort':'cohort_34','uid':'fixture'},
                today=date(2026,10,10),include_attendance=False)
            user_lookup.assert_not_called()
            return result

    def test_counts_deduplicate_and_obey_period_boundary(self):
        result = self.context(['2026-09-16','2026-09-16','2026-10-15','2026-10-16'])
        self.assertEqual(result['periods'][0]['scheduled_days'],2)
        self.assertEqual(result['periods'][1]['scheduled_days'],1)
        self.assertEqual(result['scheduled_days_source'],'curriculum_rows')
        self.assertNotIn('status_counts',result['periods'][0])

    def test_missing_schedule_has_no_twenty_day_fallback(self):
        result = self.context([])
        self.assertIsNone(result['periods'][0]['scheduled_days'])
        self.assertEqual(result['scheduled_days_source'],'unavailable')
