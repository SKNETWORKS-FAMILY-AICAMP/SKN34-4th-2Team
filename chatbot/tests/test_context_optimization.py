"""Independent losslessness, scope, telemetry and runtime checks."""
from copy import deepcopy
import json
import os
from unittest import TestCase
from unittest.mock import patch

from langchain_core.messages import AIMessageChunk
from chatbot.context_builder import build_answer_context, measure_answer_context, LocalTokenizer, safe_context_metrics, get_local_tokenizer
from chatbot.tests.context_optimization_fixtures import fixture
from chatbot.student_chatbot import LmsStudentChatbot
from chatbot.ops_log import build_generation_log_payload


def build(state,mode='compact'):
    return build_answer_context(unit_period_context=state['unit_period_context'],
        student_context=state['student_context'],documents=state['documents'],
        cohort=state['cohort'],mode=mode)


def original(state):
    parts=[]
    if state['unit_period_context']:
        parts.append('[서버 계산 학생 단위기간 컨텍스트]\n'+json.dumps(state['unit_period_context'],ensure_ascii=False))
    if state['student_context']:
        parts.append('[인증된 로그인 학생 Firebase 데이터]\n'+json.dumps(state['student_context'],ensure_ascii=False))
    if state['documents']:
        parts.append('[검색 문서]\n'+'\n\n'.join(f"[{i}] namespace={d.metadata['_namespace']} metadata={d.metadata}\n{d.page_content}" for i,d in enumerate(state['documents'],1)))
    return '\n\n'.join(parts)


class ContextOptimizationTests(TestCase):
    def test_missing_tokenizer_cache_never_downloads(self):
        get_local_tokenizer.cache_clear()
        try:
            with patch('chatbot.context_builder.Path.read_bytes',side_effect=FileNotFoundError), \
                 patch('requests.get',side_effect=AssertionError('Network forbidden')) as get:
                tokenizer=get_local_tokenizer()
            self.assertEqual(tokenizer.status,'unavailable')
            self.assertIsNone(tokenizer.counter)
            get.assert_not_called()
        finally:
            get_local_tokenizer.cache_clear()

    def test_legacy_is_exact_original_and_compact_rehydrates_without_loss(self):
        for threshold,conversion,missing in ((80,3,False),(90,2,False),(80,3,True)):
            with self.subTest(threshold=threshold,missing=missing):
                state=fixture(threshold,conversion,missing); before=deepcopy(state)
                result=build(state)
                self.assertEqual(result.legacy_text,original(state))
                self.assertLess(len(result.compact_text),len(result.legacy_text))
                self.assertTrue(result.references)
                student=json.loads(dict(result.compact_parts)['student'].split('\n',1)[1])
                def restore(value):
                    if isinstance(value,dict):
                        if set(value)=={'$context_ref'}:
                            target=state
                            for key in value['$context_ref'].split('.'): target=target[key]
                            return deepcopy(target)
                        return {key:restore(item) for key,item in value.items()}
                    if isinstance(value,list): return [restore(item) for item in value]
                    return value
                self.assertEqual(restore(student),state['student_context'])
                self.assertEqual(state,before)
                for d in state['documents']:
                    self.assertIn(d.page_content,result.compact_text)
                    self.assertIn(str(d.metadata),result.compact_text)

    def test_other_cohort_version_and_storage_key_never_deduplicate(self):
        for field,value in [('cohort','cohort_other'),('storage_key','different-upload'),('document_hash','other-hash')]:
            state=fixture()
            policy=state['student_context']['data']['student_attendance']['unit_period_context']['policy_calculation']
            policy[field]=value
            result=build(state)
            self.assertFalse(result.references,field)
            self.assertEqual(result.compact_text,result.legacy_text)

    def test_different_numeric_subtree_is_kept(self):
        state=fixture()
        state['unit_period_context']['calendar_basis']['anchor_day']='different'
        result=build(state)
        self.assertNotIn(('student_context.data.student_attendance.unit_period_context.calendar_basis','unit_period_context.calendar_basis'),result.references)

    def test_legacy_mode_no_duplicates_and_small_payload(self):
        state=fixture(); result=build(state,'legacy')
        self.assertEqual(result.text,original(state))
        for shared,student in (({},{}),({'x':[1]}, {'data':{'student_attendance':{'unit_period_context':{'x':[1]}}}})):
            result=build_answer_context(unit_period_context=shared,student_context=student)
            self.assertEqual(result.compact_text,result.legacy_text)
            self.assertFalse(result.references)

    def test_metrics_are_explicit_estimates_and_contain_no_source_text(self):
        result=build(fixture())
        metrics=measure_answer_context(result,system='SECRET_SYSTEM',history=[],question='SECRET_QUESTION',
            tokenizer=LocalTokenizer(counter=len,status='available',reason='none'))
        self.assertGreater(metrics['saved_token_estimate'],0)
        self.assertEqual(metrics['legacy']['token_estimate'],metrics['legacy']['chars'])
        self.assertEqual(sum(v['chars'] for v in metrics['legacy']['categories']),metrics['legacy']['chars'])
        self.assertIn('metadata_chars',next(x for x in metrics['legacy']['evidence'] if x['category']=='policy'))
        metrics['question']='SECRET_QUESTION';metrics['legacy']['evil']='SECRET_DATA'
        clean=safe_context_metrics(metrics)
        self.assertNotIn('SECRET',json.dumps(clean))
        self.assertNotIn('cohort_34',json.dumps(clean))

    def test_missing_or_failed_tokenizer_has_no_fake_estimates(self):
        def broken(_): raise RuntimeError('unavailable')
        for tokenizer in (LocalTokenizer(),LocalTokenizer(counter=broken,status='available',reason='none')):
            report=measure_answer_context(build(fixture()),system='s',history=[],question='q',tokenizer=tokenizer)
            self.assertEqual(report['tokenizer_status'],'unavailable')
            self.assertNotIn('token_estimate',json.dumps(report))

    def test_answer_integration_and_log_preserve_usage_and_sources(self):
        state=fixture()
        class Capture:
            def stream(self,inputs,config):
                self.inputs=inputs
                yield AIMessageChunk(content='합성 답변',usage_metadata={'input_tokens':321,'output_tokens':4,'total_tokens':325})
        chain=Capture();bot=object.__new__(LmsStudentChatbot);bot.answer_chain=chain
        outputs=[]
        for mode in ('legacy','compact'):
            with patch.dict(os.environ,{'LMS_CHATBOT_CONTEXT_MODE':mode}):
                answer=bot._answer(state)
            self.assertEqual(chain.inputs['context'],build(state,mode).text)
            self.assertEqual(answer['token_in'],321)
            self.assertEqual(answer['context_metrics']['mode'],mode)
            outputs.append(answer)
        self.assertEqual(outputs[0]['sources'],outputs[1]['sources'])
        payload=build_generation_log_payload(cohort_id='test',created_by='synthetic',latency_ms=1,
            status='success',thread_id='test',snapshot=outputs[1])
        self.assertEqual(payload['contextMetrics']['mode'],'compact')
        self.assertNotIn(state['question'],json.dumps(payload,ensure_ascii=False))

    def test_runtime_requires_explicit_compact_opt_in(self):
        state=fixture()
        class Capture:
            def stream(self,inputs,config):
                self.inputs=inputs
                yield AIMessageChunk(content='offline')
        chain=Capture();bot=object.__new__(LmsStudentChatbot);bot.answer_chain=chain
        for value in (None,'unexpected'):
            with patch.dict(os.environ):
                if value is None: os.environ.pop('LMS_CHATBOT_CONTEXT_MODE',None)
                else: os.environ['LMS_CHATBOT_CONTEXT_MODE']=value
                result=bot._answer(state)
            self.assertEqual(result['context_metrics']['mode'],'legacy')
            self.assertEqual(chain.inputs['context'],original(state))
