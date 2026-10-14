from django.test import SimpleTestCase
from unittest.mock import Mock, patch

from lms.api import QuestionAnswerIn, resume_review_question_answer


class QuestionAnswerSchemaTests(SimpleTestCase):
    def test_selection_id_survives_django_request_schema(self):
        body = QuestionAnswerIn(
            resumeId='base', tailoredResumeId='tailored', questionId='q',
            answers=[{'question': '선택', 'answer': 'Beacon 분석',
                      'source_type': 'selection', 'selected_experience_id': 'projects:beacon'}],
        )
        assert body.answers[0].dict()['selected_experience_id'] == 'projects:beacon'

    def test_django_proxy_keeps_latest_memo_and_choice_with_long_history(self):
        answers = [
            {'question': '메모', 'answer': '현재는 Beacon 중심', 'source_type': 'memo'},
            {'question': '이전 선택', 'answer': 'Apollo', 'source_type': 'selection',
             'selected_experience_id': 'projects:apollo'},
        ]
        answers.extend({'question': f'보충 {index}', 'answer': f'사실 {index}'} for index in range(15))
        # A legacy/latest choice must shadow the older valid one even after trimming.
        answers.insert(5, {'question': '다시 선택', 'answer': 'Apollo 말고 다른 경험', 'source_type': 'selection'})
        body = QuestionAnswerIn(resumeId='base', tailoredResumeId='copy', questionId='q', answers=answers)
        row = {'id': 9, 'legacy_id': 'base', 'code': '34', 'firebase_uid': 'user'}
        with patch('lms.api._owned_resume', return_value=(row, None)), \
             patch('lms.api._review_call', return_value={'draft': ''}) as call:
            resume_review_question_answer(Mock(), body)
        path, payload = call.call_args.args
        self.assertEqual(path, '/api/v1/resumes/question-answer/proxy')
        self.assertEqual(len(payload['answers']), 12)
        self.assertEqual([item['source_type'] for item in payload['answers']].count('memo'), 1)
        self.assertEqual([item['source_type'] for item in payload['answers']].count('selection'), 1)
        self.assertEqual(payload['answers'][0]['answer'], '현재는 Beacon 중심')
        self.assertEqual(next(item for item in payload['answers'] if item['source_type'] == 'selection')['answer'],
                         'Apollo 말고 다른 경험')
        self.assertEqual([item['answer'] for item in payload['answers'] if item['source_type'] == 'answer'],
                         [f'사실 {index}' for index in range(5, 15)])

    def test_django_proxy_keeps_latest_valid_selection_even_when_followed_by_answers(self):
        answers = [{'question': '메모', 'answer': '현재 메모', 'source_type': 'memo'}]
        answers.extend({'question': f'보충 {index}', 'answer': f'사실 {index}'} for index in range(16))
        answers.insert(2, {'question': '선택', 'answer': 'Beacon', 'source_type': 'selection',
                           'selected_experience_id': 'projects:beacon'})
        body = QuestionAnswerIn(resumeId='base', tailoredResumeId='copy', questionId='q', answers=answers)
        row = {'id': 9, 'legacy_id': 'base', 'code': '34', 'firebase_uid': 'user'}
        with patch('lms.api._owned_resume', return_value=(row, None)), \
             patch('lms.api._review_call', return_value={'draft': ''}) as call:
            resume_review_question_answer(Mock(), body)
        sent = call.call_args.args[1]['answers']
        self.assertEqual(sent[0]['answer'], '현재 메모')
        self.assertEqual(next(item for item in sent if item['source_type'] == 'selection')['selected_experience_id'],
                         'projects:beacon')
        self.assertEqual([item['answer'] for item in sent if item['source_type'] == 'answer'],
                         [f'사실 {index}' for index in range(6, 16)])
