from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import Mock

from chatbot_lab.bot import LAB_MODEL, _assert_luna, _luna_environment
from chatbot_lab.mock_firebase import load_fixture, load_mock_student_context
from chatbot_lab.routing import (
    LabSupervisorGuardrail,
    bind_session_cohort_to_project_query,
    detect_routing_signals,
    reconcile_decision,
)
from chatbot.student_chatbot import SupervisorDecision
from chatbot_lab.prompts import LAB_ANSWER_PROMPT
from chatbot_lab.attendance import enrich_unit_period_context
from chatbot_lab.project_search import (
    cohort_buckets,
    cohort_range,
    diversify_by_cohort,
    neutralize_cohort_ranges,
)
from langchain_core.documents import Document


class LabSafetyTest(unittest.TestCase):
    def test_project_cohort_range_is_not_mistaken_for_last_cohort(self) -> None:
        self.assertEqual(cohort_range("1~28기 최종 프로젝트"), (1, 28))
        self.assertEqual(cohort_range("1기부터 28기까지 사례"), (1, 28))
        neutral = neutralize_cohort_ranges("1~28기 최종 프로젝트")
        self.assertNotIn("28기", neutral)
        self.assertEqual(len(cohort_buckets(1, 28)), 7)

    def test_project_range_results_prefer_different_cohorts(self) -> None:
        documents = [
            Document(id="28-a", page_content="a", metadata={"cohort": "28"}),
            Document(id="28-b", page_content="b", metadata={"cohort": "28"}),
            Document(id="27-a", page_content="c", metadata={"cohort": "27"}),
            Document(id="26-a", page_content="d", metadata={"cohort": "26"}),
        ]
        selected = diversify_by_cohort(documents, 3)
        self.assertEqual([doc.metadata["cohort"] for doc in selected], ["28", "27", "26"])

    def test_previous_cohort_project_references_are_explicitly_allowed(self) -> None:
        self.assertIn("현재 기수와 달라도", LAB_ANSWER_PROMPT)
        self.assertIn("기수 범위 위반으로 거절하지 않는다", LAB_ANSWER_PROMPT)
        self.assertIn("이전 기수 학생의\n개인정보", LAB_ANSWER_PROMPT)

    def test_in_progress_attendance_estimate_explains_80_percent_margin(self) -> None:
        context = {
            "current_unit_period": 3,
            "periods": [{
                "number": 3,
                "scheduled_days": 21,
                "recorded_days": 20,
                "status_counts": {"present": 12, "late": 6, "officialLeave": 2},
                "attendance_rate": None,
            }],
        }
        estimate = enrich_unit_period_context(context)["periods"][0]["in_progress_estimate"]
        self.assertEqual(estimate["attendance_rate"], 90.0)
        self.assertTrue(estimate["requirement_met_so_far"])
        self.assertEqual(estimate["remaining_scheduled_days"], 1)
        self.assertEqual(estimate["max_additional_absent_days_within_remaining"], 1)
        self.assertEqual(estimate["exception_count_until_next_absence_equivalent"], 3)
        self.assertEqual(estimate["final_rate_if_all_remaining_absent"], 85.7)

    def test_attendance_prompt_does_not_encourage_absence(self) -> None:
        self.assertIn("결석해도 괜찮다", LAB_ANSWER_PROMPT)
        self.assertIn("내부 계산값으로만 사용", LAB_ANSWER_PROMPT)
        self.assertIn("정상 출석", LAB_ANSWER_PROMPT)

    def test_task_union_cannot_drop_a_compound_request(self) -> None:
        from chatbot_lab.bot import LabSupervisorDecision, LabTask

        decision = LabSupervisorDecision(
            route="lms",
            namespaces=[],
            student_scopes=[],
            query="복합 질문",
            tasks=[
                LabTask(
                    query="내 제출 파일 조회",
                    namespaces=[],
                    student_scopes=["student_private", "assignment_files"],
                ),
                LabTask(
                    query="이전 프로젝트 검색",
                    namespaces=["project_reference"],
                    student_scopes=[],
                ),
            ],
        )
        base = Mock()
        base.invoke.return_value = decision
        fixed = LabSupervisorGuardrail(base).invoke(
            {"messages": [Mock(content="내 파일과 이전 프로젝트를 같이 찾아줘")]},
            Mock(),
        )
        self.assertEqual(fixed.namespaces, ["project_reference"])
        self.assertEqual(
            fixed.student_scopes, ["student_private", "assignment_files"],
        )
        self.assertIn("내 제출 파일 조회", fixed.query)
        self.assertIn("이전 프로젝트 검색", fixed.query)

    def test_attendance_fixture_contains_raw_records_not_answer(self) -> None:
        fixture = load_fixture()
        serialized = str(fixture).lower()
        self.assertNotIn("attendance_rate", serialized)
        self.assertNotIn("requirement_met", serialized)

        context = load_mock_student_context(
            "mock-student-001", "cohort_34", ["student_private"], "지난 출석"
        )
        periods = context["data"]["student_private"]["unit_period_context"]["periods"]
        self.assertIsNotNone(periods[0]["attendance_rate"])
        self.assertIsNone(periods[1]["attendance_rate"])

    def test_mock_leave_records_keep_firebase_leave_types(self) -> None:
        attendance = load_fixture()["collections"]["cohorts"]["cohort_34"]["attendances"]
        sick = next(item for item in attendance.values() if item.get("sourceLabel") == "질병/입원")
        vacation = next(item for item in attendance.values() if item.get("sourceLabel") == "휴가")
        self.assertEqual((sick["status"], sick["officialLeaveType"]), ("officialLeave", "sick"))
        self.assertEqual(
            (vacation["status"], vacation["officialLeaveType"]),
            ("officialLeave", "vacation"),
        )

    def test_lab_python_does_not_name_forbidden_model(self) -> None:
        root = Path(__file__).parents[1]
        sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in root.rglob("*.py")
            if path != Path(__file__)
        )
        self.assertNotIn("gpt-5.6-sol", sources.lower())

    def test_model_guard_accepts_only_luna(self) -> None:
        _assert_luna(Mock(model_name=LAB_MODEL), "test")
        with self.assertRaises(RuntimeError):
            _assert_luna(Mock(model_name="another-model"), "test")

    def test_temporary_model_settings_are_restored(self) -> None:
        names = ("LMS_SUPERVISOR_MODEL", "LMS_NODE_MODEL")
        before = {name: os.environ.get(name) for name in names}
        with _luna_environment():
            self.assertTrue(all(os.environ[name] == LAB_MODEL for name in names))
        self.assertEqual(before, {name: os.environ.get(name) for name in names})

    def test_explicit_mixed_lms_signals_are_merged(self) -> None:
        question = "내가 오늘 지각하면 내 출석에는 어떻게 반영돼?"
        signals = detect_routing_signals(question)
        self.assertEqual(signals.namespaces, ("policy",))
        self.assertEqual(signals.student_scopes, ("student_private",))
        fixed = reconcile_decision(question, SupervisorDecision(route="blocked", query=""))
        self.assertEqual(fixed.route, "lms")
        self.assertEqual(fixed.namespaces, ["policy"])
        self.assertEqual(fixed.student_scopes, ["student_private"])

    def test_coding_test_question_searches_notice(self) -> None:
        for question in ("다음 코딩테스트 언제지", "다음 코테 언제야"):
            with self.subTest(question=question):
                signals = detect_routing_signals(question)
                self.assertTrue(signals.lms)
                self.assertIn("notice", signals.namespaces)

    def test_unrelated_personal_request_is_not_forced_into_lms(self) -> None:
        decision = SupervisorDecision(route="blocked", query="내 이력서 대신 써줘")
        fixed = reconcile_decision("내 이력서 대신 써줘", decision)
        self.assertEqual(fixed.route, "blocked")

    def test_owned_assignment_file_uses_private_and_file_scopes(self) -> None:
        signals = detect_routing_signals("내가 낸 과제 파일을 확인하고 싶어")
        self.assertEqual(
            set(signals.student_scopes), {"student_private", "assignment_files"}
        )

    def test_private_value_does_not_automatically_search_policy(self) -> None:
        signals = detect_routing_signals("내 출석률 알려줘")
        self.assertEqual(signals.namespaces, ())
        self.assertEqual(signals.student_scopes, ("student_private",))

    def test_implicit_monthly_attendance_is_the_logged_in_students_data(self) -> None:
        signals = detect_routing_signals("이번 달 출결 집계 정보 알려줘")
        self.assertEqual(signals.namespaces, ())
        self.assertEqual(signals.student_scopes, ("student_private",))

    def test_attendance_rule_stays_a_policy_question(self) -> None:
        signals = detect_routing_signals("이번 달 출결 인정 기준이 뭐야?")
        self.assertEqual(signals.namespaces, ("policy",))
        self.assertEqual(signals.student_scopes, ())

    def test_lounge_food_rule_is_a_policy_question(self) -> None:
        signals = detect_routing_signals("라운지에서 음식 먹어도 돼?")
        self.assertEqual(signals.namespaces, ("policy",))

    def test_explicit_recent_facility_change_checks_policy_and_notice(self) -> None:
        signals = detect_routing_signals("최근 공지로 바뀐 라운지 취식 규칙 알려줘")
        self.assertEqual(signals.namespaces, ("policy", "notice"))

    def test_data_only_query_does_not_erase_the_models_selection(self) -> None:
        decision = SupervisorDecision(
            route="lms", namespaces=["policy"], student_scopes=["cohort_shared"], query="과제 일정"
        )
        fixed = reconcile_decision("이번 기수 과제 마감 일정 알려줘", decision)
        self.assertEqual(fixed.namespaces, ["policy"])
        self.assertEqual(fixed.student_scopes, ["cohort_shared"])

    def test_implicit_project_cohort_uses_authenticated_student_cohort(self) -> None:
        query = bind_session_cohort_to_project_query(
            "3차 프로젝트 주제 알려줘", "cohort_34", ["project_reference"],
        )
        self.assertIn("34기", query)

    def test_explicit_project_cohort_is_not_overwritten(self) -> None:
        query = bind_session_cohort_to_project_query(
            "33기 3차 프로젝트 주제 알려줘", "cohort_34", ["project_reference"],
        )
        self.assertNotIn("현재 로그인 학생 기수", query)
        self.assertIn("33기", query)

    def test_project_date_question_reads_curriculum_pdf(self) -> None:
        signals = detect_routing_signals("3차 프로젝트 언제 시작해?")
        self.assertIn("project_reference", signals.namespaces)
        self.assertIn("curriculum_files", signals.student_scopes)

    def test_final_project_deadline_notice_also_reads_curriculum_pdf(self) -> None:
        signals = detect_routing_signals("최종 프로젝트 마감 공지와 발표일을 알려줘")
        self.assertIn("notice", signals.namespaces)
        self.assertIn("project_reference", signals.namespaces)
        self.assertIn("curriculum_files", signals.student_scopes)

    def test_weekly_class_question_reads_curriculum_pdf(self) -> None:
        signals = detect_routing_signals("이번 주 수업 뭐야?")
        self.assertIn("curriculum_files", signals.student_scopes)

    def test_project_topic_does_not_force_curriculum_pdf(self) -> None:
        signals = detect_routing_signals("3차 프로젝트 주제 알려줘")
        self.assertIn("project_reference", signals.namespaces)
        self.assertNotIn("curriculum_files", signals.student_scopes)

    def test_project_calendar_rule_uses_each_authenticated_cohort_pdf(self) -> None:
        self.assertIn("로그인 학생의 기수 커리큘럼 PDF", LAB_ANSWER_PROMPT)
        self.assertIn("날짜순 등장 순서대로 1차부터", LAB_ANSWER_PROMPT)
        self.assertIn("마지막 날은 발표일", LAB_ANSWER_PROMPT)
        self.assertIn("특정 기수의 날짜나 횟수를", LAB_ANSWER_PROMPT)
        self.assertIn("로그인 기수 PDF에서 다시 계산", LAB_ANSWER_PROMPT)
        self.assertIn("주제는 일정으로부터 추측하지 않는다", LAB_ANSWER_PROMPT)


if __name__ == "__main__":
    unittest.main()
