"""공고 대화를 만드는 동안 흘려보내는 경로(`/api/v1/jobs/chat/stream`).

답 하나가 5~20초 걸린다. 화면이 정해 둔 문구만 돌리지 않도록 실제로 하는 일과 쓰는 글을 보낸다.

여기서 지키는 약속.

1. **단계는 시작할 때 온다.** 검색이면 가르기 → 조건 조회 → 마감 확인, 질문이면 가르기 → 집계 → 답 쓰기.
2. **글 조각은 LLM 이 쓰는 답에만 온다.** 공고 검색 답은 정해진 틀이라 흘려보낼 글이 없다.
3. **조각을 이으면 최종 답과 같다.** 화면은 다 받으면 `done`의 답으로 바꿔 끼운다.
4. **결과는 마지막에 한 번, 실패는 이벤트로 온다.**
"""

from __future__ import annotations

import json
import unittest

from fastapi.testclient import TestClient

from job_matching_bot.api import schemas
from job_matching_bot.api.service import CHAT_PROGRESS_LABELS
from job_matching_bot.tests.test_job_chat import ChatTestCase, answer, turn


class StreamingAnswerer:
    """쓰는 동안 두 조각을 넘기는 가짜 답. 한 번에 부르면 틀린 것이다."""

    def __init__(self, pieces):
        self.pieces = pieces

    def __call__(self, values):
        raise AssertionError("스트리밍 요청인데 한 번에 불렀다")

    def stream(self, values, on_text):
        for piece in self.pieces:
            on_text(piece)
        return answer("".join(self.pieces))


class ServiceStreamTest(ChatTestCase):
    def _chat(self, out, message, **kwargs):
        service = self.service(out)
        service._adviser = StreamingAnswerer(["백엔드 신입은 ", "API 하나를 끝까지 만들어 보세요."])
        stages, texts = [], []
        result = service.chat(
            schemas.JobChatRequest(message=message, **kwargs),
            progress=lambda stage, _detail: stages.append(stage),
            on_text=texts.append,
        )
        return result, stages, texts

    def test_a_question_announces_its_stages_and_streams_the_answer(self):
        result, stages, texts = self._chat(turn(intent="질문", roles=["백엔드"]), "백엔드 신입은 뭘 준비해?")
        self.assertEqual(["route", "stats", "answer"], stages)
        self.assertEqual(["백엔드 신입은 ", "API 하나를 끝까지 만들어 보세요."], texts)
        self.assertEqual("".join(texts), result.reply, "조각을 이으면 최종 답이다")

    def test_a_search_announces_its_stages_but_has_no_text(self):
        result, stages, texts = self._chat(turn(roles=["백엔드"]), "백엔드 찾아줘")
        self.assertEqual("검색", result.mode)
        self.assertEqual(["route", "search", "liveness"], stages)
        self.assertEqual([], texts)

    def test_without_listeners_the_answer_is_written_in_one_go(self):
        """예전 경로(`/jobs/chat`)는 그대로다 — 가짜 답의 `stream`을 부르지 않는다."""
        service = self.service(turn(intent="질문", roles=["백엔드"]))
        result = service.chat(schemas.JobChatRequest(message="백엔드 신입은 뭘 준비해?"))
        self.assertEqual("질문", result.mode)

    def test_a_broken_listener_does_not_stop_the_answer(self):
        service = self.service(turn(intent="질문", roles=["백엔드"]))
        service._adviser = StreamingAnswerer(["끝까지 ", "씁니다."])

        def explode(*_args):
            raise RuntimeError("듣는 쪽이 끊겼다")

        result = service.chat(
            schemas.JobChatRequest(message="뭘 준비해?"), progress=explode, on_text=explode
        )
        self.assertEqual("끝까지 씁니다.", result.reply)


def _events(response) -> list[dict]:
    return [
        json.loads(line[len("data: "):])
        for line in response.text.split("\n\n")
        if line.startswith("data: ")
    ]


class ChatStreamEndpointTest(unittest.TestCase):
    """`/api/v1/jobs/chat/stream`. 대화 자체는 가짜로 둔다."""

    def setUp(self):
        from job_matching_bot.api import main

        self.main = main
        self.original = main._chat

    def tearDown(self):
        self.main._chat = self.original

    def _serve(self, chat):
        class FakeChat:
            pass

        fake = FakeChat()
        fake.chat = chat
        self.main._chat = fake
        return TestClient(self.main.app)

    def test_progress_text_and_result_arrive_in_order(self):
        def chat(request, progress=None, on_text=None):
            progress("route", None)
            progress("answer", None)
            on_text("준비할 것은 ")
            on_text("셋입니다.")
            return schemas.JobChatResponse(
                mode="질문", reply="준비할 것은 셋입니다.", filters=schemas.ChatFilters(), total=0
            )

        response = self._serve(chat).post("/api/v1/jobs/chat/stream", json={"message": "뭘 준비해?"})
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))

        events = _events(response)
        self.assertEqual(["progress", "progress", "text", "text", "done"], [e["event"] for e in events])
        self.assertEqual(CHAT_PROGRESS_LABELS["route"], events[0]["label"], "화면은 이 말을 그대로 띄운다")
        self.assertEqual("준비할 것은 셋입니다.", events[-1]["result"]["reply"])

    def test_a_failure_arrives_as_an_event_without_the_stack(self):
        def chat(request, progress=None, on_text=None):
            raise KeyError("secret-internal-name")

        events = _events(self._serve(chat).post("/api/v1/jobs/chat/stream", json={"message": "뭘 준비해?"}))
        self.assertEqual("error", events[-1]["event"])
        self.assertNotIn("secret-internal-name", events[-1]["detail"])
