"""챗봇의 HTTP 경계. `POST /api/v1/jobs/chat`.

검색과 답이 맞는지는 `test_job_chat.py`가 본다. 여기서 보는 것은 **그 앞뒤 한 겹**,
즉 앱이 보낸 JSON이 요청 객체가 되기까지와 응답 객체가 JSON이 되기까지다.

이 한 겹이 지키는 약속 셋.

1. **앱이 보낸 값이 그대로 서비스에 닿는다.** 특히 `last_job_ids`는 순서가 곧 뜻이다.
   "2번"이 몇 번째인지가 여기서 어긋나면 엉뚱한 공고를 놓고 답한다.
2. **틀린 요청은 조용히 통과하지 않는다.** `StrictModel`이라 오타 난 필드는 무시되는
   대신 422가 된다. 필드 이름을 잘못 보내 놓고 기본값으로 동작하면 앱 쪽에서 원인을
   찾기 어렵다.
3. **저장소가 없으면 503이다.** 500으로 나가면 앱은 서버가 터진 것으로 읽는다. 공고
   저장소를 아직 안 만들었을 뿐이고, 그건 안내할 수 있는 상태다.
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from job_matching_bot.api import schemas
from job_matching_bot.api.service import StoreUnavailable


def _response(**kwargs) -> schemas.JobChatResponse:
    kwargs.setdefault("mode", "검색")
    kwargs.setdefault("reply", "서울 백엔드 8건이에요.")
    kwargs.setdefault("filters", schemas.ChatFilters(roles=["백엔드"], regions=["서울"]))
    kwargs.setdefault("total", 8)
    return schemas.JobChatResponse(**kwargs)


def _job(job_id="J1", **kwargs) -> schemas.JobChatJob:
    return schemas.JobChatJob(
        job_id=job_id,
        company=kwargs.pop("company", "1회사"),
        title=kwargs.pop("title", "백엔드 개발자"),
        source_url=kwargs.pop("source_url", "https://example.com/jobs/1"),
        region=kwargs.pop("region", "서울 강남구"),
        career=kwargs.pop("career", "신입"),
        employment_type=kwargs.pop("employment_type", "정규직"),
        **kwargs,
    )


class ChatEndpointTestCase(unittest.TestCase):
    """서비스는 가짜로 둔다. 넘어온 요청을 `self.received`에 남긴다."""

    def setUp(self):
        from job_matching_bot.api import main

        self.main = main
        self.original = main._chat
        self.received: schemas.JobChatRequest | None = None

    def tearDown(self):
        self.main._chat = self.original

    def serve(self, answer=None, raises=None, **client_kwargs) -> TestClient:
        test = self

        class FakeChat:
            def chat(self, request):
                test.received = request
                if raises is not None:
                    raise raises
                return answer if answer is not None else _response()

        self.main._chat = FakeChat()
        return TestClient(self.main.app, **client_kwargs)

    def post(self, body, **kwargs):
        return self.serve(**kwargs).post("/api/v1/jobs/chat", json=body)


class RequestTest(ChatEndpointTestCase):
    """앱이 보낸 JSON이 요청 객체가 되는 자리."""

    def test_a_message_alone_is_enough(self):
        """첫 질문에는 이어갈 조건도 앞서 보여 준 목록도 없다."""
        response = self.post({"message": "백엔드 찾아줘"})
        self.assertEqual(200, response.status_code)
        self.assertEqual("백엔드 찾아줘", self.received.message)
        self.assertIsNone(self.received.filters)
        self.assertIsNone(self.received.job_id)
        self.assertEqual([], self.received.last_job_ids)
        self.assertEqual(5, self.received.top_k, "안 보내면 다섯 건")

    def test_previous_filters_cross_the_boundary(self):
        """서버는 대화를 저장하지 않는다. 조건은 매 요청에 실려 와야 이어진다."""
        self.post({
            "message": "서울만",
            "filters": {"roles": ["백엔드"], "career": "신입"},
        })
        self.assertEqual(["백엔드"], self.received.filters.roles)
        self.assertEqual("신입", self.received.filters.career)

    def test_the_previous_list_keeps_its_order(self):
        """순서가 곧 "몇 번"이다. 뒤바뀌면 2번이 다른 공고가 된다."""
        self.post({"message": "2번 자세히 봐줘", "last_job_ids": ["J7", "J3", "J1"]})
        self.assertEqual(["J7", "J3", "J1"], self.received.last_job_ids)

    def test_a_tapped_card_and_a_resume_come_through(self):
        self.post({
            "message": "나한테 맞는 공고야?",
            "job_id": "SARAMIN-1",
            "resume_text": "Python으로 FastAPI 추천 API를 만들었습니다.",
        })
        self.assertEqual("SARAMIN-1", self.received.job_id)
        self.assertIn("FastAPI", self.received.resume_text)

    def test_a_misspelled_field_is_rejected_not_ignored(self):
        """`lastJobIds`로 보내면 조용히 빈 목록이 되어 "2번"이 먹통이 된다."""
        response = self.post({"message": "2번 자세히", "lastJobIds": ["J1", "J2"]})
        self.assertEqual(422, response.status_code)
        self.assertIsNone(self.received, "서비스까지 가지 않는다")

    def test_an_empty_message_is_rejected(self):
        self.assertEqual(422, self.post({"message": ""}).status_code)
        self.assertEqual(422, self.post({}).status_code)

    def test_top_k_stays_inside_the_range(self):
        """0건을 달라거나 스무 건을 넘겨 달라는 요청은 여기서 걸러진다."""
        self.assertEqual(422, self.post({"message": "백엔드", "top_k": 0}).status_code)
        self.assertEqual(422, self.post({"message": "백엔드", "top_k": 21}).status_code)
        self.assertEqual(200, self.post({"message": "백엔드", "top_k": 20}).status_code)

    def test_too_many_previous_jobs_are_rejected(self):
        response = self.post(
            {"message": "2번", "last_job_ids": [f"J{i}" for i in range(21)]}
        )
        self.assertEqual(422, response.status_code)


class ResponseTest(ChatEndpointTestCase):
    """응답 객체가 JSON이 되는 자리. 앱이 읽는 이름 그대로 나가야 한다."""

    def test_the_answer_reaches_the_app_whole(self):
        body = self.post({"message": "백엔드 찾아줘"}).json()
        self.assertEqual("검색", body["mode"])
        self.assertEqual("서울 백엔드 8건이에요.", body["reply"])
        self.assertEqual(8, body["total"])
        self.assertEqual(["백엔드"], body["filters"]["roles"])

    def test_jobs_carry_the_fields_the_card_draws(self):
        answer = _response(jobs=[_job(tech_stack=["Python", "FastAPI"])])
        body = self.post({"message": "백엔드 찾아줘"}, answer=answer).json()
        job = body["jobs"][0]
        self.assertEqual("J1", job["job_id"])
        self.assertEqual("1회사", job["company"])
        self.assertEqual("https://example.com/jobs/1", job["source_url"])
        self.assertEqual(["Python", "FastAPI"], job["tech_stack"])
        self.assertIsNone(job["deadline"], "마감일 없는 공고도 있다")

    def test_an_empty_result_is_still_a_well_formed_answer(self):
        """0건이라고 필드를 빼면 앱이 읽다 멈춘다."""
        answer = _response(reply="찾지 못했어요.", total=0, suggestions=["지역 상관없이"])
        body = self.post({"message": "제주 용접"}, answer=answer).json()
        self.assertEqual([], body["jobs"])
        self.assertEqual(0, body["total"])
        self.assertEqual(["지역 상관없이"], body["suggestions"])

    def test_the_mode_the_app_branches_on_survives(self):
        """비교·추천은 앱이 다르게 그린다. 여기서 뭉개지면 화면이 어긋난다."""
        for mode in ("검색", "질문", "공고", "비교", "추천", "안내"):
            with self.subTest(mode=mode):
                body = self.post({"message": "..."}, answer=_response(mode=mode)).json()
                self.assertEqual(mode, body["mode"])

    def test_the_resume_scope_comes_back_for_a_handoff(self):
        """추천으로 넘길 때 앱은 이 값만큼만 이력서를 보낸다."""
        answer = _response(mode="추천", resume_scope="프로젝트")
        body = self.post({"message": "내 프로젝트로 골라줘"}, answer=answer).json()
        self.assertEqual("프로젝트", body["resume_scope"])


class FailureTest(ChatEndpointTestCase):
    """못 하는 것은 못 한다고, 앱이 알아들을 수 있는 코드로 말한다."""

    def test_a_missing_store_is_503_with_a_reason(self):
        """서버가 터진 것이 아니라 공고 저장소가 없는 것이다. 앱이 안내할 수 있어야 한다."""
        raises = StoreUnavailable("공고 저장소가 없습니다: artifacts/jobs.sqlite")
        response = self.post({"message": "백엔드"}, raises=raises)
        self.assertEqual(503, response.status_code)
        self.assertIn("공고 저장소가 없습니다", response.json()["detail"])

    def test_an_unexpected_failure_does_not_leak_the_reason(self):
        """안에서 무엇이 터졌는지는 로그에 남길 것이지 앱에 보낼 것이 아니다."""
        response = self.post(
            {"message": "백엔드"},
            raises=ZeroDivisionError("내부 사정"),
            raise_server_exceptions=False,
        )
        self.assertEqual(500, response.status_code)
        self.assertNotIn("내부 사정", response.text)


if __name__ == "__main__":
    unittest.main()
