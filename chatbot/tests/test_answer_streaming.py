from concurrent.futures import ThreadPoolExecutor
from threading import Event
import json
import os
from unittest import TestCase
from unittest.mock import patch

# Offline graph tests must not export traces even when local .env enables it.
os.environ['LANGSMITH_TRACING'] = 'false'
os.environ['LANGCHAIN_TRACING_V2'] = 'false'

from langchain_core.messages import AIMessage, AIMessageChunk
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from chatbot import api
from chatbot.student_chatbot import LmsStudentChatbot, ChatState, _FirstAnswerTokenTimer


class AnswerStreamingTests(TestCase):
    def bot(self, chain):
        bot=object.__new__(LmsStudentChatbot)
        bot.answer_chain=chain
        builder=StateGraph(ChatState)
        builder.add_node('answer',bot._answer)
        builder.add_edge(START,'answer'); builder.add_edge('answer',END)
        bot.graph=builder.compile(checkpointer=InMemorySaver())
        return bot

    def inputs(self):
        return {'question':'내 출석','thread_id':'stream-test','cohort':'cohort_34',
                'student_uid':'test','unit_period_context':{'periods':[]}}

    def test_first_text_arrives_before_model_completion_and_final_state_is_whole(self):
        release=Event(); finished=Event()
        class Chain:
            def stream(self, inputs, config):
                yield AIMessageChunk(content=[{'type':'reasoning','summary':[{'type':'summary_text','text':'internal'}]}])
                yield AIMessageChunk(content='첫 문장. ')
                if not release.wait(5): raise TimeoutError('Consumer did not receive first text')
                yield AIMessageChunk(content='다음 문장.',usage_metadata={'input_tokens':10,'output_tokens':5,'total_tokens':15})
                finished.set()
        bot=self.bot(Chain()); stream=bot.stream(self.inputs())
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(next,stream)
            try:
                self.assertEqual(future.result(timeout=4),'첫 문장. ')
                self.assertFalse(finished.is_set())
            finally:
                release.set()
        self.assertEqual(list(stream),['다음 문장.'])
        state=bot.graph.get_state({'configurable':{'thread_id':'stream-test'}}).values
        self.assertEqual(state['answer'],'첫 문장. 다음 문장.')
        self.assertEqual(state['token_in'],10)
        self.assertNotIn('internal',state['answer'])

    def test_stream_error_propagates_after_partial_answer_without_repeating(self):
        class Chain:
            def stream(self, inputs, config):
                yield AIMessageChunk(content='일부 답변')
                raise RuntimeError('failed')
        stream=self.bot(Chain()).stream(self.inputs())
        self.assertEqual(next(stream),'일부 답변')
        with self.assertRaises(RuntimeError): next(stream)

    def test_no_generated_text_uses_single_fallback(self):
        class Chain:
            def stream(self, inputs, config):
                yield AIMessageChunk(content='')
        chunks=list(self.bot(Chain()).stream(self.inputs()))
        self.assertEqual(len(chunks),1)
        self.assertIn('답변을 생성하지 못했습니다',chunks[0])

    def test_responses_blocks_reach_ndjson_before_completion_without_message_callbacks(self):
        # Exercise the installed SDK conversion, not hand-written text chunks.
        # No ChatOpenAI client, network or provider callback is involved.
        from openai.types.responses import ResponseTextDeltaEvent, ResponseReasoningSummaryTextDeltaEvent
        from langchain_openai.chat_models.base import _convert_responses_chunk_to_generation_chunk

        release, finished = Event(), Event()
        events = [
            ResponseReasoningSummaryTextDeltaEvent(type='response.reasoning_summary_text.delta',
                delta='synthetic internal reasoning', item_id='reasoning-1', output_index=0,
                summary_index=0, sequence_number=1),
            ResponseTextDeltaEvent(type='response.output_text.delta', delta='첫 문장. ',
                item_id='answer-1', output_index=1, content_index=0, sequence_number=2, logprobs=[]),
            ResponseTextDeltaEvent(type='response.output_text.delta', delta='다음 문장.',
                item_id='answer-1', output_index=1, content_index=0, sequence_number=3, logprobs=[]),
        ]
        class Chain:
            def stream(self, inputs, config):
                indexes = (-1, -1, -1)
                for number, event in enumerate(events):
                    *indexes, generation = _convert_responses_chunk_to_generation_chunk(
                        event, *indexes, output_version='responses/v1')
                    yield generation.message
                    if number == 1 and not release.wait(5):
                        raise TimeoutError('Consumer did not receive first text')
                yield AIMessageChunk(content=[], chunk_position='last', usage_metadata={
                    'input_tokens': 12, 'output_tokens': 8, 'total_tokens': 20})
                finished.set()
        bot = self.bot(Chain())
        inputs = self.inputs()
        stream = api._ndjson_chat(bot, inputs, {'uid': 'test', 'cohort': 'cohort_34'})
        with patch.object(api, 'write_generation_log', return_value='synthetic-log') as log:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(next, stream)
                try:
                    first = json.loads(future.result(timeout=4))
                    self.assertEqual(first, {'type': 'token', 'content': '첫 문장. '})
                    self.assertFalse(finished.is_set())
                    log.assert_not_called()
                finally:
                    release.set()
            remaining = [json.loads(line) for line in stream]
        self.assertTrue(finished.is_set())
        self.assertEqual(remaining[0], {'type': 'token', 'content': '다음 문장.'})
        self.assertEqual([event['type'] for event in remaining], ['token', 'done'])
        state = bot.graph.get_state({'configurable': {'thread_id': 'stream-test'}}).values
        self.assertEqual(first['content'] + remaining[0]['content'], state['answer'])
        self.assertNotIn('synthetic internal reasoning', state['answer'])
        self.assertEqual(state['token_in'], 12)
        self.assertEqual(state['token_out'], 8)
        self.assertIn('firstTokenMs', log.call_args.args[1])
        log.assert_called_once()

    def test_legacy_messages_filter_falls_back_when_only_final_ai_message_is_delivered(self):
        # Reproduce the old boundary under absent graph-token callbacks. This
        # establishes the failure mechanism, not the provider's reason for
        # withholding callbacks in a particular live run.
        clock = [100.0]
        timer = _FirstAnswerTokenTimer(clock[0])
        class InvokeOnlyChain:
            def invoke(self, inputs, config):
                clock[0] += 1
                config['callbacks'][0].on_llm_new_token('첫 문장. ')
                clock[0] += 4
                return AIMessage(content='첫 문장. 다음 문장.')
        chain = InvokeOnlyChain()
        def old_answer(state):
            response = chain.invoke({}, config={'callbacks': [timer]})
            return {'answer': response.text, 'messages': [AIMessage(content=response.text)]}
        builder = StateGraph(ChatState)
        builder.add_node('answer', old_answer)
        builder.add_edge(START, 'answer'); builder.add_edge('answer', END)
        graph = builder.compile(checkpointer=InMemorySaver())
        bot = object.__new__(LmsStudentChatbot)
        graph_input, config = bot._prepare_call(self.inputs())
        with patch('chatbot.student_chatbot.time.perf_counter', side_effect=lambda: clock[0]):
            delivered = list(graph.stream(graph_input, config, stream_mode='messages'))
        eligible = [message.text for message, metadata in delivered
                    if metadata.get('langgraph_node') == 'answer'
                    and isinstance(message, AIMessageChunk) and message.text]
        self.assertFalse(eligible)
        self.assertTrue(any(isinstance(message, AIMessage) and not isinstance(message, AIMessageChunk)
                            for message, _ in delivered))
        self.assertEqual(timer.first_token_ms, 1000)
        self.assertEqual(clock[0], 105.0)
        self.assertEqual(graph.get_state(config).values['answer'], '첫 문장. 다음 문장.')
