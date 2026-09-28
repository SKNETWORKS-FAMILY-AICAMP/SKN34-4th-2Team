"""자동 검사가 실제로 결함을 잡는지.

검사가 늘 0건을 내면 통과하는 것처럼 보이지만 아무것도 지키지 못한다. 각 검사가
**잡아야 할 것을 잡고, 잡지 말아야 할 것은 놓아주는지**를 여기서 못박는다.

특히 인용 대조는 한 번 오탐을 냈다. 서버와 다른 규칙으로 비교했더니 30건 중 14건이
전부 걸렸는데 전부 정상이었다. 그 케이스를 회귀로 남긴다.
"""

from __future__ import annotations

import unittest
from unittest import mock

from job_matching_bot.evaluation import recommend_check as check

# 인용 대조는 저장소에서 공고를 다시 읽는다(`_record`). 그 저장소는 운영 RDS 라서
# 테스트에서는 비워 둔다. 여기 공고는 전부 `row(description=...)`로 넘긴다.
_no_store = mock.patch.object(check, "_record", return_value=None)


def setUpModule():
    _no_store.start()


def tearDownModule():
    _no_store.stop()


def row(career_type="ANY", min_years=None, status="OPEN", deadline=None, description=""):
    """저장소 행 대신 쓰는 사전. sqlite3.Row 처럼 대괄호로 읽힌다."""
    return {
        "career_type": career_type,
        "min_career_years": min_years,
        "status": status,
        "deadline": deadline,
        "description": description,
    }


def job(fit="보통", reasons=None, region="서울 강남구", employment="정규직", company="가회사"):
    return {
        "job_id": "SARAMIN-1",
        "company": company,
        "title": "백엔드 개발자",
        "fit": fit,
        "reasons": reasons or [],
        "conditions": {"region": region, "employment_type": employment},
    }


ENTRY = {"career_years": 0, "preferred_regions": [], "preferred_employment_types": []}
SENIOR = {"career_years": 3, "preferred_regions": [], "preferred_employment_types": []}


class ExperiencedForEntryTest(unittest.TestCase):
    """오늘 실제로 잡은 결함. 25건 중 6건이 이랬고 셋은 "높음"이었다."""

    def test_experienced_posting_is_a_defect_for_a_new_grad(self):
        found = check.check_experienced_for_entry(ENTRY, job(), row(career_type="EXPERIENCED"))
        self.assertIsNotNone(found)
        self.assertIn("연차 미기재", found)

    def test_years_are_named_when_the_posting_says_them(self):
        found = check.check_experienced_for_entry(
            ENTRY, job(), row(career_type="EXPERIENCED", min_years=3)
        )
        self.assertIn("3년", found)

    def test_the_same_posting_is_fine_for_an_experienced_person(self):
        self.assertIsNone(
            check.check_experienced_for_entry(SENIOR, job(), row(career_type="EXPERIENCED"))
        )

    def test_open_to_all_is_not_a_defect(self):
        self.assertIsNone(check.check_experienced_for_entry(ENTRY, job(), row(career_type="ANY")))


class RegionTest(unittest.TestCase):
    def test_outside_the_wanted_region_is_a_defect(self):
        persona = {**ENTRY, "preferred_regions": ["서울"]}
        found = check.check_region_outside_preference(persona, job(region="부산 해운대구"), None)
        self.assertIn("부산", found)

    def test_nationwide_postings_pass(self):
        """전국 근무는 어디를 원하든 지원할 수 있다."""
        persona = {**ENTRY, "preferred_regions": ["서울"]}
        self.assertIsNone(
            check.check_region_outside_preference(persona, job(region="전국"), None)
        )

    def test_no_preference_means_nothing_to_violate(self):
        self.assertIsNone(
            check.check_region_outside_preference(ENTRY, job(region="부산"), None)
        )

    def test_unstated_region_is_not_counted_as_a_violation(self):
        """적혀 있지 않은 것과 어긋난 것은 다르다."""
        persona = {**ENTRY, "preferred_regions": ["서울"]}
        self.assertIsNone(
            check.check_region_outside_preference(persona, job(region="미기재"), None)
        )


class ReasonTest(unittest.TestCase):
    def test_high_fit_without_any_reason_is_a_defect(self):
        found = check.check_high_without_reason(ENTRY, job(fit="높음"), None)
        self.assertIsNotNone(found)

    def test_high_fit_with_a_reason_passes(self):
        self.assertIsNone(
            check.check_high_without_reason(
                ENTRY, job(fit="높음", reasons=[{"claim": "겹친다"}]), None
            )
        )

    def test_moderate_fit_without_reasons_is_not_this_check(self):
        self.assertIsNone(check.check_high_without_reason(ENTRY, job(fit="보통"), None))


class QuoteTest(unittest.TestCase):
    """서버와 같은 규칙으로 대조해야 한다."""

    def test_a_quote_that_is_not_in_the_posting_is_caught(self):
        found = check.check_quote_not_in_job(
            ENTRY,
            job(reasons=[{"job_quote": "Kubernetes 운영 경험 필수"}]),
            row(description="자격요건\n- Python 백엔드 개발 경험"),
        )
        self.assertIsNotNone(found)

    def test_non_breaking_spaces_are_not_a_mismatch(self):
        """공고 원문에는 \\xa0 가 섞여 있고 LLM은 보통 공백으로 바꿔 인용한다.

        문자열을 그대로 비교했을 때 30건 중 14건이 전부 여기서 걸렸다. 전부 정상이었다.
        """
        body = "•\xa0RESTful\xa0API\xa0설계\xa0경험\n•\xa0FastAPI\xa0기반의\xa0Backend\xa0개발\xa0경험"
        self.assertIsNone(
            check.check_quote_not_in_job(
                ENTRY, job(reasons=[{"job_quote": "RESTful API 설계 경험"}]), row(description=body)
            )
        )

    def test_a_very_short_quote_is_skipped(self):
        """두세 글자는 우연히 맞을 수 있어 판단 근거가 못 된다."""
        self.assertIsNone(
            check.check_quote_not_in_job(
                ENTRY, job(reasons=[{"job_quote": "API"}]), row(description="전혀 다른 글")
            )
        )


class ClosedTest(unittest.TestCase):
    def test_a_posting_past_its_deadline_is_a_defect(self):
        found = check.check_closed(ENTRY, job(), row(deadline="2020-01-01"))
        self.assertIn("2020-01-01", found)

    def test_a_posting_that_left_the_site_is_a_defect(self):
        found = check.check_closed(ENTRY, job(), row(status="EXPIRED"))
        self.assertIn("EXPIRED", found)

    def test_no_deadline_is_fine(self):
        self.assertIsNone(check.check_closed(ENTRY, job(), row()))


class CompanyCapTest(unittest.TestCase):
    def test_more_than_the_cap_from_one_company_is_a_defect(self):
        report = check.Report()
        check.check_company_cap("백엔드 신입", [job(company="가회사")] * 3, report)
        self.assertEqual(1, len(report.defects))
        self.assertIn("가회사 3건", report.defects[0].detail)

    def test_at_the_cap_is_allowed(self):
        report = check.Report()
        check.check_company_cap("백엔드 신입", [job(company="가회사")] * 2, report)
        self.assertEqual([], report.defects)


class InspectTest(unittest.TestCase):
    """전체 흐름. 결함이 있으면 세고, 없으면 0이다."""

    def test_a_clean_result_has_no_defects(self):
        raw = {"백엔드 수료생": {"recommendations": []}}
        report = check.inspect(raw, {"백엔드 수료생": ENTRY})
        self.assertEqual([], report.defects)
        self.assertEqual(0, report.checked)

    def _inspect(self, raw, personas, **kwargs):
        stored = {"SARAMIN-1": row(career_type="EXPERIENCED", min_years=3, status="REMOVED")}
        with mock.patch.object(check, "store_rows", return_value=stored):
            return check.inspect(raw, personas, **kwargs)

    def test_an_unknown_resume_is_skipped_not_treated_as_a_new_grad(self):
        """옛 결과 파일의 이력서 이름이 지금 목업과 달랐다. 못 찾은 이력서를 연차 0으로
        보아 경력 3년 이력서에 "신입에게 경력 공고"를 4건 셌다."""
        report = self._inspect({"백엔드 경력 3년": {"recommendations": [job()]}}, {})
        self.assertNotIn("신입에게 경력 공고", [d.check for d in report.defects])
        self.assertEqual(["백엔드 경력 3년"], report.missing_personas)

    def test_closed_check_runs_only_on_the_day_it_was_fetched(self):
        """지난 결과를 오늘 저장소로 보면 그 사이 마감된 공고까지 결함이 된다."""
        raw = {"경력": {"recommendations": [job()]}}
        today = [d.check for d in self._inspect(raw, {"경력": SENIOR}).defects]
        later = [d.check for d in self._inspect(raw, {"경력": SENIOR}, same_day=False).defects]
        self.assertIn("마감·삭제된 공고", today)
        self.assertNotIn("마감·삭제된 공고", later)


class RunFileTest(unittest.TestCase):
    def test_saved_run_keeps_the_resume_conditions_it_was_checked_with(self):
        personas = {"경력 3년": {**SENIOR, "resume_text": "길어서 남기지 않는다"}}
        saved = check.wrap_run({"경력 3년": {"recommendations": []}}, personas, "app-mocks")
        raw, kept, fetched_on = check.unwrap_run(saved)
        self.assertEqual({"경력 3년": {"recommendations": []}}, raw)
        self.assertEqual(3, kept["경력 3년"]["career_years"])
        self.assertNotIn("resume_text", kept["경력 3년"])
        self.assertEqual(10, len(fetched_on))

    def test_an_old_file_is_results_only(self):
        raw, kept, fetched_on = check.unwrap_run({"백엔드": {"recommendations": []}})
        self.assertEqual({"백엔드": {"recommendations": []}}, raw)
        self.assertIsNone(kept)
        self.assertIsNone(fetched_on)

    def test_summary_counts_every_check_even_when_zero(self):
        report = check.Report(personas=1, checked=2)
        report.add("희망 지역 밖", "경력", job(), "희망 서울 인데 부산")
        out = check.summary(report, "eval-resumes", "2026-09-13")
        self.assertEqual(1, out["counts"]["희망 지역 밖"])
        self.assertEqual(0, out["counts"]["회사당 상한 초과"])
        self.assertEqual(2, out["jobs"])


if __name__ == "__main__":
    unittest.main()
