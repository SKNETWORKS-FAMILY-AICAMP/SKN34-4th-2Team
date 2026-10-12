"""Independent concurrency, isolation and unchanged answer-input verification."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event, Barrier
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from langchain_core.messages import HumanMessage, AIMessageChunk
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from chatbot.student_chatbot import LmsStudentChatbot, SupervisorDecision, ChatState
from chatbot.tests.context_optimization_fixtures import fixture
from chatbot import api


def decision():
    return SupervisorDecision(route='lms',query='출석',student_scopes=['student_attendance'])


def bot(loader, invoke=None):
    value=object.__new__(LmsStudentChatbot)
    value.shared_context_loader=loader
    value.supervisor_chain=None
    value.supervisor_middleware=SimpleNamespace(invoke=invoke or (lambda *_:decision()))
    return value


def state(uid='synthetic-a',cohort='cohort_34'):
    return {'question':'내 출석','messages':[HumanMessage(content='내 출석')],
        'student_uid':uid,'cohort':cohort,'defer_shared_context':True,'unit_period_context':{}}


class ParallelPreparationTests(TestCase):
    def test_loader_and_supervisor_actually_overlap_and_join(self):
        started=Event();model_entered=Event();loaded=Event()
        def load(session):
            started.set()
            if not model_entered.wait(2):raise AssertionError('Supervisor did not overlap')
            loaded.set();return {'scheduled_days':120}
        def invoke(*_):
            self.assertTrue(started.wait(2));model_entered.set();return decision()
        result=bot(load,invoke)._supervisor(state())
        self.assertTrue(loaded.is_set())
        self.assertEqual(result['unit_period_context'],{'scheduled_days':120})
        self.assertEqual(result['parallel_prep_enabled'],1)
        self.assertFalse(result['defer_shared_context'])

    def test_four_concurrent_requests_do_not_share_sessions(self):
        gate=Barrier(4)
        def load(session):
            gate.wait(timeout=4)
            return {'marker':session['uid'],'cohort':session['cohort']}
        shared_bot=bot(load)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda i:shared_bot._supervisor(state(f'user-{i}',f'cohort-{i}')),range(4)))
        for i,result in enumerate(results):
            self.assertEqual(result['unit_period_context'],{'marker':f'user-{i}','cohort':f'cohort-{i}'})

    def test_supervisor_failure_drains_loader_and_keeps_original_error(self):
        started=Event();release=Event();finished=Event()
        def load(_):
            started.set();release.wait(2);finished.set();raise ValueError('loader error')
        def invoke(*_):
            self.assertTrue(started.wait(2));release.set();raise RuntimeError('supervisor error')
        with self.assertRaisesRegex(RuntimeError,'supervisor error'):
            bot(load,invoke)._supervisor(state())
        self.assertTrue(finished.is_set())

    def test_loader_failure_matches_serial_fallback(self):
        failed=Mock(side_effect=ValueError('DB unavailable'))
        with patch.object(api,'_load_unit_context',failed):
            serial=api._chat_inputs(api.InitRequest(thread_id='test'),{'uid':'u','cohort':'cohort_34'})
        result=bot(failed)._supervisor(state())
        self.assertEqual(result['unit_period_context'],serial['unit_period_context'])

    def test_explicit_context_and_omitted_context_do_not_inherit_previous_state(self):
        loader=Mock(return_value={'new':True});b=bot(loader)
        explicit={'question':'q','thread_id':'t','unit_period_context':{'existing':1},'defer_shared_context':True}
        prepared,_=b._prepare_call(explicit)
        self.assertFalse(prepared['defer_shared_context'])
        self.assertEqual(prepared['unit_period_context'],{'existing':1})
        fresh,_=b._prepare_call({'question':'q','thread_id':'t'})
        self.assertEqual(fresh['unit_period_context'],{})
        self.assertEqual(fresh['student_uid'],'')
        self.assertEqual(fresh['cohort'],'')
        self.assertFalse(fresh['defer_shared_context'])

    def test_api_default_is_eager_and_deferral_does_not_read(self):
        with patch.object(api,'_load_unit_context',return_value={'x':1}) as load:
            eager=api._chat_inputs(api.InitRequest(thread_id='test'),{'uid':'u','cohort':'cohort_34'})
            deferred=api._chat_inputs(api.InitRequest(thread_id='test'),{'uid':'u','cohort':'cohort_34'},defer_shared_context=True)
        load.assert_called_once_with({'uid':'u','cohort':'cohort_34'},include_attendance=False)
        self.assertEqual(eager['unit_period_context'],{'x':1})
        self.assertEqual(deferred['unit_period_context'],{})
        self.assertTrue(deferred['defer_shared_context'])

    def test_graph_answer_prompt_and_calculation_are_identical(self):
        fixed=fixture();captures=[]
        class Chain:
            def stream(self,inputs,config):
                captures.append(deepcopy(inputs));yield AIMessageChunk(content='동일 계산 결과')
        loader=Mock(return_value=deepcopy(fixed['unit_period_context']))
        b=bot(loader);b.answer_chain=Chain()
        graph=StateGraph(ChatState)
        graph.add_node('supervisor',b._supervisor)
        graph.add_node('student',lambda _: {'student_context':deepcopy(fixed['student_context']), 'documents':fixed['documents']})
        graph.add_node('answer',b._answer)
        graph.add_edge(START,'supervisor');graph.add_edge('supervisor','student');graph.add_edge('student','answer');graph.add_edge('answer',END)
        b.graph=graph.compile(checkpointer=InMemorySaver())
        for mode in ('serial','parallel'):
            inputs={'question':fixed['question'],'thread_id':mode,'student_uid':'synthetic','cohort':fixed['cohort'],
                'unit_period_context':fixed['unit_period_context'] if mode=='serial' else {},'defer_shared_context':mode=='parallel'}
            self.assertEqual(b.invoke(inputs)['answer'],'동일 계산 결과')
        self.assertEqual(captures[0],captures[1])
        loader.assert_called_once_with({'uid':'synthetic','cohort':fixed['cohort']})
