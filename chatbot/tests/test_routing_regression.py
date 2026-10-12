"""이전 lab 실험의 핵심 안전성·검색 범위 회귀 검사."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import Mock

from chatbot.project_search import cohort_buckets, cohort_range, diversify_by_cohort, neutralize_cohort_ranges
from chatbot.student_chatbot import (
    ANSWER_PROMPT,
    RoutingGuardrailMiddleware,
    SupervisorDecision,
    SupervisorGuardrailMiddleware,
    detect_routing_signals,
    reconcile_decision,
)


class RoutingRegressionTests(unittest.TestCase):
    def test_eval_cases_remain_parseable(self) -> None:
        directory = Path(__file__).resolve().parents[1] / "evaluation"
        for name in ("eval_cases.json", "hard_eval_cases.json"):
            with self.subTest(name=name):
                cases = json.loads((directory / name).read_text(encoding="utf-8"))
                self.assertTrue(cases)
                for case in cases:
                    self.assertTrue({"id", "question", "route", "namespaces", "student_scopes"} <= case.keys())

    def test_cohort_range_and_diversity(self) -> None:
        self.assertEqual(cohort_range("1~28기 최종 프로젝트"), (1, 28))
        self.assertEqual(cohort_range("1기부터 28기까지 사례"), (1, 28))
        self.assertNotIn("28기", neutralize_cohort_ranges("1~28기 최종 프로젝트"))
        self.assertEqual(len(cohort_buckets(1, 28)), 7)
        docs = [
            Mock(id="28-a", metadata={"cohort": "28"}),
            Mock(id="28-b", metadata={"cohort": "28"}),
            Mock(id="27-a", metadata={"cohort": "27"}),
        ]
        self.assertEqual(
            [doc.metadata["cohort"] for doc in diversify_by_cohort(docs, 2)],
            ["28", "27"],
        )

    def test_obvious_lms_signals_are_preserved(self) -> None:
        signals = detect_routing_signals("내가 오늘 지각하면 내 출석에는 어떻게 반영돼?")
        self.assertEqual(signals.namespaces, ("policy",))
        self.assertEqual(signals.student_scopes, ("student_attendance",))
        self.assertEqual(
            detect_routing_signals("최근 공지로 바뀐 라운지 취식 규칙 알려줘").namespaces,
            ("policy", "notice"),
        )

    def test_compound_tasks_keep_both_scopes(self) -> None:
        decision = SupervisorDecision(
            route="lms", namespaces=[], student_scopes=[], query="복합 질문",
            tasks=[
                {"query": "내 제출 파일 조회", "namespaces": [], "student_scopes": ["assignment_files"]},
                {"query": "이전 프로젝트 검색", "namespaces": ["project_reference"], "student_scopes": []},
            ],
        )
        base = Mock()
        base.invoke.return_value = decision
        middleware = RoutingGuardrailMiddleware(base)
        result = middleware.invoke({"messages": [Mock(content="내 파일과 이전 프로젝트")]}, Mock())
        self.assertIn("assignment_files", result.student_scopes)
        self.assertIn("project_reference", result.namespaces)

    def test_blocked_decision_stays_blocked(self) -> None:
        decision = SupervisorDecision(route="blocked", query="다른 학생 출결과 우리 정책")
        result = reconcile_decision("다른 학생 출결과 우리 정책", decision)
        self.assertEqual(result.route, "blocked")
        self.assertEqual(result.namespaces, [])
        self.assertEqual(result.student_scopes, [])

    def test_answer_prompt_keeps_evidence_boundaries(self) -> None:
        self.assertIn("정책은 기본 규칙", ANSWER_PROMPT)
        self.assertIn("문서별 내용을 섞지 말고", ANSWER_PROMPT)
        self.assertIn("결석을 허용·권장하지 않는다", ANSWER_PROMPT)


if __name__ == "__main__":
    unittest.main()
