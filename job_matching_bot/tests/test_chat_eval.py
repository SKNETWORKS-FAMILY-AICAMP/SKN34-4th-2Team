"""챗봇 채점 도구가 재야 할 것을 재는지.

가장 중요한 것은 마지막 시험이다. **케이스에 적어 둔 기대값을 아무도 안 보는 일**이
실제로 있었다. `intent`, `counts_jobs`, `job_refs`를 적어 두었는데 응답에 그 칸이
없어 전부 건너뛰었고, 그래도 22/22 통과라고 나왔다. 재는 줄 알았던 것을 안 재는
쪽이 아예 안 재는 쪽보다 나쁘다.
"""

from __future__ import annotations

import datetime
import json
import unittest
from types import SimpleNamespace

from job_matching_bot.evaluation import chat_eval, chat_grader_page
from job_matching_bot.evaluation.chat_grader_page import build_page


def _turn(**kwargs) -> SimpleNamespace:
    base = dict(intent="검색", topic="채용", counts_jobs=False, job_refs=[],
                unavailable="", requirement_query="")
    return SimpleNamespace(**{**base, **kwargs})


class CaseFileTest(unittest.TestCase):
    def test_every_expected_field_is_actually_checked(self):
        cases = json.loads(chat_eval.CASES.read_text(encoding="utf-8"))["cases"]
        self.assertEqual(chat_eval.unknown_keys(cases), set())

    def test_the_two_layers_do_not_overlap(self):
        self.assertEqual(chat_eval.HTTP_KEYS & chat_eval.ROUTER_KEYS, frozenset())


class RouterCheckTest(unittest.TestCase):
    def test_intent_is_compared(self):
        checks = chat_eval.check_router({"intent": "질문"}, _turn(intent="검색"))
        self.assertEqual([ok for _, ok, _ in checks], [False])

    def test_counts_jobs_false_is_compared_not_skipped(self):
        # `if expect.get("counts_jobs")`로 썼다면 False 기대가 통째로 빠진다.
        checks = chat_eval.check_router({"counts_jobs": False}, _turn(counts_jobs=True))
        self.assertEqual([ok for _, ok, _ in checks], [False])

    def test_job_refs_order_matters(self):
        checks = chat_eval.check_router({"job_refs": [1, 3]}, _turn(job_refs=[3, 1]))
        self.assertEqual([ok for _, ok, _ in checks], [False])

    def test_empty_job_refs_is_compared(self):
        ok = chat_eval.check_router({"job_refs": []}, _turn(job_refs=[3]))
        self.assertEqual([o for _, o, _ in ok], [False])

    def test_nothing_expected_means_nothing_checked(self):
        self.assertEqual(chat_eval.check_router({}, _turn()), [])


class HttpCheckTest(unittest.TestCase):
    def test_resume_scope_is_compared(self):
        checks = chat_eval.check(
            {"resume_scope": "프로젝트"}, {}, {"resume_scope": "전체"}, 1.0)
        self.assertIn(("이력서 범위", False, "프로젝트 ↔ 전체"), checks)

    def test_extra_filter_values_are_forgiven(self):
        checks = chat_eval.check(
            {"filters": {"roles": ["백엔드"]}}, {},
            {"filters": {"roles": ["백엔드", "서버"]}}, 1.0)
        self.assertTrue(all(ok for _, ok, _ in checks))


class RuleTest(unittest.TestCase):
    """사람 없이도 확실히 틀렸다고 말할 수 있는 것들. chat_check.py 에서 옮겨 왔다."""

    def test_a_casual_reply_is_caught(self):
        self.assertIsNotNone(chat_eval.rule_말투({"reply": "어 그런 공고 많아. 한번 봐봐"}))

    def test_a_polite_reply_passes(self):
        self.assertIsNone(chat_eval.rule_말투({"reply": "서울 백엔드 공고를 찾아드릴게요."}))

    def test_a_very_short_reply_is_not_judged(self):
        # 열 글자도 안 되는 말에 종결 어미를 요구하면 오판만 는다.
        self.assertIsNone(chat_eval.rule_말투({"reply": "네"}))

    def test_a_count_the_answer_invented_is_caught(self):
        got = {"reply": "조건에 맞는 공고가 412건 있어요.", "total": 334}
        self.assertIsNotNone(chat_eval.rule_건수(got))

    def test_the_real_count_passes(self):
        got = {"reply": "334건이에요.", "total": 334}
        self.assertIsNone(chat_eval.rule_건수(got))

    def test_a_markdown_table_is_caught(self):
        table = "| 기술 | 건수 |\n| --- | --- |"
        self.assertIsNotNone(chat_eval.rule_마크다운표({"reply": table}))

    def test_talking_about_a_table_the_user_never_saw_is_caught(self):
        self.assertIsNotNone(chat_eval.rule_표라는말({"reply": "표에 나온 대로입니다."}))

    def test_the_off_topic_reply_must_be_the_fixed_one(self):
        self.assertIsNotNone(chat_eval.rule_범위밖고정문구({"reply": "그건 잘 모르겠어요."}))

    def test_a_job_attached_to_an_off_topic_reply_is_caught(self):
        got = {"reply": "저는 채용과 취업 준비에 대해서만 도와드릴 수 있어요.",
               "jobs": [{"company": "x"}]}
        self.assertIsNotNone(chat_eval.rule_범위밖고정문구(got))

    def test_calling_jobs_A_and_B_is_caught(self):
        self.assertIsNotNone(chat_eval.rule_ab라벨({"reply": "A는 신입, B는 경력을 뽑습니다."}))

    def test_an_ordinary_A_is_not_an_AB_label(self):
        self.assertIsNone(chat_eval.rule_ab라벨({"reply": "AWS와 Azure를 씁니다."}))

    def test_every_rule_a_case_names_exists(self):
        cases = json.loads(chat_eval.CASES.read_text(encoding="utf-8"))["cases"]
        named = {r for c in cases for t in c["turns"]
                 for r in ((t.get("expect") or {}).get("rules") or [])}
        self.assertEqual(named - set(chat_eval.RULES), set())

    def test_no_rule_sits_unused(self):
        cases = json.loads(chat_eval.CASES.read_text(encoding="utf-8"))["cases"]
        named = {r for c in cases for t in c["turns"]
                 for r in ((t.get("expect") or {}).get("rules") or [])}
        self.assertEqual(set(chat_eval.RULES) - named, set())


class GraderPageTest(unittest.TestCase):
    RESULTS = [{
        "id": "ref-single",
        "note": "직전 목록에서 2번",
        "turns": [{
            "message": "2번 자세히 봐줘",
            "got": {"mode": "공고", "reply": "신입 지원이 가능한 자리입니다.",
                    "jobs": [{"company": "카카오", "title": "백엔드 개발자"}]},
            "elapsed": 3.2,
        }],
    }]

    def test_the_reply_and_its_evidence_are_both_on_the_page(self):
        page = build_page(self.RESULTS, "20260911-000000")
        self.assertIn("신입 지원이 가능한 자리입니다.", page)
        self.assertIn("카카오", page)

    def test_a_reply_cannot_close_the_data_block_early(self):
        results = [{**self.RESULTS[0], "turns": [
            {**self.RESULTS[0]["turns"][0], "got": {
                "mode": "공고", "reply": "</script><script>alert(1)</script>", "jobs": []}}
        ]}]
        page = build_page(results, "x")
        self.assertNotIn("</script><script>alert(1)", page)

    def test_the_deadline_the_answer_claimed_is_visible(self):
        results = [{"id": "search-deadline", "note": "", "turns": [{
            "message": "마감 임박한 백엔드 공고만 보여줘",
            "got": {"mode": "검색", "reply": "7일 내 마감 · 252건", "total": 252, "jobs": [
                {"company": "코너", "title": "백엔드", "source_url": "https://x/1",
                 "region": "서울 용산구", "career": "경력 4년 이상",
                 "employment_type": "정규직", "deadline": "2026-09-13T23:59:59+09:00"}]},
            "elapsed": 3.3}]}]
        page = build_page(results, "20260911-153508")
        self.assertIn("마감 09.13 (D-2)", page)
        self.assertIn("https://x/1", page)
        self.assertIn("서울 용산구", page)

    def test_a_deadline_already_past_is_marked(self):
        label, past = chat_grader_page._deadline_label(
            "2026-09-08T23:59:59+09:00", datetime.date(2026, 9, 11))
        self.assertTrue(past)
        self.assertIn("지남", label)

    def test_a_missing_deadline_says_so(self):
        label, past = chat_grader_page._deadline_label(None, datetime.date(2026, 9, 11))
        self.assertEqual((label, past), ("마감일 미기재", False))

    def test_a_missing_reply_does_not_break_the_page(self):
        results = [{"id": "x", "note": "", "turns": [
            {"message": "안녕", "got": {"mode": "안내"}, "elapsed": 0.4}]}]
        self.assertIn("안녕", build_page(results, "x"))


if __name__ == "__main__":
    unittest.main()
