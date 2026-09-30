"""추천 검색 조건(build_filter, match_requirements)은 하드 필터가 떨어뜨릴 공고만 미리 뺀다.

검색 조건이 하드 필터보다 엄격하면 통과할 공고를 영영 못 본다. 공고 · 이력서를 여러 개 섞어
Pinecone 조건을 여기서 직접 풀어 보고, 조건이 뺀 공고는 하드 필터도 떨어뜨리는지 본다.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from itertools import product

from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.matching.hard_filter import EDUCATION_RANK, hard_filter
from job_matching_bot.retrieval import documents as doc
from job_matching_bot.retrieval.search import build_filter
from job_matching_bot.schemas.resume import ResumeProfile


def matches(meta: dict, condition: dict) -> bool:
    """Pinecone 메타데이터 조건을 푼다. 쓰는 연산자만."""
    for key, rule in condition.items():
        if key == "$and":
            if not all(matches(meta, c) for c in rule):
                return False
        elif key == "$or":
            if not any(matches(meta, c) for c in rule):
                return False
        else:
            value = meta.get(key)
            for op, want in rule.items():
                ok = {
                    "$eq": lambda: value == want,
                    "$ne": lambda: value != want,
                    "$in": lambda: (set(value) & set(want)) if isinstance(value, list) else value in want,
                    "$nin": lambda: value not in want,
                    "$lte": lambda: value is not None and value <= want,
                    "$gte": lambda: value is not None and value >= want,
                }[op]()
                if not ok:
                    return False
    return True


def resume(years: float, education: str) -> ResumeProfile:
    return ResumeProfile(resume_id="r", target_roles=["백엔드"], skills=["Java"], project_skills=["Java"],
                         preferred_regions=[], preferred_employment_types=[], education_level=education,
                         career_years=years, majors=[], certifications=[])


BASE = replace(mock_jobs()[0], status="OPEN", required_majors=[], required_major_terms=[],
               required_certifications=[], required_certification_groups=[], body_is_image=False)
JOBS = [
    replace(BASE, career_type=kind, min_career_years=years, education=education)
    for kind, years, education in product(
        ("ENTRY", "ANY", "EXPERIENCED"), (None, 0, 1, 2, 3, 5), (*EDUCATION_RANK, "미기재", "")
    )
]
RESUMES = [resume(y, e) for y, e in product((0, 0.2, 0.6, 1, 2, 2.5, 2.6, 3, 5, 10), (*EDUCATION_RANK, ""))]


class SearchFilterAgreesWithHardFilterTest(unittest.TestCase):
    def test_never_drops_what_the_hard_filter_would_keep(self):
        for r in RESUMES:
            condition = build_filter([], [], r.career_years, education_level=r.education_level, match_requirements=True)
            for job in JOBS:
                if matches(doc.to_metadata(job), condition):
                    continue
                if job.career_type != "EXPERIENCED" and r.career_years < 1 and (job.min_career_years or 0) > 1:
                    continue  # 예전부터 있던 신입 조건(연차 ≤ 1) — 이번 변경과 별개
                with self.subTest(years=r.career_years, education=r.education_level,
                                  job=(job.career_type, job.min_career_years, job.education)):
                    self.assertEqual("FAIL", hard_filter(job, r)["status"])

    def test_drops_what_used_to_waste_rerank_slots(self):
        """신입에게 연차 미기재 경력 공고 · 경력자에게 연차가 먼 공고 · 이력서보다 높은 학력."""
        entry = build_filter([], [], 0, education_level="대졸", match_requirements=True)
        self.assertFalse(matches(doc.to_metadata(replace(BASE, career_type="EXPERIENCED", min_career_years=None)), entry))
        senior = build_filter([], [], 2, education_level="대졸", match_requirements=True)
        self.assertFalse(matches(doc.to_metadata(replace(BASE, career_type="EXPERIENCED", min_career_years=5)), senior))
        self.assertTrue(matches(doc.to_metadata(replace(BASE, career_type="EXPERIENCED", min_career_years=None)), senior))
        college = build_filter([], [], 0, education_level="초대졸", match_requirements=True)
        self.assertFalse(matches(doc.to_metadata(replace(BASE, career_type="ANY", education="대졸")), college))
        self.assertTrue(matches(doc.to_metadata(replace(BASE, career_type="ANY", education="미기재")), college))

    def test_chat_search_is_unchanged(self):
        """채팅 검색은 추천 조건을 걸지 않는다(match_requirements 기본값 False)."""
        self.assertEqual({"$and": [{"status": {"$eq": "OPEN"}}, {"min_career_years": {"$lte": 1}}]},
                         build_filter([], [], 0))
        self.assertEqual({"status": {"$eq": "OPEN"}}, build_filter([], [], 5))


if __name__ == "__main__":
    unittest.main()
