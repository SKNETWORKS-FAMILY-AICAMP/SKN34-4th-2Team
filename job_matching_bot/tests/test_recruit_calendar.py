"""공채 달력 수집 — 응답 모양은 2026-10-07 실제 응답에서 줄였다"""

import unittest
from datetime import date

from job_matching_bot.crawling.recruit_calendar import (
    apply_method,
    company_summary,
    merge_rows,
    months_from,
    parse_jobkorea,
    parse_saramin,
)

SARAMIN = {
    "success": True,
    "data": {"list": {
        "20261018": [{
            "rec_idx": 55178925, "company_nm": "한국미우라공업㈜", "title": "생산기술과 신입사원 채용",
            "company_logo_url": "https://clogo.saramin.co.kr/a.jpg", "how_to_apply": "email",
            "opening_date": "20261018", "closing_date": "20261025", "schedule_type": "OPEN",
        }],
        "20261025": [
            {"rec_idx": 55178925, "company_nm": "한국미우라공업㈜", "title": "생산기술과 신입사원 채용",
             "company_logo_url": "https://clogo.saramin.co.kr/a.jpg", "how_to_apply": "email",
             "opening_date": "20261018", "closing_date": "20261025", "schedule_type": "CLOSE"},
            {"rec_idx": 1, "company_nm": "가나", "title": "t", "company_logo_url": "",
             "how_to_apply": "homepage", "opening_date": "", "closing_date": "20261025", "schedule_type": "CLOSE"},
        ],
    }},
}

JOBKOREA = """
<table><tr>
<td class=" disable"><div class="dayDiv"><div class="calCont"><strong class="day">30</strong></div></div></td>
<td class=" "><div class="dayDiv"><div class="calCont"><strong class="day">1</strong>
  <div class="AgiCntnts"><span class="link start "><a href="/Recruit/GI_Read/50097944" title="디알텍"
     class="devBoothItem AgiLink" data-gno="50097944"><strong>시작</strong>디알텍</a></span></div>
</div></div></td>
<td class=" saturday "><div class="dayDiv"><div class="calCont"><strong class="day">10</strong>
  <div class="AgiCntnts"><span class="link end "><a href="/Recruit/GI_Read/50097944" title="디알텍"
     class="devBoothItem AgiLink" data-gno="50097944"><strong>마감</strong>디알텍</a></span></div>
</div></div></td>
</tr></table>
"""


class RecruitCalendarTests(unittest.TestCase):
    def test_months(self) -> None:
        self.assertEqual(months_from(date(2026, 12, 3), 2), ["202612", "202701"])

    def test_saramin_one_row_per_posting(self) -> None:
        rows = {r["source_job_id"]: r for r in parse_saramin(SARAMIN, "scale001")}
        self.assertEqual(len(rows), 2, "시작 · 마감 날에 두 번 나와도 한 줄")
        row = rows["55178925"]
        self.assertEqual(row["schedule_types"], ["OPEN", "CLOSE"])
        self.assertEqual((row["opening_date"], row["closing_date"]), ("2026-10-18", "2026-10-25"))
        self.assertEqual(row["apply_method"], "EMAIL")
        self.assertEqual(rows["1"]["apply_method"], "HOMEPAGE")
        self.assertIsNone(rows["1"]["logo_url"])
        self.assertIsNone(rows["1"]["opening_date"])

    def test_apply_method_priority(self) -> None:
        self.assertEqual(apply_method("email,homepage"), "HOMEPAGE")
        self.assertEqual(apply_method("homepage,profile"), "HOMEPAGE")
        self.assertEqual(apply_method("email,profile"), "SITE")
        self.assertEqual(apply_method("email,post,fax"), "EMAIL")
        self.assertEqual(apply_method("post,nae"), "OTHER")
        self.assertIsNone(apply_method(None))

    def test_company_type_order(self) -> None:
        """1000대기업(scale002)은 중견 · 중소에도 붙어 다른 형태가 있으면 그쪽"""
        rows = [*parse_saramin(SARAMIN, "scale002"), *parse_saramin(SARAMIN, "kosdaq")]
        [company] = [c for c in company_summary(merge_rows(rows)) if c["company_name"] == "가나"]
        self.assertEqual(company["company_type"], "코스닥")

    def test_saramin_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "기업 형태"):
            parse_saramin({"success": False, "error": {"message": "하나 이상의 기업 형태를 선택해주세요."}}, "x")

    def test_jobkorea_dates_from_cells(self) -> None:
        [row] = parse_jobkorea(JOBKOREA, "202610")
        self.assertEqual(row["source_job_id"], "50097944")
        self.assertEqual(row["company_name"], "디알텍")
        self.assertEqual((row["opening_date"], row["closing_date"]), ("2026-10-01", "2026-10-10"))

    def test_merge_and_companies(self) -> None:
        a = parse_saramin(SARAMIN, "scale001")
        b = parse_saramin(SARAMIN, "kospi")
        merged = merge_rows([*a, *b])
        self.assertEqual(len(merged), 2)
        self.assertEqual(next(r for r in merged if r["source_job_id"] == "1")["company_types"], ["scale001", "kospi"])
        companies = {c["company_name"]: c for c in company_summary(merged)}
        self.assertEqual(companies["한국미우라공업㈜"]["logo_url"], "https://clogo.saramin.co.kr/a.jpg")
        self.assertEqual(companies["한국미우라공업㈜"]["company_type"], "대기업")


if __name__ == "__main__":
    unittest.main()
