"""필터로 공고를 찾는 창구. `POST /api/v1/jobs/search`.

자기소개서 탭이 쓴다. 챗봇 검색(`/jobs/chat`)과 저장소 조회는 같지만 **말을 해석하지
않는다** — 사용자가 필터를 손으로 골랐으니 옮길 말이 없다. 그래서 여기서 지키는
약속은 챗봇 쪽과 다르다.

1. **LLM을 부르지 않는다.** 이 화면은 즐겨찾기에 담을 공고를 고르는 자리다. 조건을
   조금씩 바꿔 가며 여러 번 누르는데 그때마다 몇 초를 기다릴 이유가 없다.
2. **마감된 공고는 목록에 없다.** 즐겨찾기에 담고 나서 자기소개서를 쓸 때가 되어서야
   "이미 닫힌 공고"라고 막히면 늦다. 담기 전에 거른다.
3. **조건이 비면 아무것도 주지 않는다.** 빈 필터로 전체를 훑으면 수만 건이 걸린다.
   찾고 싶은 게 없는 상태는 "전부 보여 달라"가 아니다.
4. **본문 없는 공고도 주되 표시한다.** 목록에서만 본 공고는 자기소개서를 쓸 근거가
   없다. 빼 버리면 사용자는 왜 안 보이는지 모르므로, 보여 주고 `has_detail`로 알린다.
"""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from job_matching_bot.api import schemas
from job_matching_bot.api.service import ChatService, StoreUnavailable
from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.ingestion.sqlite_store import SqliteJobStore


class _NoLiveness:
    """사이트를 열어 보지 않는다. 확인이 실패한 것과 같게 전부 살아 있는 것으로 둔다."""

    def alive(self, job_ids):
        return list(job_ids)


class SearchJobsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "store.sqlite"
        base = mock_jobs()[0]
        jobs = [
            replace(
                base,
                job_id="A",
                source_job_id="A",
                company="가회사",
                title="백엔드 개발자",
                description="Python으로 API를 만듭니다",
                tech_stack=["Python", "FastAPI"],
                keywords=["IT개발·데이터"],
                region="서울 강남구",
                career_type="ENTRY",
                min_career_years=None,
                employment_type="정규직",
                deadline=None,
                status="OPEN",
            ),
            replace(
                base,
                job_id="B",
                source_job_id="B",
                company="나회사",
                title="프론트엔드 개발자",
                description="React로 화면을 만듭니다",
                tech_stack=["React"],
                keywords=["IT개발·데이터"],
                region="서울 마포구",
                career_type="ENTRY",
                min_career_years=None,
                employment_type="정규직",
                deadline=None,
                status="OPEN",
            ),
            replace(
                base,
                job_id="C",
                source_job_id="C",
                company="다회사",
                title="백엔드 개발자 (마감)",
                description="Python 서버를 만듭니다",
                tech_stack=["Python"],
                keywords=["IT개발·데이터"],
                region="서울 금천구",
                career_type="ENTRY",
                min_career_years=None,
                employment_type="정규직",
                deadline="2020-01-01",
                status="OPEN",
            ),
        ]
        with SqliteJobStore(self.path) as store:
            store.upsert(jobs, source="MOCK")
        self.service = ChatService(store_path=self.path)
        self.service._liveness = _NoLiveness()

    def tearDown(self):
        self.temp.cleanup()

    def search(self, **kwargs):
        top_k = kwargs.pop("top_k", 20)
        seen = kwargs.pop("seen_job_ids", [])
        return self.service.search_jobs(
            schemas.JobSearchRequest(
                filters=schemas.ChatFilters(**kwargs), top_k=top_k, seen_job_ids=seen
            )
        )

    def test_finds_by_role(self):
        result = self.search(roles=["백엔드"])
        self.assertEqual(["A"], [job.job_id for job in result.jobs])

    def test_drops_expired_job(self):
        """마감일이 지난 공고는 저장소가 OPEN이라고 해도 목록에 없다."""
        ids = [job.job_id for job in self.search(skills=["Python"]).jobs]
        self.assertIn("A", ids)
        self.assertNotIn("C", ids)

    def test_empty_filters_return_nothing(self):
        result = self.search()
        self.assertEqual([], result.jobs)
        self.assertEqual(0, result.total)

    def test_seen_ids_are_excluded(self):
        """다음 쪽. 이미 본 공고를 빼고 준다."""
        first = self.search(keywords=["개발자"], top_k=1)
        self.assertEqual(1, len(first.jobs))
        second = self.search(
            keywords=["개발자"], top_k=1, seen_job_ids=[first.jobs[0].job_id]
        )
        self.assertNotEqual(first.jobs[0].job_id, second.jobs[0].job_id)

    def test_summary_tells_what_was_filtered(self):
        """해석이 틀렸으면 사용자가 알아채야 한다."""
        self.assertIn("백엔드", self.search(roles=["백엔드"], regions=["서울"]).summary)

    def test_missing_store_raises_store_unavailable(self):
        service = ChatService(store_path=Path(self.temp.name) / "없는파일.sqlite")
        with self.assertRaises(StoreUnavailable):
            service.search_jobs(
                schemas.JobSearchRequest(filters=schemas.ChatFilters(roles=["백엔드"]))
            )


class SearchEndpointTest(unittest.TestCase):
    """HTTP 경계 한 겹. 앱이 보낸 JSON이 요청 객체가 되기까지."""

    def setUp(self):
        from job_matching_bot.api import main

        self.main = main
        self.original = main._chat
        self.received: schemas.JobSearchRequest | None = None

    def tearDown(self):
        self.main._chat = self.original

    def _stub(self, result=None, error=None):
        test = self

        class Stub:
            def search_jobs(self, request):
                test.received = request
                if error is not None:
                    raise error
                return result

        self.main._chat = Stub()
        return TestClient(self.main.app)

    def test_passes_filters_through(self):
        client = self._stub(
            schemas.JobSearchResponse(jobs=[], total=0, summary="백엔드 · 서울")
        )
        response = client.post(
            "/api/v1/jobs/search",
            json={"filters": {"roles": ["백엔드"], "regions": ["서울"]}, "top_k": 5},
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual(["백엔드"], self.received.filters.roles)
        self.assertEqual(5, self.received.top_k)

    def test_unknown_field_is_rejected(self):
        """오타 난 필드는 조용히 무시되지 않는다. 앱에서 원인을 찾기 어려워진다."""
        client = self._stub(schemas.JobSearchResponse(jobs=[], total=0))
        response = client.post(
            "/api/v1/jobs/search", json={"filters": {"roles": ["백엔드"]}, "topK": 5}
        )
        self.assertEqual(422, response.status_code)

    def test_missing_store_is_503(self):
        """500으로 나가면 앱은 서버가 터진 것으로 읽는다. 안내할 수 있는 상태다."""
        client = self._stub(error=StoreUnavailable("공고 저장소가 없습니다."))
        response = client.post(
            "/api/v1/jobs/search", json={"filters": {"roles": ["백엔드"]}}
        )
        self.assertEqual(503, response.status_code)


if __name__ == "__main__":
    unittest.main()
