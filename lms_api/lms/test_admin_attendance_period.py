from datetime import date
from unittest import TestCase
from unittest.mock import Mock, patch

from lms.admin_attendance_period import attendance_unit_period
from lms.admin_assistant import _Session

COHORT = {"id": 2, "code": "cohort_34"}
BASIS = {
    "status": "extracted", "cohort": "cohort_34", "document_hash": "a" * 64,
    "article": "1", "evidence": "단위기간", "anchor": "course_start",
    "cycle": "calendar_month", "end": "next_start_minus_one_day",
    "last_period": "course_end", "class_days": "cohort_schedule",
    "month_end_handling": "unspecified",
}


class AdminAttendancePeriodTests(TestCase):
    def period(self, today, previous=False, start=date(2026, 8, 17), end=date(2026, 12, 10)):
        cur = Mock()
        cur.fetchone.return_value = (start, end)
        with patch("lms.admin_attendance_period.load_active_snapshot", return_value={
            "cohort": "cohort_34", "calendar_basis": BASIS, "criteria": {}, "storage_key": "policy",
        }):
            return attendance_unit_period(cur, COHORT, today, previous)

    def test_current_period_crosses_calendar_month(self):
        result = self.period(date(2026, 10, 13))
        self.assertEqual((result["start"], result["end"]), ("2026-09-17", "2026-10-16"))

    def test_boundary_previous_and_final_period(self):
        self.assertEqual(self.period(date(2026, 10, 17))["start"], "2026-10-17")
        self.assertEqual(self.period(date(2026, 10, 17), True)["start"], "2026-09-17")
        self.assertEqual(self.period(date(2026, 12, 1))["end"], "2026-12-10")

    def test_no_current_or_previous_period(self):
        for today, previous in [(date(2026, 8, 1), False), (date(2027, 1, 1), False), (date(2026, 8, 18), True)]:
            with self.subTest(today=today), self.assertRaises(ValueError):
                self.period(today, previous)

    def test_missing_policy_does_not_fall_back(self):
        cur = Mock()
        cur.fetchone.return_value = (date(2026, 8, 17), date(2026, 12, 10))
        with patch("lms.admin_attendance_period.load_active_snapshot", side_effect=ValueError("missing")):
            with self.assertRaisesRegex(ValueError, "활성 기수 정책"):
                attendance_unit_period(cur, COHORT, date(2026, 10, 13))

    @patch("lms.admin_assistant.attendance_unit_period")
    @patch("lms.admin_assistant.datetime")
    def test_default_stats_use_unit_period_through_today(self, clock, period):
        clock.now.return_value.date.return_value = date(2026, 10, 13)
        period.return_value = {"start": "2026-09-17", "end": "2026-10-16"}
        cur = Mock()
        cur.fetchall.return_value = [("a", "학생", "present", 10)]
        result = _Session({}, COHORT)._tool_attendance_stats(cur, {})
        self.assertEqual(cur.execute.call_args.args[1], [2, date(2026, 9, 17), date(2026, 10, 13)])
        self.assertEqual(result["totals"]["present"], 10)
        self.assertEqual(result["period"], "current_unit")

    def test_custom_dates_and_student_scope(self):
        session = _Session({}, COHORT)
        cur = Mock()
        cur.fetchall.return_value = [("a", "학생A", "present", 10), ("b", "학생B", "late", 5)]
        with patch.object(session, "_find_student", return_value={"uid": "a", "name": "학생A"}):
            result = session._tool_attendance_stats(cur, {"name": "학생A", "period": "custom",
                "from_date": "2026-10-01", "to_date": "2026-10-13"})
        self.assertEqual(result["from"], "2026-10-01")
        self.assertEqual(result["totals"]["late"], 0)
        self.assertEqual([s["uid"] for s in result["students"]], ["a"])
