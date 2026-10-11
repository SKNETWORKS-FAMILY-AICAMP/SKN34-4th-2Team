from django.test import SimpleTestCase
from unittest.mock import Mock, patch

from lms.api import QuestionWorkflowIn, resume_review_question_workflow


class QuestionWorkflowProxyTests(SimpleTestCase):
    def test_proxy_sends_latest_memo_and_recent_notes_for_every_question(self):
        notes = [{'question': f'질문 {i}', 'answer': f'답 {i}'} for i in range(15)]
        body = QuestionWorkflowIn(resumeId='base', tailoredResumeId='apply_1', questions=[
            {'id': 'cq1', 'memo': '3일 붙잡음', 'notes': notes},
            {'id': 'cq2'},
        ])
        row = {'id': 9, 'legacy_id': 'base', 'code': '34', 'firebase_uid': 'user'}
        with patch('lms.api._owned_resume', return_value=(row, None)), \
             patch('lms.api._review_call', return_value={'questions': []}) as call:
            resume_review_question_workflow(Mock(), body)
        path, payload = call.call_args.args
        assert path == '/api/v1/resumes/question-workflow/proxy'
        assert call.call_args.kwargs['timeout'] == 300
        assert payload['uid'] == 'user' and payload['cohort_id'] == '34' and payload['tailored_resume_id'] == 'apply_1'
        first, second = payload['questions']
        assert first['memo'] == '3일 붙잡음'
        assert [n['answer'] for n in first['notes']] == [f'답 {i}' for i in range(3, 15)]
        assert second == {'id': 'cq2', 'memo': '', 'notes': []}

    def test_proxy_stops_when_resume_is_not_owned(self):
        denied = Mock()
        body = QuestionWorkflowIn(resumeId='other', tailoredResumeId='apply_1', questions=[])
        with patch('lms.api._owned_resume', return_value=(None, denied)), \
             patch('lms.api._review_call') as call:
            assert resume_review_question_workflow(Mock(), body) is denied
        call.assert_not_called()

    def test_proxy_passes_single_question_and_saved_plan(self):
        plan = {'cq1': {'question_id': 'cq1', 'parts': [{'key': '역량', 'quote': '역량'}], 'lead_source_ids': [], 'angle': ''}}
        body = QuestionWorkflowIn(resumeId='base', tailoredResumeId='apply_1', questions=[{'id': 'cq1'}],
                                  only='cq1', plan=plan)
        row = {'id': 9, 'legacy_id': 'base', 'code': '34', 'firebase_uid': 'user'}
        with patch('lms.api._owned_resume', return_value=(row, None)), \
             patch('lms.api._review_call', return_value={'questions': []}) as call:
            resume_review_question_workflow(Mock(), body)
        _, payload = call.call_args.args
        assert payload['only'] == 'cq1' and payload['plan'] == plan
