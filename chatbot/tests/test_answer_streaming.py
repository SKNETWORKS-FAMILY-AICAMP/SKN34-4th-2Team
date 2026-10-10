from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import TestCase
from langchain_core.messages import AIMessageChunk
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from chatbot.student_chatbot import LmsStudentChatbot, ChatState


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
