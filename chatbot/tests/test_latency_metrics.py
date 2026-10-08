from __future__ import annotations

import unittest
import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage

from chatbot.ops_log import build_generation_log_payload
from chatbot.api import ProxyChatRequest, proxy_chat
from chatbot.student_chatbot import LmsStudentChatbot


class FakeEmbeddings:
    def __init__(self) -> None:
        self.calls = 0

    def embed_query(self, query: str) -> list[float]:
        self.calls += 1
        return [0.1, 0.2]


class FakeIndex:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(matches=[SimpleNamespace(
            id="doc-1", score=0.9, metadata={"doc_id": "doc-1", "page_content": "본문"},
        )])


class FakeAnswerChain:
    def invoke(self, inputs: dict, config: dict) -> AIMessage:
        config["callbacks"][0].on_llm_new_token("답")
        return AIMessage(content="답변", usage_metadata={"input_tokens": 21, "output_tokens": 3, "total_tokens": 24})


class LatencyMetricsTests(unittest.TestCase):
    def test_namespace_search_counts_external_calls_without_recording_query(self) -> None:
        bot = object.__new__(LmsStudentChatbot)
        bot.k = 4
        bot.index = FakeIndex()
        bot.embeddings = FakeEmbeddings()
        state = {"query": "질문 원문", "cohort": "cohort_34", "namespaces": ["policy", "notice"]}

        with patch("chatbot.cohort_document_rag.active_policy_namespace", return_value="policy"):
            result = bot._retrieve_namespaces(state, ["policy", "notice"])

        self.assertEqual(result["embedding_calls"], 2)
        self.assertEqual(result["vector_calls"], 2)
        self.assertEqual(len(result["documents"]), 2)
        self.assertEqual(bot.embeddings.calls, 2)
        self.assertEqual(len(bot.index.calls), 2)
        self.assertTrue(all(call["include_metadata"] for call in bot.index.calls))
        self.assertEqual({call["namespace"] for call in bot.index.calls}, {"policy", "notice"})

    def test_answer_metrics_are_numeric_and_logs_exclude_plaintext(self) -> None:
        bot = object.__new__(LmsStudentChatbot)
        bot.answer_chain = FakeAnswerChain()
        result = bot._answer({
            "question": "질문 원문",
            "messages": [HumanMessage(content="질문 원문")],
            "documents": [Document(page_content="본문", metadata={"_namespace": "policy", "doc_id": "d1"})],
        })
        self.assertEqual(result["retrieved_chunks"], 1)
        self.assertEqual(result["retrieved_chunk_chars"], 2)
        self.assertGreater(result["prompt_chars"], 2)
        self.assertGreaterEqual(result["answer_model_ms"], 0)
        self.assertGreaterEqual(result["answer_ttft_ms"], 0)

        payload = build_generation_log_payload(
            cohort_id="34", created_by="uid", latency_ms=100,
            status="success", thread_id="thread", snapshot={
                "embedding_calls": 2,
                "vector_calls": 2,
                "prompt_chars": result["prompt_chars"],
                "retrieved_chunks": result["retrieved_chunks"],
                "question": "질문 원문",
            },
        )
        self.assertEqual(payload["embeddingCalls"], 2)
        self.assertEqual(payload["retrievedChunks"], 1)
        self.assertNotIn("질문 원문", str(payload))

    def test_proxy_collects_answer_and_persists_numeric_metrics(self) -> None:
        bot = SimpleNamespace(
            stream=lambda _inputs: iter(["첫", "답"]),
            ops_snapshot=lambda _inputs: {"supervisor_ms": 4, "embedding_calls": 2},
        )
        with (
            patch("chatbot.api.valid_proxy_token", return_value=True),
            patch("chatbot.api._session_from_uid", return_value={"uid": "demo", "cohort": "34"}),
            patch("chatbot.api._ready_chatbot", return_value=bot),
            patch("chatbot.api.write_generation_log") as write_log,
        ):
            response = proxy_chat(ProxyChatRequest(message="질문", uid="demo"), "test-token")
        self.assertEqual(response, {"answer": "첫답"})
        payload = write_log.call_args.args[1]
        self.assertEqual(payload["supervisorMs"], 4)
        self.assertEqual(payload["embeddingCalls"], 2)
        self.assertIn("firstTokenMs", payload)
        self.assertNotIn("질문", str(payload))


if __name__ == "__main__":
    unittest.main()
