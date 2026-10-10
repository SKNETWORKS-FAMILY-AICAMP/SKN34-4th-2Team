from datetime import date
from unittest import TestCase
from unittest.mock import MagicMock, patch

from chatbot.api import InitRequest, _chat_inputs
from chatbot.firebase_student_context import load_unit_period_context
from chatbot.student_chatbot import detect_routing_signals
from chatbot.unit_period import calculate_unit_period_context


class UnitPeriodContextTests(TestCase):
    def test_dates_without_curriculum_and_partial_final_month(self):
        context = calculate_unit_period_context(date(2026, 10, 7), date(2027, 3, 31), today=date(2026, 11, 7))
        self.assertEqual(context['current_unit_period'], 2)
        self.assertEqual([(p['start_date'], p['end_date']) for p in context['periods']], [
            ('2026-10-07', '2026-11-06'), ('2026-11-07', '2026-12-06'),
            ('2026-12-07', '2027-01-06'), ('2027-01-07', '2027-02-06'),
            ('2027-02-07', '2027-03-06'), ('2027-03-07', '2027-03-31'),
        ])
        self.assertTrue(all(p['attendance_rate'] is None for p in context['periods']))

    def test_calendar_load_reads_schedule_without_personal_attendance(self):
        conn = MagicMock()
        cur = conn.cursor.return_value
        cur.execute.return_value.fetchone.side_effect = [
            {'id': 40, 'code': 'cohort-test'},
            {'start_date': date(2026, 10, 7), 'end_date': date(2027, 3, 31)},
            None,
        ]
        with patch('chatbot.firebase_student_context._connect') as connect:
            connect.return_value.__enter__.return_value = conn
            result = load_unit_period_context({'cohort': 'cohort-test', 'uid': 'student'}, include_attendance=False)
        self.assertEqual(cur.execute.call_count, 3)
        self.assertFalse(any('FROM attendances' in call.args[0] for call in cur.execute.call_args_list))
        self.assertEqual(len(result['periods']), 6)
        self.assertNotIn('attendance_rate', result['periods'][0])

    def test_each_chat_receives_authenticated_calendar(self):
        session = {'uid': 'student', 'cohort': 'cohort-test'}
        with patch('chatbot.api._load_unit_context', return_value={'periods': []}) as loader:
            inputs = _chat_inputs(InitRequest(thread_id='test'), session)
        loader.assert_called_once_with(session, include_attendance=False)
        self.assertEqual(inputs['unit_period_context'], {'periods': []})
        self.assertTrue(detect_routing_signals('이번 단위기간 시작일과 종료일은?').lms)

    def test_load_failure_replaces_context_instead_of_reusing_old_dates(self):
        with patch('chatbot.api._load_unit_context', side_effect=RuntimeError('unavailable')):
            inputs = _chat_inputs(InitRequest(thread_id='test'), {'uid': 'student', 'cohort': 'missing'})
        self.assertIn('unavailable_reason', inputs['unit_period_context'])
        self.assertNotIn('periods', inputs['unit_period_context'])
