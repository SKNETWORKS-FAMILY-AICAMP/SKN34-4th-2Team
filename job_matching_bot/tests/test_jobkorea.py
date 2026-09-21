"""잡코리아 정규화 검증.

실제 수집본(`artifacts/job_raw/JOBKOREA_POC/details.jsonl`)이 있으면 그것으로도
확인한다. 없으면 파싱 규칙만 본다.
"""

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from job_matching_bot.config import ARTIFACTS_DIR
from job_matching_bot.ingestion.jobkorea import (
    CLOSED_MARKER,
    is_closed_page,
    is_parsable,
    normalize_jobkorea,
    parse_skills,
)

KST = timezone(timedelta(hours=9))
AS_OF = datetime(2026, 9, 19, 12, 0, tzinfo=KST)

DETAILS = ARTIFACTS_DIR / "job_raw" / "JOBKOREA_POC" / "details.jsonl"


def _record(**overrides):
    record = {
        "source": "JOBKOREA_POC",
        "source_job_id": "50018510",
        "source_url": "https://www.jobkorea.co.kr/Recruit/GI_Read/50018510",
        "title": "AI사업팀 개발자 채용",
        "company": "㈜싸이웰시스템",
        "description": "담당업무\nㆍRPA 개발\n자격요건\nㆍPython 개발 가능자\n",
        "conditions": {
            "경력": "신입·경력",
            "학력": "초대졸 이상",
            "근무형태": "정규직, 인턴",
            "근무지역": "서울 강서구 양천로 547",
        },
        "posted_at": "2026-09-18",
        "deadline_raw": "2026-10-02T23:59",
        "image_body": False,
        "closed": False,
        "list_item": {"job_sectors": ["솔루션", "WAS"]},
    }
    record.update(overrides)
    return record


class ClosedMarkerTest(unittest.TestCase):
    """2026-09-19 표본 21건(마감 11 / 열림 10)으로 고른 문구를 지킨다."""

    def test_closed_phrase(self):
        self.assertTrue(is_closed_page(f"접수기간 · 방법 {CLOSED_MARKER} 시작일 2026.07.16"))

    def test_open_page_mentions_deadline_but_is_not_closed(self):
        # 열린 공고에도 "마감"은 계속 나온다. 표본 10건 중 9건이 그랬다.
        for text in (
            "마감일은 기업의 사정으로 인해 조기 마감 또는 변경될 수 있습니다",
            "마감일 2026.10.24(토)",
            "근무시간 10:00 ~ 22:00 오픈 9:30 ~ 21:30 or 마감 10:30~22:30",
        ):
            with self.subTest(text=text):
                self.assertFalse(is_closed_page(text))


class ParsableTest(unittest.TestCase):
    def test_headhunting_without_json_ld_is_rejected(self):
        # 헤드헌팅 공고는 JSON-LD가 없어 제목이 비어 온다.
        self.assertFalse(is_parsable(_record(title="")))

    def test_normal_record_is_accepted(self):
        self.assertTrue(is_parsable(_record()))


class SkillBlockTest(unittest.TestCase):
    def test_reads_skill_section(self):
        body = "담당업무\nㆍ개발\n스킬\nㆍPython, RAG, LLM\n핵심역량\nㆍ성실성\n"
        self.assertEqual(parse_skills(body), ["Python", "RAG", "LLM"])

    def test_no_skill_section(self):
        self.assertEqual(parse_skills("담당업무\nㆍ개발\n"), [])


class NormalizeTest(unittest.TestCase):
    def test_basic_fields(self):
        job = normalize_jobkorea(_record(), as_of=AS_OF)
        self.assertEqual(job.job_id, "JOBKOREA-50018510")
        self.assertEqual(job.source, "JOBKOREA_POC")
        self.assertEqual(job.career_type, "ANY")
        self.assertEqual(job.education, "초대졸")
        self.assertEqual(job.employment_type, "정규직")
        self.assertEqual(job.status, "OPEN")

    def test_deadline_comes_from_json_ld_not_text(self):
        job = normalize_jobkorea(_record(), as_of=AS_OF)
        self.assertEqual(job.deadline, "2026-10-02T23:59")
        self.assertEqual(job.posted_at, "2026-09-18")
        self.assertEqual(job.field_provenance["deadline"], "json_ld.validThrough")

    def test_past_deadline_is_expired(self):
        job = normalize_jobkorea(_record(deadline_raw="2026-08-15T23:59"), as_of=AS_OF)
        self.assertEqual(job.status, "EXPIRED")

    def test_source_saying_closed_wins_over_future_deadline(self):
        # 마감일이 남아 있어도 기업이 조기 마감할 수 있다.
        job = normalize_jobkorea(_record(closed=True), as_of=AS_OF)
        self.assertEqual(job.status, "CLOSED")


@unittest.skipUnless(DETAILS.exists(), "수집본이 없으면 건너뛴다")
class RealSampleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with DETAILS.open(encoding="utf-8") as handle:
            cls.records = [json.loads(line) for line in handle if line.strip()][:200]

    def test_every_parsable_record_normalizes(self):
        for record in self.records:
            if not is_parsable(record):
                continue
            with self.subTest(gno=record.get("source_job_id")):
                job = normalize_jobkorea(record, as_of=AS_OF)
                self.assertTrue(job.job_id.startswith("JOBKOREA-"))
                self.assertTrue(job.company)
                self.assertTrue(job.title)
                self.assertIn(job.career_type, {"ENTRY", "EXPERIENCED", "ANY", "UNKNOWN"})
