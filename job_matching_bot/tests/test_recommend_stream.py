"""추천을 하면서 단계를 흘려보내는 경로.

추천은 15초쯤 걸린다. 한 번에 돌려주면 앱이 그동안 보여 줄 것이 막대 하나뿐이라
무엇이 진행 중인지 알 수 없었다. 그래서 단계가 바뀔 때마다 한 줄씩 내보낸다.

여기서 지키는 약속 셋.

1. **단계는 정해진 순서로 온다.** 앱이 그 순서로 줄을 세우므로 뒤바뀌면 안 된다.
2. **결과는 마지막에 한 번 온다.** 기존 응답과 같은 모양이라 앱이 그대로 읽는다.
3. **알림이 추천을 막지 않는다.** 듣는 쪽이 터져도 추천은 끝까지 간다.
"""

from __future__ import annotations

import json
import unittest

from fastapi.testclient import TestClient

from job_matching_bot.api import schemas
from job_matching_bot.api.service import RECOMMEND_STAGES, _progress_reporter


def _request() -> dict:
    return {
        "resume_text": "Python으로 FastAPI 추천 API를 만들었습니다. 벡터 검색도 붙였습니다.",
        "top_k": 3,
    }


def _events(response) -> list[dict]:
    """SSE 본문에서 `data:` 줄만 뽑아 파싱한다."""
    return [
        json.loads(line[len("data: "):])
        for line in response.text.split("\n\n")
        if line.startswith("data: ")
    ]


class ProgressReporterTest(unittest.TestCase):
    """알림은 곁다리다 — 실패해도 추천이 끝까지 가야 한다."""

    def test_no_callback_is_a_no_op(self):
        say = _progress_reporter(None)
        say("resume")
        say("resume", "끝")  # 아무 일도 일어나지 않으면 통과다

    def test_a_broken_listener_does_not_escape(self):
        def explode(stage, detail):
            raise RuntimeError("듣는 쪽이 터졌다")

        _progress_reporter(explode)("search", None)


class RecommendStreamTest(unittest.TestCase):
    """`/api/v1/jobs/recommend/stream`. 추천 자체는 가짜로 둔다."""

    def setUp(self):
        from job_matching_bot.api import main

        self.main = main
        self.original = main._service

    def tearDown(self):
        self.main._service = self.original

    def _serve(self, recommend):
        class FakeService:
            pass

        service = FakeService()
        service.recommend = recommend
        self.main._service = service
        return TestClient(self.main.app)

    def test_stages_arrive_in_order_and_the_result_comes_last(self):
        answer = schemas.RecommendResponse(
            recommendations=[],
            search_query="프론트엔드",
            profile_summary="",
            reranked=False,
            warnings=[],
        )

        def recommend(request, progress=None):
            for stage in RECOMMEND_STAGES:
                progress(stage, None)
                progress(stage, f"{stage} 끝")
            return answer

        response = self._serve(recommend).post("/api/v1/jobs/recommend/stream", json=_request())
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))

        events = _events(response)
        starts = [e["stage"] for e in events if e["event"] == "progress" and e["detail"] is None]
        self.assertEqual(list(RECOMMEND_STAGES), starts, "앱이 이 순서로 줄을 세운다")

        self.assertEqual("done", events[-1]["event"], "결과는 맨 마지막 한 번")
        self.assertEqual("프론트엔드", events[-1]["result"]["search_query"])
        self.assertEqual(1, sum(1 for e in events if e["event"] == "done"))

    def test_a_finished_stage_carries_a_line_to_show(self):
        """끝난 단계의 문구는 그대로 화면에 나간다. 비어 있으면 보여 줄 것이 없다."""

        def recommend(request, progress=None):
            progress("search", None)
            progress("search", "열린 공고에서 40건을 추렸어요")
            return schemas.RecommendResponse(
                recommendations=[], search_query="", profile_summary="",
                reranked=False, warnings=[],
            )

        response = self._serve(recommend).post("/api/v1/jobs/recommend/stream", json=_request())
        done = [e for e in _events(response) if e["event"] == "progress" and e["detail"]]
        self.assertEqual(["열린 공고에서 40건을 추렸어요"], [e["detail"] for e in done])

    def test_a_failure_arrives_as_an_event_not_a_dead_connection(self):
        """스트림은 이미 200으로 열려 있다. 상태 코드로는 실패를 알릴 수 없다."""
        from job_matching_bot.api.service import SearchUnavailable

        def recommend(request, progress=None):
            progress("resume", None)
            raise SearchUnavailable("공고 검색에 실패했습니다: TimeoutError")

        response = self._serve(recommend).post("/api/v1/jobs/recommend/stream", json=_request())
        self.assertEqual(200, response.status_code)
        last = _events(response)[-1]
        self.assertEqual("error", last["event"])
        self.assertIn("공고 검색에 실패", last["detail"])

    def test_an_unexpected_failure_does_not_leak_the_stack(self):
        def recommend(request, progress=None):
            raise ZeroDivisionError("내부 사정")

        response = self._serve(recommend).post("/api/v1/jobs/recommend/stream", json=_request())
        last = _events(response)[-1]
        self.assertEqual("error", last["event"])
        self.assertIn("ZeroDivisionError", last["detail"])
        self.assertNotIn("내부 사정", last["detail"])


if __name__ == "__main__":
    unittest.main()
