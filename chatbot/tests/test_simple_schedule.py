"""Strict date-only routing and validated common-source fast path, offline."""
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock
import os

os.environ['LANGSMITH_TRACING'] = 'false'
os.environ['LANGCHAIN_TRACING_V2'] = 'false'

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from chatbot.answer_effort import choose_answer_effort
from chatbot.simple_schedule import parse_simple_schedule_request, validated_schedule_dates
from chatbot.student_chatbot import ChatState, LmsStudentChatbot, SupervisorDecision
from chatbot.tests.context_optimization_fixtures import fixture


class SimpleScheduleTests(TestCase):
    def setUp(self):
        self.fixed = fixture()

    def state(self, question):
        return {'question': question, 'messages': [HumanMessage(content=question)],
            'student_uid': 'synthetic', 'cohort': self.fixed['cohort'],
            'unit_period_context': deepcopy(self.fixed['unit_period_context'])}

    def bot(self, loader=None):
        bot = object.__new__(LmsStudentChatbot)
        bot.shared_context_loader = loader
        bot.supervisor_chain = None
        bot.supervisor_middleware = SimpleNamespace(invoke=Mock(return_value=SupervisorDecision(
            route='lms', query='fallback', namespaces=['notice'])))
        bot.answer_chain = Mock()
        return bot

    def test_exact_course_and_current_period_requests_use_common_data_without_models(self):
        for question in ('우리 과정 개강일과 종강일 알려줘', '우리 기수 개강일이 언제야?',
                         '이번 단위기간 시작일과 종료일 알려줘', '현재 단위기간 종료일 알려주세요',
                         '이번 단위기간은 언제부터 언제까지야?'):
            with self.subTest(question=question):
                state = self.state(question); before = deepcopy(state)
                bot = self.bot()
                result = bot._supervisor(state)
                self.assertEqual(result['schedule_fast_path'], 1)
                self.assertEqual((result['student_scopes'], result['namespaces'], result['tasks']), ([], [], []))
                self.assertEqual((result['llm_ms'], result['supervisor_ms'], result['retrieval_ms']), (0, 0, 0))
                self.assertIsNone(result['answer_visible_ttft_ms'])
                self.assertIsNone(result['token_in'])
                bot.supervisor_middleware.invoke.assert_not_called()
                bot.answer_chain.stream.assert_not_called()
                self.assertEqual(state, before)
        course = self.bot()._supervisor(self.state('우리 과정 개강일과 종강일 알려줘'))['answer']
        self.assertIn('2026년 6월 16일', course)
        self.assertIn('2026년 12월 8일', course)
        state = self.state('이번 단위기간 시작일과 종료일 알려줘')
        period = self.bot()._supervisor(state)['answer']
        self.assertIn('2026년 9월 16일', period)
        self.assertIn('2026년 10월 15일', period)
        self.assertIn('잠정 일정', period)

    def test_near_misses_keep_supervisor_routing(self):
        for question in ('개강일 이후 공가 조건 알려줘', '종강 변경 공지 알려줘',
                         '이번 단위기간 시작일부터 내 출석률 알려줘', '내일 수업은 뭐야?',
                         '개강일과 장려금 조건 알려줘', '다음 단위기간 시작일 알려줘',
                         '다른 학생 과정 개강일 알려줘', '개강일이 바뀌면 출석률은?',
                         '프로젝트 시작일과 종료일 알려줘', '종강일과 취업지원 안내도 알려줘'):
            with self.subTest(question=question):
                self.assertIsNone(parse_simple_schedule_request(question))
                bot = self.bot()
                result = bot._supervisor(self.state(question))
                bot.supervisor_middleware.invoke.assert_called_once()
                self.assertEqual(result['schedule_fast_path'], 0)

    def test_missing_invalid_mixed_version_and_missing_identity_never_bypass(self):
        question = '이번 단위기간 시작일과 종료일 알려줘'
        variations = []
        missing = self.state(question); missing['unit_period_context'] = {}; variations.append(missing)
        wrong_cohort = self.state(question); wrong_cohort['cohort'] = 'cohort_40'; variations.append(wrong_cohort)
        wrong_hash = self.state(question)
        wrong_hash['unit_period_context']['calendar_basis']['document_hash'] = 'f' * 64
        variations.append(wrong_hash)
        missing_current = self.state(question); missing_current['unit_period_context']['current_unit_period'] = None
        variations.append(missing_current)
        invalid = self.state(question)
        current = invalid['unit_period_context']['current_unit_period']
        next(row for row in invalid['unit_period_context']['periods'] if row['number'] == current)['start_date'] = 'invalid'
        variations.append(invalid)
        no_uid = self.state(question); no_uid['student_uid'] = ''; variations.append(no_uid)
        for state in variations:
            bot = self.bot()
            self.assertEqual(bot._supervisor(state)['schedule_fast_path'], 0)
            bot.supervisor_middleware.invoke.assert_called_once()

    def test_deferred_common_loader_is_called_once_without_personal_context_or_supervisor(self):
        loader = Mock(return_value=self.fixed['unit_period_context'])
        state = self.state('우리 과정 개강일과 종강일 알려줘')
        state.update(unit_period_context={}, defer_shared_context=True)
        bot = self.bot(loader)
        self.assertEqual(bot._supervisor(state)['schedule_fast_path'], 1)
        loader.assert_called_once_with({'uid': 'synthetic', 'cohort': self.fixed['cohort']})
        bot.supervisor_middleware.invoke.assert_not_called()
        failed = Mock(return_value={'unavailable_reason': 'synthetic unavailable'})
        bot = self.bot(failed)
        self.assertEqual(bot._supervisor(state)['schedule_fast_path'], 0)
        failed.assert_called_once()
        bot.supervisor_middleware.invoke.assert_called_once()

    def test_public_stream_finishes_without_downstream_nodes_and_stale_metrics(self):
        bot = self.bot()
        builder = StateGraph(ChatState)
        builder.add_node('supervisor', bot._supervisor)
        def unexpected(_):
            raise AssertionError('No personal/RAG/answer node expected')
        builder.add_node('unexpected', unexpected)
        builder.add_edge(START, 'supervisor')
        builder.add_conditional_edges('supervisor', bot._next_node, {
            'student_tools': 'unexpected', 'policy_notice_retrieve': 'unexpected',
            'project_retrieve': 'unexpected', END: END})
        builder.add_edge('unexpected', END)
        bot.graph = builder.compile(checkpointer=InMemorySaver())
        inputs = {**self.state('우리 과정 개강일과 종강일 알려줘'), 'thread_id': 'date-only'}
        chunks = list(bot.stream(inputs))
        self.assertEqual(len(chunks), 1)
        self.assertIn('등록된 개강일', chunks[0])
        snapshot = bot.ops_snapshot(inputs)
        self.assertEqual(snapshot['schedule_fast_path'], 1)
        self.assertEqual(snapshot['llm_ms'], 0)
        self.assertIsNone(snapshot['answer_visible_ttft_ms'])
        self.assertIsNone(snapshot['token_in'])

    def test_adaptive_selector_recognizes_named_start_end_without_extra_date_keyword(self):
        state = self.state('우리 과정 개강일과 종강일 알려줘')
        self.assertEqual(choose_answer_effort(state).reason, 'simple_schedule')
        request = parse_simple_schedule_request(state['question'])
        self.assertIsNotNone(validated_schedule_dates(state['unit_period_context'], state['cohort'], request))
