"""Offline answer telemetry/config contracts; no provider requests or traces."""
import os
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

os.environ['LANGSMITH_TRACING'] = 'false'
os.environ['LANGCHAIN_TRACING_V2'] = 'false'

from langchain_core.messages import AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGenerationChunk
from langchain_openai import ChatOpenAI

from chatbot.ops_log import build_generation_log_payload
from chatbot.student_chatbot import (
    LmsStudentChatbot, _FirstAnswerTokenTimer, _answer_reasoning_options, _message_usage_details,
)


class VisibleTtftTests(TestCase):
    def test_nontext_callbacks_are_not_visible_text_and_existing_answer_is_preserved(self):
        clock = [100.0]
        class Chain:
            def stream(self, inputs, config):
                callback = config['callbacks'][0]
                for at, content in ((100.2, []), (101.0, [{'type': 'reasoning', 'summary': []}]),
                                    (108.0, '안내 문장.')):
                    clock[0] = at
                    chunk = AIMessageChunk(content=content)
                    callback.on_llm_new_token(content, chunk=ChatGenerationChunk(message=chunk))
                    yield chunk
                clock[0] = 110.0
                yield AIMessageChunk(content=[], usage_metadata={
                    'input_tokens': 100, 'output_tokens': 40, 'total_tokens': 140,
                    'input_token_details': {'cache_read': 20},
                    'output_token_details': {'reasoning': 30}})
        bot = object.__new__(LmsStudentChatbot)
        bot.answer_chain = Chain()
        deltas = []
        with patch('chatbot.student_chatbot.time.perf_counter', side_effect=lambda: clock[0]), \
             patch('chatbot.student_chatbot.get_stream_writer', return_value=deltas.append):
            result = bot._answer({'question': 'synthetic question',
                'messages': [HumanMessage(content='synthetic question')], 'unit_period_context': {'periods': []}})
        self.assertEqual(result['answer_ttft_ms'], 1000)  # Legacy nonempty callback.
        self.assertEqual(result['answer_first_callback_ms'], 200)
        self.assertEqual(result['answer_first_nonempty_callback_ms'], 1000)
        self.assertEqual(result['answer_first_model_event_ms'], 200)
        self.assertEqual(result['answer_visible_ttft_ms'], 8000)
        self.assertEqual(result['answer_model_ms'], 10000)
        self.assertEqual(result['answer'], '안내 문장.')
        self.assertEqual(deltas, [{'type': 'answer_delta', 'text': '안내 문장.'}])
        self.assertEqual(result['answer_reasoning_events'], 1)
        self.assertEqual(result['answer_reasoning_tokens'], 30)
        self.assertEqual(result['answer_cached_input_tokens'], 20)
        self.assertEqual((result['token_in'], result['token_out']), (100, 40))

    def test_no_model_text_does_not_invent_visible_ttft_or_usage(self):
        class Chain:
            def stream(self, inputs, config):
                yield AIMessageChunk(content=[])
        bot = object.__new__(LmsStudentChatbot)
        bot.answer_chain = Chain()
        result = bot._answer({'question': 'synthetic', 'messages': [HumanMessage(content='synthetic')],
                              'unit_period_context': {'periods': []}})
        self.assertIsNone(result['answer_visible_ttft_ms'])
        self.assertIsNone(result['answer_first_callback_ms'])
        self.assertIsNone(result['answer_reasoning_tokens'])
        self.assertIsNone(result['answer_cached_input_tokens'])
        self.assertIsNotNone(result['answer_first_model_event_ms'])
        payload = build_generation_log_payload(cohort_id='test', created_by='test',
            latency_ms=1, status='success', snapshot=result)
        self.assertNotIn('answerVisibleTtftMs', payload)
        self.assertNotIn('answerReasoningTokens', payload)

    def test_usage_details_support_responses_and_completion_metadata_without_text(self):
        for raw in (
            {'usage': {'output_tokens_details': {'reasoning_tokens': 8},
                       'input_tokens_details': {'cached_tokens': 9}}},
            {'token_usage': {'completion_tokens_details': {'reasoning_tokens': 8},
                            'prompt_tokens_details': {'cached_tokens': 9}}},
        ):
            self.assertEqual(_message_usage_details(SimpleNamespace(response_metadata=raw)),
                             {'reasoning_tokens': 8, 'cached_input_tokens': 9})
        message = SimpleNamespace(usage_metadata={
            'output_token_details': {'priority_reasoning': 0},
            'input_token_details': {'priority_cache_read': 12}})
        self.assertEqual(_message_usage_details(message), {'reasoning_tokens': 0, 'cached_input_tokens': 12})
        self.assertEqual(_message_usage_details(SimpleNamespace(usage_metadata={
            'output_token_details': {'reasoning': 'private text'},
            'input_token_details': {'cache_read': True}})), {})

    def test_default_options_are_omitted_and_supported_low_is_in_responses_payload(self):
        self.assertEqual(_answer_reasoning_options(None), {})
        self.assertEqual(_answer_reasoning_options(''), {})
        self.assertEqual(_answer_reasoning_options('   '), {})
        with patch('httpx.Client.send', side_effect=AssertionError('No provider request allowed')):
            default = ChatOpenAI(model='gpt-6-luna', api_key='synthetic-offline-key',
                                 use_responses_api=True, streaming=True, max_retries=0,
                                 **_answer_reasoning_options(None))
            low = ChatOpenAI(model='gpt-6-luna', api_key='synthetic-offline-key',
                             use_responses_api=True, streaming=True, max_retries=0,
                             **_answer_reasoning_options('low'))
            self.assertNotIn('reasoning', default._get_request_payload([HumanMessage(content='synthetic')]))
            self.assertEqual(low._get_request_payload([HumanMessage(content='synthetic')])['reasoning'],
                             {'effort': 'low'})
        with self.assertRaises(ValueError):
            _answer_reasoning_options('minimal')  # Not in GPT-6 Luna's documented set.

    def test_log_allowlist_keeps_numeric_metrics_and_config_enum_only(self):
        payload = build_generation_log_payload(cohort_id='test', created_by='test', latency_ms=1,
            status='success', snapshot={'answer_visible_ttft_ms': 8000, 'answer_first_callback_ms': 200,
                'answer_reasoning_tokens': 30, 'answer_cached_input_tokens': 20,
                'answer_reasoning_effort': 'low', 'reasoning': 'private reasoning',
                'question': 'private question', 'answer': 'private answer'})
        self.assertEqual(payload['answerVisibleTtftMs'], 8000)
        self.assertEqual(payload['answerReasoningEffort'], 'low')
        self.assertNotIn('private', str(payload))
