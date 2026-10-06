"""코치에게 묻기 속도 장치 — 정확도를 바꾸지 않고 기다림만 줄이는 것들.

1. 답 글 흘려보내기: 마지막 답(`AgentAnswer` 도구 호출)의 `answer`만 흘린다. 중간 도구 호출은 흘리지 않는다.
2. 마감 확인 미리 하기: 찾은 순간 뒤에서 확인을 열고, 마무리는 그것이 끝나기를 기다린 뒤 확인한다.
3. 검색 하루 기억: 집계 · 10분 기억과 따로, 64개까지.
4. 같은 말은 가르기를 다시 하지 않는다: 운영 저장소에서, 직전 조건까지 같을 때만.
"""

from __future__ import annotations

import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from job_matching_bot.api import chat_agent, schemas
from job_matching_bot.api.service import ChatService, StageClock
from job_matching_bot.retrieval import store_search
from job_matching_bot.tests.test_job_chat import turn


def chunk(message_id, name=None, args="", index=0):
    return SimpleNamespace(id=message_id, tool_call_chunks=[{"name": name, "args": args, "index": index}], content=[])


class StreamTest(unittest.TestCase):
    def test_only_the_final_answer_text_flows(self):
        final = chat_agent.AgentAnswer(answer="816건 중 133건이에요.", job_ids=[], followups=[])
        events = [
            ("messages", (chunk("m1", "count_jobs", '{"roles":["백엔드"]}'), {})),
            ("values", {"messages": []}),
            ("messages", (chunk("m2", "AgentAnswer", ""), {})),
            ("messages", (chunk("m2", None, '{"answer": "816건 중'), {})),
            ("messages", (chunk("m2", None, ' 133건이에요.", "job_ids": []'), {})),
            ("values", {"messages": [], "structured_response": final}),
        ]
        agent = SimpleNamespace(stream=lambda payload, stream_mode: iter(events))
        pieces, stages = [], []
        clock = StageClock(progress=lambda stage, _d: stages.append(stage), on_text=pieces.append)
        state = chat_agent._stream(agent, {}, clock)
        self.assertEqual("816건 중 133건이에요.", "".join(pieces))
        self.assertNotIn("roles", "".join(pieces), "도구 고르는 호출은 흘리지 않는다")
        self.assertIs(final, state["structured_response"])
        self.assertIn("answer", stages, "답을 쓰기 시작할 때 「답을 쓰는 중」")


def card(hit) -> schemas.JobChatJob:
    return schemas.JobChatJob(job_id=hit.job_id, company="", title="", source_url="", region="", career="",
                              employment_type="", deadline=None, tech_stack=[])


class PrefetchTest(unittest.TestCase):
    def test_final_check_waits_for_the_prefetch(self):
        order = []

        def slow():
            time.sleep(0.2)
            order.append("미리")

        thread = threading.Thread(target=slow)
        thread.start()
        collected = chat_agent.Collected(hits={"J1": SimpleNamespace(job_id="J1")}, prefetch=[thread])
        service = SimpleNamespace(drop_dead=lambda ids: order.append("마무리") or set(ids))
        agent = SimpleNamespace(invoke=lambda payload: {"structured_response": chat_agent.AgentAnswer(answer="답", job_ids=["J1"])})
        with mock.patch.object(chat_agent, "Collected", return_value=collected), \
                mock.patch.object(chat_agent, "build_tools", return_value=[]), \
                mock.patch("job_matching_bot.api.service._to_chat_job", side_effect=card):
            response = chat_agent.answer(
                service, schemas.JobChatRequest(message="질문"), SimpleNamespace(filters=schemas.ChatFilters()),
                StageClock(), agent_factory=lambda tools: agent,
            )
        self.assertEqual(["미리", "마무리"], order)
        self.assertEqual("답", response.reply)


class SearchDayCacheTest(unittest.TestCase):
    def setUp(self):
        store_search._search_cache.clear()

    def test_lasts_a_day_and_is_capped(self):
        calls = []
        key = ("search", "백엔드")
        store_search.remember_search(key, lambda: calls.append(1) or "결과")
        store_search.remember_search(key, lambda: calls.append(1) or "결과")
        self.assertEqual(1, len(calls))
        for i in range(store_search._SEARCH_MAX + 5):
            store_search.remember_search(("search", i), lambda: i)
        self.assertEqual(store_search._SEARCH_MAX, len(store_search._search_cache))


class RouteCacheTest(unittest.TestCase):
    def service(self, store: str):
        self.calls = []
        out = turn(roles=["백엔드"])
        return ChatService(generator=lambda values: self.calls.append(values) or out, store_path=Path(store))

    def test_same_message_same_conditions_is_routed_once(self):
        service = self.service("artifacts/job_store.sqlite")
        previous = schemas.ChatFilters()
        service._route(previous, "서울 백엔드 신입")
        service._route(previous, " 서울 백엔드 신입 ")
        self.assertEqual(1, len(self.calls))
        service._route(schemas.ChatFilters(regions=["부산"]), "서울 백엔드 신입")
        self.assertEqual(2, len(self.calls), "직전 조건이 다르면 다시 가른다")

    def test_test_stores_are_not_cached(self):
        service = self.service("tmp/store.sqlite")
        service._route(schemas.ChatFilters(), "안녕")
        service._route(schemas.ChatFilters(), "안녕")
        self.assertEqual(2, len(self.calls))


if __name__ == "__main__":
    unittest.main()
