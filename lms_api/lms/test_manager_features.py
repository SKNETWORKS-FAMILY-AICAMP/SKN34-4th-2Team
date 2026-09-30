"""불시 점검 · 지정 알림 · 출결 신청 · 관리자 AI 어시스턴트 — DB 없이 도는 검사."""

import json
from datetime import date
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch

from django.test import Client, SimpleTestCase

from lms.admin_assistant import execute_action, run_assistant
from lms.attendance_requests import (
    issue_label,
    load_details,
    op_cancel_attendance_request,
    op_review_attendance_request,
    op_submit_attendance_request,
    public_request,
    resulting_status,
)
from lms.manager_commands import op_save_presence_check, set_alert_targets

STAFF = {"id": 4, "role": "admin", "cohort_id": 2, "is_active": True, "display_name": "매니저"}


class PresenceCheckTests(TestCase):
    def _cur(self, students):
        cur = Mock()
        cur.fetchall.return_value = students
        cur.fetchone.return_value = (31,)
        return cur

    @patch("lms.manager_commands.resolve_cohort", return_value=2)
    def test_new_check_inserts_header_and_items(self, _cohort):
        cur = self._cur([("uid-a", 8), ("uid-b", 9)])
        result = op_save_presence_check(cur, STAFF, {
            "cohortId": "cohort_34", "checkedAt": "2026-09-30T10:23:00+09:00",
            "items": [
                {"userId": "uid-a", "state": "present", "reason": "무시됨"},
                {"userId": "uid-b", "state": "absent", "reason": " 병원 "},
            ],
        })
        self.assertEqual(result, {"id": "31"})
        sqls = [c.args[0] for c in cur.execute.call_args_list]
        self.assertTrue(any("INSERT INTO presence_checks" in s for s in sqls))
        header = next(c.args[1] for c in cur.execute.call_args_list if "INSERT INTO presence_checks" in c.args[0])
        self.assertEqual(header[2], "am")
        items = [c.args[1] for c in cur.execute.call_args_list if "INSERT INTO presence_check_items" in c.args[0]]
        self.assertEqual(items, [[31, 8, "present", None], [31, 9, "absent", "병원"]])

    @patch("lms.manager_commands.resolve_cohort", return_value=2)
    def test_student_of_other_cohort_is_rejected(self, _cohort):
        cur = self._cur([("uid-a", 8)])
        with self.assertRaises(ValueError):
            op_save_presence_check(cur, STAFF, {
                "checkedAt": "2026-09-30T15:00:00+09:00",
                "items": [{"userId": "uid-a", "state": "present"}, {"userId": "uid-x", "state": "absent"}],
            })

    def test_student_cannot_save(self):
        with self.assertRaises(PermissionError):
            op_save_presence_check(Mock(), {"id": 1, "role": "student"}, {})


class AlertTargetTests(TestCase):
    def test_non_cohort_target_is_rejected(self):
        cur = Mock()
        cur.fetchall.return_value = [("uid-a", 8)]
        with self.assertRaises(ValueError):
            set_alert_targets(cur, 5, 2, ["uid-a", "uid-other"])

    def test_targets_are_replaced(self):
        cur = Mock()
        cur.fetchall.return_value = [("uid-a", 8), ("uid-b", 9)]
        self.assertEqual(set_alert_targets(cur, 5, 2, ["uid-a", "uid-b"]), 2)
        sqls = [c.args[0] for c in cur.execute.call_args_list]
        self.assertIn("DELETE FROM alert_popup_targets WHERE popup_id = %s", sqls)
        self.assertEqual(sum("INSERT INTO alert_popup_targets" in s for s in sqls), 2)


STUDENT = {"id": 8, "role": "student", "cohort_id": 2, "firebase_uid": "uid-a", "is_active": True}
TODAY = date(2026, 9, 30)
ROW_KEYS = ("id", "user_id", "cohort_id", "attendance_date", "issue_type", "status", "details", "evidence_storage_key")


def _request_row(**overrides):
    row = {
        "id": 5, "user_id": 8, "cohort_id": 2, "attendance_date": TODAY, "issue_type": "late",
        "status": "submitted", "details": json.dumps({"reason": "병원", "timeFrom": "10:00"}),
        "evidence_storage_key": None,
    }
    row.update(overrides)
    return tuple(row[k] for k in ROW_KEYS)


@patch("lms.attendance_requests.parse_day", side_effect=lambda v: date.fromisoformat(v) if v else TODAY)
class AttendanceRequestSubmitTests(TestCase):
    def test_new_request_is_inserted_with_label(self, _day):
        cur = Mock()
        cur.fetchone.side_effect = [None, (41,)]
        result = op_submit_attendance_request(cur, STUDENT, {
            "dateKey": "2026-09-30", "issueType": "earlyLeave", "timeFrom": "15:00", "reason": " 병원 진료 ",
            "officialLeaveUsed": True, "officialLeaveType": "sick",
        })
        self.assertEqual(result, {"id": "41"})
        sql, args = cur.execute.call_args.args
        self.assertIn("INSERT INTO attendance_issue_reports", sql)
        details = json.loads(args[4])
        self.assertEqual(details["reason"], "병원 진료")
        self.assertEqual(details["label"], "조퇴 15:00 · 공가(병가)")
        self.assertIsNone(details["timeTo"])

    def test_required_fields_are_checked(self, _day):
        cases = [
            {"issueType": "late", "reason": "늦잠"},
            {"issueType": "outing", "timeFrom": "13:00", "timeTo": "12:00", "reason": "은행"},
            {"issueType": "absent", "reason": ""},
            {"issueType": "absent", "reason": "면접", "officialLeaveUsed": True},
            {"issueType": "absent", "reason": "기타", "officialLeaveUsed": True, "officialLeaveType": "other"},
            {"issueType": "late", "timeFrom": "25:00", "reason": "x"},
            {"issueType": "absent", "reason": "x", "dateKey": "2026-01-01"},
        ]
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                op_submit_attendance_request(Mock(), STUDENT, payload)

    def test_staff_cannot_submit(self, _day):
        with self.assertRaises(PermissionError):
            op_submit_attendance_request(Mock(), STAFF, {"issueType": "absent", "reason": "x"})

    def test_duplicate_type_on_same_day_is_rejected(self, _day):
        cur = Mock()
        cur.fetchone.return_value = (3,)
        with self.assertRaises(ValueError):
            op_submit_attendance_request(cur, STUDENT, {"issueType": "absent", "reason": "몸살"})

    def test_someone_elses_evidence_is_rejected(self, _day):
        with self.assertRaises(PermissionError):
            op_submit_attendance_request(Mock(), STUDENT, {
                "issueType": "absent", "reason": "병원",
                "evidence": {"key": "records/cohort_34/uid-other/abc.pdf", "name": "진단서.pdf"},
            })

    def test_approved_request_cannot_be_edited(self, _day):
        cur = Mock()
        cur.fetchone.return_value = _request_row(status="approved")
        with self.assertRaises(ValueError):
            op_submit_attendance_request(cur, STUDENT, {"id": "5", "issueType": "late", "timeFrom": "10:00", "reason": "x"})

    def test_rejected_request_goes_back_to_review_when_edited(self, _day):
        cur = Mock()
        cur.fetchone.side_effect = [_request_row(status="rejected"), None]
        op_submit_attendance_request(cur, STUDENT, {"id": "5", "issueType": "late", "timeFrom": "10:30", "reason": "버스"})
        sql, args = cur.execute.call_args.args
        self.assertIn("status = 'submitted'", sql)
        self.assertEqual(args[-1], 5)


class AttendanceRequestReviewTests(TestCase):
    def test_student_cannot_cancel_approved(self):
        cur = Mock()
        cur.fetchone.return_value = _request_row(status="approved")
        with self.assertRaises(ValueError):
            op_cancel_attendance_request(cur, STUDENT, {"id": "5"})

    def test_student_cannot_cancel_others(self):
        cur = Mock()
        cur.fetchone.return_value = _request_row(user_id=99)
        with self.assertRaises(PermissionError):
            op_cancel_attendance_request(cur, STUDENT, {"id": "5"})

    def test_student_cannot_review(self):
        with self.assertRaises(PermissionError):
            op_review_attendance_request(Mock(), STUDENT, {"ids": ["5"], "decision": "approved"})

    def test_approve_applies_heaviest_status_to_attendance(self):
        cur = Mock()
        cur.fetchone.return_value = _request_row()
        cur.fetchall.return_value = [
            ("late", {"timeFrom": "10:00"}),
            ("absent", json.dumps({"officialLeaveUsed": True, "officialLeaveType": "interview"})),
        ]
        result = op_review_attendance_request(cur, STAFF, {"ids": ["5"], "decision": "approved", "comment": "확인"})
        self.assertEqual(result["applied"], [{"id": "5", "status": "officialLeave"}])
        sql, args = cur.execute.call_args.args
        self.assertIn("INSERT INTO attendances", sql)
        self.assertIn("ON CONFLICT (user_id, attendance_date)", sql)
        self.assertEqual(args, [2, 8, TODAY, "officialLeave", 4])

    def test_reject_keeps_attendance(self):
        cur = Mock()
        cur.fetchone.return_value = _request_row()
        result = op_review_attendance_request(cur, STAFF, {"ids": ["5"], "decision": "rejected", "comment": "증빙 필요"})
        self.assertEqual(result["applied"], [])
        sqls = [c.args[0] for c in cur.execute.call_args_list]
        self.assertFalse(any("INSERT INTO attendances" in s for s in sqls))
        update_args = next(c.args[1] for c in cur.execute.call_args_list if "UPDATE attendance_issue_reports" in c.args[0])
        self.assertEqual(json.loads(update_args[1])["reviewComment"], "증빙 필요")


class _FakeAttendanceDb:
    """출결 신청 · 출석부 두 표만 흉내 내는 커서 — 승인 · 승인 취소 흐름을 끝까지 돌려 본다."""

    def __init__(self, requests, attendance=None):
        self.requests = {r["id"]: {**r} for r in requests}
        self.attendance = dict(attendance or {})
        self._one = None
        self._all = []

    def execute(self, sql, args=None):
        args = list(args or [])
        self._one, self._all = None, []
        if "DELETE FROM attendance_issue_reports" in sql:
            self.requests.pop(args[0], None)
        elif "FROM attendance_issue_reports WHERE id = %s" in sql:
            row = self.requests.get(args[0])
            self._one = tuple(row[k] if k != "details" else json.dumps(row[k]) for k in ROW_KEYS) if row else None
        elif sql.lstrip().startswith("UPDATE attendance_issue_reports"):
            decision, details, _reviewer, _case, pk = args
            self.requests[pk].update(status=decision, details=json.loads(details))
        elif "SELECT issue_type, details FROM attendance_issue_reports" in sql:
            user_id, day = args
            self._all = [
                (r["issue_type"], r["details"]) for r in self.requests.values()
                if r["user_id"] == user_id and r["attendance_date"] == day and r["status"] == "approved"
            ]
        elif "SELECT details FROM attendance_issue_reports" in sql:
            user_id, day = args
            self._all = [
                (r["details"],) for r in reversed(list(self.requests.values()))
                if r["user_id"] == user_id and r["attendance_date"] == day
            ]
        elif "FROM attendances WHERE user_id" in sql:
            row = self.attendance.get((args[0], args[1]))
            self._one = (row["status"], row["data_source"], row["finalized_by_id"]) if row else None
        elif "INSERT INTO attendances" in sql:
            _cohort, user_id, day, status, reviewer = args
            self.attendance[(user_id, day)] = {"status": status, "data_source": "form", "finalized_by_id": reviewer}
        elif sql.lstrip().startswith("UPDATE attendances"):
            status, source, finalized_by, _clear, user_id, day = args
            self.attendance[(user_id, day)] = {"status": status, "data_source": source, "finalized_by_id": finalized_by}

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all


def _fake_request(pk, issue_type="late", status="submitted", **details):
    return {
        "id": pk, "user_id": 8, "cohort_id": 2, "attendance_date": TODAY, "issue_type": issue_type,
        "status": status, "details": {"reason": "x", **details}, "evidence_storage_key": None,
    }


class AttendanceReleaseTests(TestCase):
    def test_withdrawing_approval_restores_previous_status(self):
        db = _FakeAttendanceDb(
            [_fake_request(5, "absent", officialLeaveUsed=True, officialLeaveType="sick")],
            {(8, TODAY): {"status": "absent", "data_source": "manual", "finalized_by_id": 3}},
        )
        op_review_attendance_request(db, STAFF, {"ids": ["5"], "decision": "approved"})
        self.assertEqual(db.attendance[(8, TODAY)]["status"], "officialLeave")
        self.assertEqual(db.requests[5]["details"]["previousAttendance"]["status"], "absent")

        result = op_review_attendance_request(db, STAFF, {"ids": ["5"], "decision": "submitted"})
        self.assertEqual(db.attendance[(8, TODAY)], {"status": "absent", "data_source": "manual", "finalized_by_id": 3})
        self.assertTrue(result["applied"][0]["restored"])

    def test_other_approved_request_keeps_the_day(self):
        db = _FakeAttendanceDb([
            _fake_request(5, "absent", officialLeaveUsed=True, officialLeaveType="sick"),
            _fake_request(6, "late", timeFrom="10:00"),
        ])
        op_review_attendance_request(db, STAFF, {"ids": ["5", "6"], "decision": "approved"})
        self.assertEqual(db.attendance[(8, TODAY)]["status"], "officialLeave")
        op_review_attendance_request(db, STAFF, {"ids": ["5"], "decision": "rejected", "comment": "증빙 없음"})
        self.assertEqual(db.attendance[(8, TODAY)]["status"], "late")
        op_review_attendance_request(db, STAFF, {"ids": ["6"], "decision": "rejected"})
        self.assertEqual(db.attendance[(8, TODAY)]["status"], None)

    def test_manual_change_after_approval_is_left_alone(self):
        db = _FakeAttendanceDb([_fake_request(5, "late", timeFrom="10:00")])
        op_review_attendance_request(db, STAFF, {"ids": ["5"], "decision": "approved"})
        db.attendance[(8, TODAY)] = {"status": "present", "data_source": "manual", "finalized_by_id": 4}
        op_review_attendance_request(db, STAFF, {"ids": ["5"], "decision": "rejected"})
        self.assertEqual(db.attendance[(8, TODAY)]["status"], "present")

    def test_staff_deleting_approved_request_restores(self):
        db = _FakeAttendanceDb([_fake_request(5, "late", timeFrom="10:00")])
        op_review_attendance_request(db, STAFF, {"ids": ["5"], "decision": "approved"})
        op_cancel_attendance_request(db, STAFF, {"id": "5"})
        self.assertNotIn(5, db.requests)
        self.assertEqual(db.attendance[(8, TODAY)]["status"], None)


class AlertEndDateAndReadTests(TestCase):
    @patch("lms.commands.resolve_cohort", return_value=2)
    def test_insert_stores_end_date(self, _cohort):
        from lms.commands import op_upsert_alert

        cur = Mock()
        cur.fetchone.return_value = (77,)
        op_upsert_alert(cur, STAFF, {"title": "t", "endDate": "2026-09-30", "action": "insert"})
        insert = next(c.args for c in cur.execute.call_args_list if "INSERT INTO alert_popups" in c.args[0])
        self.assertIn("end_date", insert[0])
        self.assertEqual(insert[1][-1], date(2026, 9, 30))

    @patch("lms.commands.resolve_row", return_value={"id": 77, "cohort_id": 2})
    @patch("lms.commands.resolve_cohort", return_value=2)
    def test_update_without_end_date_keeps_it(self, _cohort, _row):
        from lms.commands import op_upsert_alert

        cur = Mock()
        op_upsert_alert(cur, STAFF, {"id": "77", "title": "t", "isActive": False})
        update = next(c.args for c in cur.execute.call_args_list if "UPDATE alert_popups" in c.args[0])
        self.assertEqual(update[1][7:9], [True, None])

    def test_bad_end_date_is_rejected(self):
        from lms.commands import _alert_end_date

        with self.assertRaises(ValueError):
            _alert_end_date("내일")

    @patch("lms.commands.resolve_row", return_value={"id": 77, "cohort_id": 2})
    def test_student_read_is_recorded_once(self, _row):
        from lms.commands import op_mark_alert_read

        cur = Mock()
        op_mark_alert_read(cur, STUDENT, {"popupId": 77})
        sql, args = cur.execute.call_args.args
        self.assertIn("ON CONFLICT (popup_id, user_id) DO NOTHING", sql)
        self.assertEqual(args, [77, 8])

    @patch("lms.commands.resolve_row", return_value={"id": 77, "cohort_id": 99})
    def test_other_cohort_read_is_rejected(self, _row):
        from lms.commands import op_mark_alert_read

        with self.assertRaises(PermissionError):
            op_mark_alert_read(Mock(), STUDENT, {"popupId": 77})

    def test_staff_read_is_ignored(self):
        from lms.commands import op_mark_alert_read

        cur = Mock()
        op_mark_alert_read(cur, STAFF, {"popupId": 77})
        cur.execute.assert_not_called()

    def test_assistant_alert_defaults_to_today(self):
        from lms.admin_assistant import _end_date_arg

        self.assertEqual(len(_end_date_arg(None)), 10)
        self.assertEqual(_end_date_arg("2026-10-03"), "2026-10-03")
        self.assertIsNone(_end_date_arg("none"))


class AttendanceRequestLabelTests(TestCase):
    def test_legacy_google_form_rows_are_read(self):
        self.assertEqual(issue_label("sick", load_details('{"officialLeaveUsed": true}')), "공가(병가)")
        self.assertEqual(resulting_status("vacation", {}), "officialLeave")

    def test_outing_label_shows_time_range(self):
        self.assertEqual(issue_label("outing", {"timeFrom": "13:00", "timeTo": "14:30"}), "외출 13:00~14:30")
        self.assertEqual(resulting_status("outing", {}), "outing")

    def test_public_row_hides_evidence_name_without_file(self):
        row = {
            "id": 5, "user_id": 8, "attendance_date": TODAY, "issue_type": "vacation", "status": "submitted",
            "details": '{"officialLeaveUsed": true, "evidenceName": "x.pdf"}', "evidence_storage_key": None,
            "reviewed_by_id": None, "reviewed_at": None, "created_at": None,
        }
        public = public_request(row, {8: "uid-a"}, lambda key: key)
        self.assertEqual((public["userId"], public["issueType"], public["label"]), ("uid-a", "absent", "공가(휴가)"))
        self.assertTrue(public["officialLeaveUsed"])
        self.assertIsNone(public["evidenceName"])


class MyAlertPopupsRouteTests(SimpleTestCase):
    def test_login_is_required(self):
        response = Client(HTTP_HOST="127.0.0.1").get("/api/alert-popups/mine")
        self.assertEqual(response.status_code, 401)


def _completion(content=None, calls=None):
    message = SimpleNamespace(content=content, tool_calls=calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _call(name, args):
    return SimpleNamespace(id=f"call-{name}", function=SimpleNamespace(name=name, arguments=json.dumps(args)))


class AdminAssistantTests(TestCase):
    @patch("lms.admin_assistant._log")
    @patch("lms.admin_assistant._cohort", return_value={"id": 2, "code": "cohort_34", "name": "34기"})
    @patch("lms.admin_assistant.connection")
    @patch("lms.admin_assistant.find_students")
    @patch("lms.admin_assistant.dispatch")
    def test_proposal_is_returned_without_executing(self, dispatch, find, connection, _cohort, _log):
        find.return_value = {"students": [{"uid": "uid-a", "name": "홍길동"}], "spotCheck": None}
        cur = MagicMock()
        cur.fetchall.side_effect = [[("uid-a", 8)], [("uid-a", "홍길동")]]
        connection.cursor.return_value.__enter__.return_value = cur
        client = Mock()
        client.chat.completions.create.side_effect = [
            _completion(calls=[_call("find_students", {"filters": ["missing_check_in", "missing_attendance_form"]})]),
            _completion(calls=[_call("propose_alert", {
                "title": "출결폼 제출 안내", "content": "출결폼을 제출해 주세요.", "target_user_ids": ["uid-a"],
            })]),
            _completion(content="홍길동 학생 1명에게 보낼 알림을 준비했습니다."),
        ]
        result = run_assistant(STAFF, 2, [{"role": "user", "content": "입실 안 하고 출결폼도 안 낸 사람에게 알림"}], client=client)
        find.assert_called_once()
        self.assertEqual(find.call_args.args[3], ["missing_check_in", "missing_attendance_form"])
        dispatch.assert_not_called()
        self.assertEqual(len(result["actions"]), 1)
        action = result["actions"][0]
        self.assertEqual((action["type"], action["targets"]), ("send_alert", [{"uid": "uid-a", "name": "홍길동"}]))

        self.assertEqual(result["context"], "[조회한 학생 1명] 홍길동(uid-a)")

    def test_student_is_forbidden(self):
        from lms.admin_assistant import AssistantError

        with self.assertRaises(AssistantError):
            run_assistant({"id": 1, "role": "student"}, 2, [{"role": "user", "content": "hi"}], client=Mock())

    @patch("lms.admin_assistant._log")
    @patch("lms.admin_assistant._cohort", return_value={"id": 2, "code": "cohort_34", "name": "34기"})
    @patch("lms.admin_assistant.dispatch", return_value={"id": "91"})
    def test_execute_alert_uses_existing_command_with_targets(self, dispatch, _cohort, _log):
        result = execute_action(STAFF, 2, {
            "type": "send_alert", "title": "출결폼", "content": "제출해 주세요",
            "targets": [{"uid": "uid-a", "name": "홍길동"}],
        })
        op, payload = dispatch.call_args.args[1], dispatch.call_args.args[2]
        self.assertEqual(op, "upsertAlertPopup")
        self.assertEqual(payload["targetUserIds"], ["uid-a"])
        self.assertEqual(payload["cohortId"], "cohort_34")
        self.assertEqual(result["popupId"], "91")


class AssistantReadToolTests(TestCase):
    COHORT = {"id": 2, "code": "cohort_34", "name": "34기"}

    def _session(self):
        from lms.admin_assistant import _Session

        return _Session(STAFF, self.COHORT)

    def test_attendance_stats_counts_and_filters_by_status(self):
        cur = MagicMock()
        cur.fetchall.return_value = [
            ("uid-a", "홍길동", "late", 3), ("uid-a", "홍길동", "absent", 1),
            ("uid-b", "김철수", "late", 1), ("uid-c", "이영희", "present", 9),
        ]
        session = self._session()
        result = session._tool_attendance_stats(cur, {
            "from_date": "2026-09-01", "to_date": "2026-09-30", "status": "late", "min_count": 3,
        })
        self.assertEqual(result["totals"]["late"], 4)
        self.assertEqual([s["uid"] for s in result["students"]], ["uid-a"])
        self.assertEqual(result["students"][0]["absent"], 1)
        self.assertEqual(session.memo(), "[조회한 학생 1명] 홍길동(uid-a)")

    def test_attendance_stats_rejects_too_long_range(self):
        with self.assertRaises(ValueError):
            self._session()._tool_attendance_stats(MagicMock(), {"from_date": "2026-01-01", "to_date": "2026-09-30"})

    def test_student_profile_returns_candidates_when_name_is_ambiguous(self):
        cur = MagicMock()
        cur.fetchall.return_value = [
            (1, "uid-a", "김민수", "a@x", 3, 0), (2, "uid-b", "김민수정", "b@x", 4, 0),
            (3, "uid-c", "박김민수", "c@x", 5, 0),
        ]
        result = self._session()._tool_student_profile(cur, {"name": "민수"})
        self.assertTrue(result["ambiguous"])
        self.assertEqual(len(result["candidates"]), 3)

    def test_student_profile_prefers_exact_name(self):
        cur = MagicMock()
        cur.fetchall.side_effect = [
            [(1, "uid-a", "김민수", "a@x", 3, 12000), (2, "uid-b", "김민수정", "b@x", 4, 0)],
            [], [], [], [],
        ]
        cur.fetchone.return_value = (1, 5000)
        result = self._session()._tool_student_profile(cur, {"name": "김민수"})
        self.assertEqual((result["uid"], result["mileageBalance"]), ("uid-a", 12000))
        self.assertEqual(result["pendingPurchases"], {"count": 1, "amount": 5000})
        self.assertNotIn("pk", result)

    @patch("lms.admin_assistant.find_students")
    def test_form_status_lists_missing_students_for_titled_task(self, find):
        find.return_value = {"students": [{"uid": "uid-a", "name": "홍길동"}, {"uid": "uid-b", "name": "김철수"}]}
        cur = MagicMock()
        cur.fetchall.side_effect = [
            [(7, "프로젝트 주제 조사", "builtin", None, True, 1)],
            [("uid-a",)],
        ]
        session = self._session()
        result = session._tool_form_status(cur, {"title": "주제"})
        task = result["tasks"][0]
        self.assertEqual((task["mode"], task["submitted"], task["total"]), ("builtin", 1, 2))
        self.assertEqual(task["missing"], [{"uid": "uid-b", "name": "김철수"}])
        self.assertIn("김철수(uid-b)", session.memo())

    def test_unknown_tool_and_bad_args_become_errors_for_the_model(self):
        session = self._session()
        self.assertIn("error", session.run_tool("drop_table", {}))
        with patch("lms.admin_assistant.connection") as connection:
            connection.cursor.return_value.__enter__.return_value = MagicMock()
            self.assertIn("error", session.run_tool("attendance_stats", {"status": "sleeping"}))
