"""Offline adaptive classification and concurrent bound-chain isolation."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from types import MappingProxyType
import os
from unittest import TestCase
from unittest.mock import Mock, patch
from types import SimpleNamespace
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

os.environ['LANGSMITH_TRACING'] = 'false'
os.environ['LANGCHAIN_TRACING_V2'] = 'false'

from langchain_core.messages import AIMessageChunk
from chatbot.answer_effort import choose_answer_effort
from chatbot.ops_log import build_generation_log_payload
from chatbot.student_chatbot import LmsStudentChatbot, _answer_reasoning_options, ChatState, SupervisorDecision
from chatbot.answer_effort import attendance_context_sufficient_without_search
from chatbot.tests.context_optimization_fixtures import fixture


class AdaptiveAnswerEffortTests(TestCase):
    def state(self, question='이번 단위기간 출석 어때?', missing=False):
        state = fixture(missing=missing)
        state.update(question=question, attendance_basis='unit', tasks=[],
                     student_scopes=['student_attendance'])
        return state

    def test_colloquial_status_is_low_but_policy_and_compound_stay_medium(self):
        for question in ('이번달 출석 괜찮나', '이번 달 출결 괜찮아?', '내 전체 훈련기간 출석 괜찮나'):
            state = self.state(question)
            state['attendance_basis'] = 'completion' if '전체' in question else 'unit'
            self.assertEqual(choose_answer_effort(state).effort, 'low')
        for question in ('이번달 출석 괜찮나 그리고 공지 알려줘', '이번달 공가 조건 괜찮나', '출석 예외 규정 알려줘'):
            self.assertEqual(choose_answer_effort(self.state(question)).effort, 'medium')

    def test_no_search_requires_same_cohort_complete_source_and_plain_request(self):
        state = self.state('이번달 출석 괜찮나')
        state['student_uid'] = 'synthetic-only'
        self.assertTrue(attendance_context_sufficient_without_search(state))
        self.assertEqual(state['student_context']['data']['student_attendance']['unit_period_context']
                         ['policy_calculation']['criteria']['allowance']['source_status'], 'draft')
        for mutation in ('uid', 'cohort', 'issues', 'rules', 'missing', 'compound', 'exception'):
            changed = deepcopy(state)
            context = changed['student_context']['data']['student_attendance']['unit_period_context']
            if mutation == 'uid': changed['student_uid'] = ''
            elif mutation == 'cohort': changed['cohort'] = 'cohort_40'
            elif mutation == 'issues': context['policy_calculation']['issues'] = {'allowance': 'conflicting'}
            elif mutation == 'rules': context['calculation_rules']['attendance_threshold_percent'] += 1
            elif mutation == 'missing':
                next(row for row in context['periods'] if row['number'] == context['current_unit_period'])['in_progress_estimate']['projection_status'] = 'records_need_review'
            elif mutation == 'compound': changed['question'] += ' 그리고 공지 알려줘'
            else: changed['question'] = '다음 수업에 지각하면 어떻게 돼?'
            self.assertFalse(attendance_context_sufficient_without_search(changed), mutation)

    def test_real_graph_stream_routes_search_and_selects_adaptive_chain(self):
        # Production nodes/edges and stream, with only IO/model outputs mocked.
        for question, missing, search_expected, effort in (
            ('이번달 출석 괜찮나', False, 0, 'low'),
            ('이번달 며칠 더 출석해야 해?', False, 0, 'low'),
            ('전체 훈련기간 출석 괜찮나', False, 0, 'low'),
            ('이번달 출석 괜찮나', True, 1, 'medium'),
            ('이번달 출석 공가 규정 알려줘', False, 1, 'medium'),
            ('이번달 출석 괜찮나 그리고 공지 알려줘', False, 1, 'medium'),
        ):
            with self.subTest(question=question, missing=missing):
                state = self.state(question, missing=missing)
                bot = object.__new__(LmsStudentChatbot)
                bot.supervisor_chain = None
                bot.supervisor_middleware = SimpleNamespace(invoke=lambda inputs, chain:
                    SupervisorDecision(route='lms', query=question, namespaces=['policy', 'notice'],
                                       student_scopes=['student_attendance']))
                bot.student_context_loader = Mock(return_value=state['student_context'])
                bot.answer_reasoning_effort = 'adaptive'
                bot.answer_chain = Mock()
                bot.adaptive_answer_chains = {level: Mock() for level in ('low', 'medium')}
                for level, chain in bot.adaptive_answer_chains.items():
                    chain.stream.side_effect = lambda inputs, config, text=level: iter([AIMessageChunk(content=text)])
                search = Mock(return_value={'documents': state['documents']})
                graph = StateGraph(ChatState)
                graph.add_node('supervisor', bot._supervisor)
                graph.add_node('student_tools', bot._student_tools)
                graph.add_node('policy_notice_retrieve', search)
                graph.add_node('project_retrieve', lambda _: {})
                graph.add_node('answer', bot._answer)
                graph.add_edge(START, 'supervisor')
                graph.add_conditional_edges('supervisor', bot._next_node)
                graph.add_conditional_edges('student_tools', bot._after_student_tools)
                graph.add_conditional_edges('policy_notice_retrieve', bot._after_policy_notice)
                graph.add_edge('answer', END)
                graph.add_edge('project_retrieve', 'answer')
                bot.graph = graph.compile(checkpointer=InMemorySaver())
                with patch('chatbot.attendance_basis.redis_backoff_active', return_value=True):
                    inputs = {'question': question, 'thread_id': 'routing-test', 'student_uid': 'synthetic-only',
                              'cohort': state['cohort'], 'unit_period_context': state['unit_period_context']}
                    self.assertEqual(''.join(bot.stream(inputs)), effort)
                self.assertEqual(search.call_count, search_expected)
                bot.student_context_loader.assert_called_once()
                selected = bot.adaptive_answer_chains[effort]
                selected.stream.assert_called_once()
                bot.adaptive_answer_chains['medium' if effort == 'low' else 'low'].stream.assert_not_called()
                payload = selected.stream.call_args.args[0]
                if search_expected == 0:
                    self.assertIn('전체 훈련기간 수료' if '전체' in question else '이번 단위기간', payload['question'])
                self.assertIn('source_status', payload['context'])
                self.assertIn('draft', payload['context'])

    def test_simple_verified_unit_schedule_and_simulation_are_low_without_namespace_shortcut(self):
        state = self.state()
        before = deepcopy(state)
        self.assertEqual(choose_answer_effort(state).effort, 'low')
        self.assertEqual(state, before)
        self.assertTrue(any(doc.metadata['_namespace'] == 'policy' for doc in state['documents']))
        state['question'] = '다음 수업에 지각하면 어떻게 돼?'
        self.assertEqual(choose_answer_effort(state).effort, 'low')
        schedule = self.state('개강일은 언제야?')
        schedule.update(attendance_basis=None, student_context={}, student_scopes=['cohort_shared'])
        self.assertEqual(choose_answer_effort(schedule).reason, 'simple_schedule')
        completion = self.state()
        completion['attendance_basis'] = 'completion'
        threshold = completion['student_context']['data']['student_attendance']['unit_period_context']['completion_progress']['threshold_percent']
        completion['question'] = f'내 전체 훈련기간 출석률 {threshold}% 넘으려면 며칠 더 출석해야 해?'
        self.assertEqual(choose_answer_effort(completion).reason, 'simple_completion')

    def test_whole_course_future_simulation_is_not_a_precomputed_unit_scenario(self):
        state = self.state('다음 수업에 지각하면 며칠 더 출석해야 해?')
        self.assertEqual(choose_answer_effort(state).effort, 'low')
        state['attendance_basis'] = 'completion'
        self.assertEqual(choose_answer_effort(state).effort, 'medium')
        for question in ('오늘 지각하면 며칠 더 출석해야 해?', '다다음 수업에 지각하면?',
                         '10월 12일에 지각하면 며칠 더 출석해야 해?'):
            self.assertEqual(choose_answer_effort(self.state(question)).effort, 'medium')

    def test_policy_compound_both_unknown_and_unprovided_hypotheses_stay_medium(self):
        for question in ('장려금 예외 규정 알려줘', '내 출석률 계산 공식 설명해줘', '왜 그렇게?', '정책이 90%로 바뀌면?',
                         '어제 지각을 정정하면?', '다음 수업 지각하고 그 다음 결석하면?',
                         '출석과 과제를 동시에 알려줘'):
            with self.subTest(question=question):
                self.assertEqual(choose_answer_effort(self.state(question)).effort, 'medium')
        for change in ({'attendance_basis': 'both'}, {'attendance_basis': 'clarify'},
                       {'tasks': [{}, {}]}, {'student_scopes': ['student_attendance', 'assignment_files']}):
            state = self.state(); state.update(change)
            self.assertEqual(choose_answer_effort(state).effort, 'medium')
        self.assertEqual(choose_answer_effort(self.state(missing=True)).effort, 'medium')

    def test_invalid_current_period_dates_nonfinite_values_and_missing_data_are_medium(self):
        for current in (None, 999):
            state = self.state('이번 단위기간 시작 날짜는 언제야?')
            state.update(attendance_basis=None, student_context={}, student_scopes=['cohort_shared'])
            state['unit_period_context']['current_unit_period'] = current
            self.assertEqual(choose_answer_effort(state).effort, 'medium')
        state = self.state('이번 단위기간 시작 날짜는 언제야?')
        state.update(attendance_basis=None, student_context={}, student_scopes=['cohort_shared'])
        current = state['unit_period_context']['current_unit_period']
        row = next(row for row in state['unit_period_context']['periods'] if row['number'] == current)
        row['start_date'] = 'invalid-date'
        self.assertEqual(choose_answer_effort(state).effort, 'medium')
        for rate in (float('inf'), float('nan')):
            state = self.state()
            context = state['student_context']['data']['student_attendance']['unit_period_context']
            row = next(row for row in context['periods'] if row['number'] == context['current_unit_period'])
            row['in_progress_estimate']['attendance_rate'] = rate
            self.assertEqual(choose_answer_effort(state).effort, 'medium')
        state = self.state(); state['student_context'] = {}
        self.assertEqual(choose_answer_effort(state).effort, 'medium')

    def test_fixed_unset_and_adaptive_options_preserve_existing_direct_calls(self):
        self.assertEqual(_answer_reasoning_options(None), {})
        self.assertEqual(_answer_reasoning_options('adaptive'), {})
        self.assertEqual(_answer_reasoning_options('low'), {'reasoning': {'effort': 'low'}})
        class Chain:
            def stream(self, inputs, config):
                yield AIMessageChunk(content='동일 답변')
        for setting in ('default', 'low', 'medium'):
            bot = object.__new__(LmsStudentChatbot)
            bot.answer_chain = Chain(); bot.answer_reasoning_effort = setting
            result = bot._answer(self.state())
            self.assertEqual(result['answer'], '동일 답변')
            self.assertEqual(result['answer_reasoning_effort'], setting)
            self.assertEqual(result['answer_effort_reason'], 'default_setting' if setting == 'default' else 'fixed_setting')

    def test_concurrent_adaptive_calls_select_independent_chains_and_safe_log_reason(self):
        barrier = Barrier(2)
        class Chain:
            def __init__(self, effort):
                self.effort = effort
            def stream(self, inputs, config):
                barrier.wait(timeout=4)
                yield AIMessageChunk(content=self.effort)
        bot = object.__new__(LmsStudentChatbot)
        bot.answer_reasoning_effort = 'adaptive'
        bot.answer_chain = None
        bot.adaptive_answer_chains = MappingProxyType({effort: Chain(effort) for effort in ('low', 'medium')})
        low = self.state()
        medium = self.state('장려금 예외 규정 알려줘')
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(bot._answer, (low, medium)))
        self.assertEqual([row['answer'] for row in results], ['low', 'medium'])
        self.assertEqual([row['answer_reasoning_effort'] for row in results], ['low', 'medium'])
        self.assertEqual(bot.answer_reasoning_effort, 'adaptive')
        for row in results:
            payload = build_generation_log_payload(cohort_id='test', created_by='test', latency_ms=1,
                status='success', snapshot=row)
            self.assertEqual(payload['answerReasoningEffort'], row['answer'])
            self.assertEqual(payload['answerEffortReason'], row['answer_effort_reason'])
        payload = build_generation_log_payload(cohort_id='test', created_by='test', latency_ms=1,
            status='success', snapshot={'answer_effort_reason': 'private text'})
        self.assertNotIn('private text', str(payload))
