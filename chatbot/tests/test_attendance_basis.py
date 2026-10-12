"""Deterministic basis selection and cross-worker graph contracts; no services."""
import json
import os
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

os.environ['LANGSMITH_TRACING'] = 'false'
os.environ['LANGCHAIN_TRACING_V2'] = 'false'

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from chatbot import attendance_basis as basis
from chatbot.student_chatbot import ChatState, LmsStudentChatbot, SupervisorDecision, SupervisorTask


class MemoryRedis:
    def __init__(self):
        self.values = {}
    def get(self, key):
        return self.values.get(key)
    def set(self, key, value, **kwargs):
        self.values[key] = value
        return True


class AttendanceBasisTests(TestCase):
    def setUp(self):
        self.redis = MemoryRedis()
        self.identity = {'uid': 'user-a', 'cohort': 'cohort_34', 'thread_id': 'conversation-a'}
        for patcher in (patch.object(basis, 'redis_client', return_value=self.redis),
                        patch.object(basis, 'redis_backoff_active', return_value=False),
                        patch.object(basis, 'mark_redis_failure')):
            patcher.start(); self.addCleanup(patcher.stop)

    def request(self, question, identity=None):
        return basis.resolve_request_basis(question, identity or self.identity)

    def test_new_ambiguous_question_asks_instead_of_using_eighty_percent(self):
        self.assertTrue(self.request('내 출석률이 80% 넘으려면 며칠 더 출석해야 해?').needs_clarification)
        record = json.loads(next(iter(self.redis.values.values())))
        self.assertEqual(record, {'version': 1, 'basis': None, 'pending': True})
        self.assertNotIn('80', str(record))

    def test_explicit_bases_and_negative_switches(self):
        for question, expected in (
            ('이번 단위기간 출석 어때?', 'unit'),
            ('내 이번 달 장려금 출석률 알려줘', 'unit'),
            ('전체 훈련기간 수료 기준으로 알려줘', 'completion'),
            ('수료 말고 이번 단위기간 기준으로 알려줘', 'unit'),
            ('단위기간 말고 전체 과정으로 알려줘', 'completion'),
            ('내 단위기간과 전체 과정 출석률을 둘 다 비교해줘', 'both'),
        ):
            with self.subTest(question=question):
                self.assertEqual(self.request(question).basis, expected)

    def test_followup_preserves_user_selected_basis_and_both_requires_reconfirmation(self):
        for first, expected in (('이번 단위기간 출석 어때?', 'unit'),
                                ('전체 훈련기간 수료 기준으로 알려줘', 'completion')):
            self.request(first)
            self.assertEqual(self.request('앞으로 며칠 더 출석해야 해?').basis, expected)
            self.assertEqual(self.request('다음 수업에 지각하면 어떻게 돼?').basis, expected)
        self.request('내 단위기간과 전체 과정 출석률을 둘 다 비교해줘')
        self.assertTrue(self.request('앞으로 며칠 더 출석해야 해?').needs_clarification)

    def test_short_selection_connects_pending_question_and_clears_old_basis(self):
        self.request('이번 단위기간 출석 어때?')
        self.request('단위기간인지 수료인지 모르겠어, 내 출석 계산 알려줘')
        self.assertTrue(self.request('그럼 내 출석률은?').needs_clarification)
        choice = self.request('단위기간이요')
        self.assertEqual(choice.basis, 'unit')
        self.assertIn('추가 정상 출석 필요일', choice.question)
        self.request('단위기간인지 수료인지 모르겠어, 내 출석 계산 알려줘')
        self.assertEqual(self.request('둘 다 알려줘').basis, 'both')

    def test_users_cohorts_threads_expiry_and_failure_do_not_inherit(self):
        self.request('이번 단위기간 출석 어때?')
        for field, value in (('uid', 'user-b'), ('cohort', 'cohort_40'), ('thread_id', 'conversation-b')):
            self.assertTrue(self.request('내 출석률은?', {**self.identity, field: value}).needs_clarification)
        self.redis.values.clear()
        self.assertTrue(self.request('내 출석률은?').needs_clarification)
        with patch.object(basis, 'redis_client', side_effect=TimeoutError('synthetic')):
            self.assertTrue(self.request('내 출석률은?').needs_clarification)

    def test_generic_requests_do_not_force_calculation_or_touch_scope_store(self):
        for question in ('이번 달 공지 알려줘', '수료 프로젝트 주제 추천', '장려금 신청 마감일',
                         '지각 규정 알려줘', '수료랑 장려금 기준 각각 비교'):
            with self.subTest(question=question), patch.object(basis, 'redis_client') as client:
                self.assertIsNone(self.request(question).basis)
                client.assert_not_called()
        self.assertTrue(self.request('지각하면 며칠 더 나가야 해?').needs_clarification)

    def test_legacy_web_is_fresh_and_never_shares_selection(self):
        for thread in ('web', 'a' * 24 + '.web'):
            identity = {**self.identity, 'thread_id': thread}
            self.assertEqual(self.request('이번 단위기간 출석 어때?', identity).basis, 'unit')
            self.assertTrue(self.request('내 출석률은?', identity).needs_clarification)
        self.assertFalse(self.redis.values)

    def graph_bot(self, middleware=None):
        bot = object.__new__(LmsStudentChatbot)
        bot.supervisor_chain = None
        self.inputs_seen = []
        def route(inputs, chain):
            text = inputs['messages'][-1].content
            self.inputs_seen.append(text)
            if text.strip() in ('단위기간이요', '둘 다 알려줘'):
                return SupervisorDecision(route='blocked', query='')
            return SupervisorDecision(route='lms', query=text, student_scopes=['student_attendance'])
        bot.supervisor_middleware = SimpleNamespace(invoke=middleware or route)
        bot.answer_chain = Mock()
        bot.answer_chain.stream.side_effect = lambda inputs, config: iter([AIMessageChunk(content='공지 안내.')])
        builder = StateGraph(ChatState)
        builder.add_node('supervisor', bot._supervisor)
        builder.add_node('data', lambda _: {'documents': [Document(page_content='합성 공지',
            metadata={'_namespace': 'notice', 'doc_id': 'notice-1'})], 'student_context': {}})
        builder.add_node('answer', bot._answer)
        builder.add_edge(START, 'supervisor')
        builder.add_conditional_edges('supervisor', bot._next_node, {
            'student_tools': 'data', 'policy_notice_retrieve': 'data', 'project_retrieve': 'data', END: END})
        builder.add_edge('data', 'answer'); builder.add_edge('answer', END)
        bot.graph = builder.compile(checkpointer=InMemorySaver())
        return bot

    def call(self, bot, question, thread='conversation-a'):
        return bot.invoke({'question': question, 'thread_id': thread,
                           'student_uid': 'user-a', 'cohort': 'cohort_34'})

    def test_fresh_second_worker_resolves_short_selection_before_supervisor(self):
        first = self.graph_bot()
        self.assertEqual(self.call(first, '내 출석률이 80% 넘으려면 며칠 더 출석해야 해?')['answer'], basis.CLARIFICATION)
        first.answer_chain.stream.assert_not_called()
        second = self.graph_bot()
        self.call(second, '단위기간이요')
        self.assertIn('내 이번 단위기간', self.inputs_seen[-1])
        self.assertIn('사용자가 확인한 개인 출석 계산 기준: 이번 단위기간',
                      second.answer_chain.stream.call_args.args[0]['question'])
        third = self.graph_bot()
        self.assertEqual(self.call(third, '내 출석률은?', 'new-conversation')['answer'], basis.CLARIFICATION)

    def test_assistant_only_old_basis_does_not_confirm_a_user_basis(self):
        bot = self.graph_bot()
        config = {'configurable': {'thread_id': 'conversation-a'}}
        bot.graph.update_state(config, {'messages': [AIMessage(content='단위기간 기준으로 계산했어요.')]})
        self.assertEqual(self.call(bot, '내 출석률은?')['answer'], basis.CLARIFICATION)
        bot.answer_chain.stream.assert_not_called()

    def test_mixed_question_preserves_notice_and_appends_only_attendance_confirmation(self):
        def route(inputs, chain):
            return SupervisorDecision(route='lms', query='mixed', namespaces=['notice'],
                student_scopes=['student_attendance'], tasks=[
                    SupervisorTask(query='내 출석률 80% 넘으려면 며칠 더 출석해야 해?',
                                   student_scopes=['student_attendance'], reason='출석'),
                    SupervisorTask(query='이번 주 공지 알려줘', namespaces=['notice'], reason='공지')])
        bot = self.graph_bot(route)
        result = self.call(bot, '내 출석률 80% 넘으려면 며칠, 그리고 이번 주 공지 알려줘')
        self.assertEqual(result['answer'], '공지 안내.\n\n' + basis.CLARIFICATION)
        self.assertEqual(bot.answer_chain.stream.call_args.args[0]['question'], '이번 주 공지 알려줘')
        self.assertEqual(result['namespaces'], ['notice'])

    def test_notice_month_does_not_choose_calculation_basis(self):
        result = self.request('내 출석률 80% 넘으려면 며칠 더 출석해야 해? 그리고 이번 달 공지 알려줘')
        self.assertTrue(result.needs_clarification)
