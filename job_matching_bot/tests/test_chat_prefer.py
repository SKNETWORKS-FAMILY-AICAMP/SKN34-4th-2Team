"""직무를 말하지 않은 검색 — 이력서의 희망 직무(없으면 개발 직군)를 앞에 둔다. 거르지는 않는다.

「대기업 공고」에 웹디자이너 · 물류 · 제품디자이너가 앞에 섰던 것을 고친다(2026-09-30).
저장소를 열지 않는다 — 검색 함수를 바꿔 끼워 무엇이 넘어가는지만 본다.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from job_matching_bot.api import schemas
from job_matching_bot.api.service import DEFAULT_PREFER_ROLES, ChatService
from job_matching_bot.retrieval import store_search
from job_matching_bot.retrieval.store_search import JobHit, SearchResult

RESUME = "백엔드 개발자를 지망합니다. Spring Boot 로 쇼핑몰 API 를 만들었습니다." * 2


def turn(**filters) -> schemas.ChatTurnOut:
    return schemas.ChatTurnOut(
        intent="검색", topic="채용", refers_to_last_answer=False, show_more=False, counts_jobs=True,
        requirement_query="", unavailable="", job_refs=[], filters=schemas.ChatFilters(**filters),
        understood="찾아볼게요.",
    )


def hit(job_id="J1") -> JobHit:
    return JobHit(job_id=job_id, company="가회사", title="백엔드 개발자", source_url="", region="서울",
                  career_label="신입", employment_type="정규직", deadline=None, tech_stack=[], relevance=0,
                  has_detail=True)


class PreferredRolesTest(unittest.TestCase):
    def setUp(self):
        self.profiled = []

        def profiler(values):
            self.profiled.append(values["resume_text"])
            return SimpleNamespace(target_roles=["백엔드 개발자", "API 개발자"])

        self.service = ChatService(generator=lambda values: self.turn, store_path=Path("store.sqlite"), profiler=profiler)

    def chat(self, out, resume_text=None):
        self.turn = out
        with patch.object(store_search, "search", return_value=SearchResult(jobs=[hit()], total=1, scanned_cap=False, strong=0)) as search, \
                patch.object(ChatService, "drop_dead", lambda self, ids: ids), \
                patch("job_matching_bot.api.service.store_available", return_value=True):
            response = self.service.chat(schemas.JobChatRequest(message="대기업 공고", resume_text=resume_text))
        return search.call_args.kwargs["prefer"], response

    def test_resume_roles_come_first_without_filtering(self):
        prefer, response = self.chat(turn(keywords=["대기업"]), resume_text=RESUME)
        self.assertEqual(prefer, ["백엔드 개발자", "API 개발자"])
        self.assertIn("이력서의 희망 직무(백엔드 개발자, API 개발자)", response.reply)

    def test_resume_is_structured_once(self):
        self.chat(turn(keywords=["대기업"]), resume_text=RESUME)
        self.chat(turn(keywords=["대기업"], regions=["서울"]), resume_text=RESUME)
        self.assertEqual(len(self.profiled), 1, "같은 이력서는 한 번만 구조화한다")

    def test_without_resume_dev_roles_come_first(self):
        prefer, response = self.chat(turn(keywords=["대기업"]))
        self.assertEqual(prefer, list(DEFAULT_PREFER_ROLES))
        self.assertIn("개발 직군", response.reply)

    def test_said_role_is_the_only_basis(self):
        prefer, response = self.chat(turn(keywords=["대기업"], roles=["데이터 분석"]), resume_text=RESUME)
        self.assertEqual(prefer, [])
        self.assertNotIn("직무를 말하지 않으셔서", response.reply)
        self.assertEqual(self.profiled, [], "직무를 말했으면 이력서를 구조화하지 않는다")

    def test_profiler_failure_falls_back_to_dev_roles(self):
        def broken(values):
            raise RuntimeError("down")

        self.service = ChatService(generator=lambda values: self.turn, store_path=Path("store.sqlite"), profiler=broken)
        prefer, _ = self.chat(turn(keywords=["대기업"]), resume_text=RESUME)
        self.assertEqual(prefer, list(DEFAULT_PREFER_ROLES))


class BigCompanyConditionTest(unittest.TestCase):
    """「대기업」으로 거르면, 사람인이 중견 · 중소로만 적은 회사의 잡코리아 공고를 뺀다."""

    def test_condition_is_added_only_for_big_companies(self):
        from datetime import datetime

        now = datetime(2026, 9, 30, tzinfo=store_search.KST)
        where, params = store_search.conditions(store_search.JobFilters(keywords=["대기업"]), now)
        self.assertTrue(any("JOBKOREA_POC" in clause and "bool_or" in clause for clause in where))
        where, _ = store_search.conditions(store_search.JobFilters(keywords=["중견기업"]), now)
        self.assertFalse(any("bool_or" in clause for clause in where))
        where, _ = store_search.conditions(store_search.JobFilters(keywords=["대기업"]), now, listing=True)
        self.assertFalse(any("bool_or" in clause for clause in where), "목록 공고에는 기업 정보가 없다")


if __name__ == "__main__":
    unittest.main()
