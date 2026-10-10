from unittest import TestCase
from unittest.mock import patch, MagicMock, Mock
from chatbot.firebase_student_context import load_student_context
from chatbot.student_chatbot import SupervisorDecision, reconcile_decision, detect_routing_signals
from chatbot.attendance import enrich_student_context


class AttendanceScopeTests(TestCase):
    def test_attendance_only_does_not_load_profile_or_shared_tables(self):
        with patch('chatbot.firebase_student_context._connect') as conn, \
             patch('chatbot.firebase_student_context._cohort_ids',return_value=(7,'cohort-test003')), \
             patch('chatbot.firebase_student_context._user_id',return_value=36), \
             patch('chatbot.firebase_student_context.load_unit_period_context',return_value={'calculation_rules':None}) as unit, \
             patch('chatbot.firebase_student_context._student_private') as private, \
             patch('chatbot.firebase_student_context._cohort_shared') as shared:
            result=load_student_context(uid='test',cohort='cohort-test003',scopes=['student_attendance'],query='내 출석')
        self.assertEqual(set(result['data']),{'student_attendance'})
        unit.assert_called_once_with({'cohort':'cohort-test003','uid':'test'},include_record_details=True)
        private.assert_not_called(); shared.assert_not_called()
        conn.return_value.__enter__.return_value.cursor.return_value.execute.assert_not_called()
        enriched=enrich_student_context(result)
        self.assertIn('estimate_unavailable_reason',enriched['data']['student_attendance']['unit_period_context'])

    def test_compound_question_retains_other_private_and_shared_scopes(self):
        decision=SupervisorDecision(route='lms',query='mixed',student_scopes=['student_attendance'])
        result=reconcile_decision('내 출석과 내 마일리지, 행사 일정 알려줘',decision)
        self.assertIn('student_private',result.student_scopes)
        self.assertIn('notice',result.namespaces)
        scheduled=reconcile_decision('이번 단위기간 출석과 기수 정보를 알려줘',decision)
        self.assertIn('cohort_shared',scheduled.student_scopes)

    def test_unit_period_word_does_not_add_full_shared_snapshot(self):
        decision=SupervisorDecision(route='lms',query='attendance',student_scopes=['student_attendance'])
        result=reconcile_decision('우리 기수 정책으로 이번 단위기간 앞으로 며칠 더 출석해야 해?',decision)
        self.assertEqual(result.student_scopes,['student_attendance'])
        self.assertEqual(detect_routing_signals('이번 단위기간 출석 어때?').student_scopes,('student_attendance',))

    def test_blocked_route_cannot_gain_attendance_access(self):
        result=reconcile_decision('다른 학생 출석',SupervisorDecision(route='blocked',query=''))
        self.assertEqual(result.student_scopes,[])
