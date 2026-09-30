"""bootstrap 스냅샷 조립. Postgres only."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from django.db import close_old_connections, connection

from lms.attendance_requests import public_request
from lms.jsonutil import public_row
from lms.practice_service import practice_snapshot
from lms.seating_layout import seating_payload
from lms.storage import read_url, signed_read_url


def _dicts(cur):
    columns = cur.description or []
    names = [column[0] for column in columns]
    json_positions = {i for i, column in enumerate(columns) if column.type_code in (114, 3802)}
    rows = []
    for raw in cur.fetchall():
        values = [json.loads(value) if i in json_positions and isinstance(value, str) else value
                  for i, value in enumerate(raw)]
        rows.append(dict(zip(names, values)))
    return rows


def _pub_list(rows, uid_by_pk, code_by_pk):
    return [public_row(r, uid_by_pk, code_by_pk) for r in rows]


def _query_group(specs: list[tuple[str, tuple[str, list] | Callable]], cur=None) -> dict[str, Any]:
    """Run one independent query group on one thread-local Django connection."""
    own_cursor = cur is None
    if own_cursor:
        close_old_connections()
        cur = connection.cursor()
    try:
        result = {}
        pending: list[tuple[str, tuple[str, list]]] = []

        def flush() -> None:
            if not pending:
                return
            cursors = []
            try:
                with connection.connection.pipeline() as pipeline:
                    for name, (sql, args) in pending:
                        query_cur = connection.cursor()
                        cursors.append((name, query_cur))
                        query_cur.execute(sql, args)
                    pipeline.sync()
                    for name, query_cur in cursors:
                        result[name] = _dicts(query_cur)
            finally:
                for _, query_cur in cursors:
                    query_cur.close()
                pending.clear()

        for name, spec in specs:
            if callable(spec):
                flush()
                result[name] = spec(cur)
            else:
                pending.append((name, spec))
        flush()
        return result
    finally:
        if own_cursor:
            cur.close()
            connection.close()


def _parallel_queries(cur, specs: dict[str, tuple[str, list] | Callable]) -> dict[str, Any]:
    """Overlap independent RDS round trips with two short-lived read connections."""
    groups: list[list[tuple[str, tuple[str, list] | Callable]]] = [[], [], []]
    # Practice runs several dependent statements within one task. Account for
    # that work before distributing the single-query tasks across groups.
    weights = {"practice": 6, "resumes": 2, "notes": 2, "submissions": 2}
    loads = [0, 3, 3]  # Worker groups also open an RDS connection.
    for name, spec in sorted(specs.items(), key=lambda item: weights.get(item[0], 1), reverse=True):
        index = min(range(len(groups)), key=lambda group: loads[group])
        groups[index].append((name, spec))
        loads[index] += weights.get(name, 1)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_query_group, group) for group in groups[1:]]
        result = _query_group(groups[0], cur)
        for future in futures:
            result.update(future.result())
    return result


def build_bootstrap(user: dict) -> dict:
    is_student = user["role"] == "student"
    with connection.cursor() as cur:
        cur.execute("SELECT id, firebase_uid FROM users")
        uid_by_pk = {r[0]: r[1] for r in cur.fetchall()}
        cur.execute("SELECT id, code FROM cohorts")
        code_by_pk = {r[0]: r[1] for r in cur.fetchall()}
        if user["role"] == "admin":
            cur.execute(
                """SELECT u.*, c.code AS cohort_code, c.name AS cohort_name
                   FROM users u LEFT JOIN cohorts c ON c.id = u.cohort_id"""
            )
        elif user["role"] == "instructor":
            cur.execute(
                """SELECT u.*, c.code AS cohort_code, c.name AS cohort_name
                   FROM users u LEFT JOIN cohorts c ON c.id = u.cohort_id
                   WHERE u.cohort_id = %s OR u.id = %s""",
                [user["cohort_id"], user["id"]],
            )
        else:
            cur.execute(
                """SELECT u.*, c.code AS cohort_code, c.name AS cohort_name
                   FROM users u LEFT JOIN cohorts c ON c.id = u.cohort_id
                   WHERE u.id = %s OR (u.cohort_id = %s AND u.role IN ('student','instructor'))""",
                [user["id"], user["cohort_id"]],
            )
        users = _dicts(cur)
        user_ids = [row["id"] for row in users] or [-1]
        cur.execute(
            """SELECT us.user_id, s.canonical_name
               FROM user_skills us JOIN skills s ON s.id = us.skill_id
               WHERE us.user_id = ANY(%s) ORDER BY s.canonical_name""",
            [user_ids],
        )
        skills_by_user = {}
        for user_id, skill_name in cur.fetchall():
            skills_by_user.setdefault(user_id, []).append(skill_name)
        cur.execute(
            "SELECT user_id, preferences FROM user_job_preferences WHERE user_id = ANY(%s)",
            [user_ids],
        )
        preferences_by_user = dict(cur.fetchall())
        for row in users:
            row["skills"] = skills_by_user.get(row["id"], [])
            row["job_preferences"] = preferences_by_user.get(row["id"], {})
        if user["role"] == "admin":
            cur.execute("SELECT * FROM cohorts")
        else:
            cur.execute("SELECT * FROM cohorts WHERE id = %s", [user["cohort_id"]])
        cohorts = _dicts(cur)
        cohort_ids = [c["id"] for c in cohorts] or [-1]

        def q(sql, args=None):
            cur.execute(sql, args or [])
            return _dicts(cur)

        # These lookups only depend on the authenticated user and visible cohorts.
        # Execute at most three groups concurrently; each worker owns its cursor.
        cohort_filter = [cohort_ids]
        private_filter = [cohort_ids, is_student, user["id"]]
        specs: dict[str, tuple[str, list] | Callable] = {
            "notices": (
                "SELECT * FROM notices WHERE cohort_id = ANY(%s) ORDER BY created_at DESC NULLS LAST",
                cohort_filter,
            ),
            # 학생에게는 기수 전체 알림과 자기에게 지정된 알림만 보낸다
            "alerts": (
                """SELECT p.*, u.display_name AS author_name FROM alert_popups p
                   LEFT JOIN users u ON u.id = p.author_id WHERE p.cohort_id = ANY(%s)
                   AND (%s = false
                        OR NOT EXISTS (SELECT 1 FROM alert_popup_targets t WHERE t.popup_id = p.id)
                        OR EXISTS (SELECT 1 FROM alert_popup_targets t WHERE t.popup_id = p.id AND t.user_id = %s))
                   ORDER BY p.sort_order NULLS LAST, p.created_at DESC NULLS LAST""",
                private_filter,
            ),
            "dismissals": ("SELECT * FROM alert_popup_dismissals WHERE user_id = %s", [user["id"]]),
            "my_alert_reads": ("SELECT popup_id FROM alert_popup_reads WHERE user_id = %s", [user["id"]]),
            "todos": ("SELECT * FROM todos WHERE user_id = %s", [user["id"]]),
            "attendances": (
                """SELECT a.*, a.attendance_date AS date_key FROM attendances a
                   WHERE a.cohort_id = ANY(%s) AND (%s = false OR a.user_id = %s)""",
                private_filter,
            ),
            "submissions": (
                """SELECT rs.*,
                          COALESCE(array_agg(rf.storage_key ORDER BY rf.id)
                                   FILTER (WHERE rf.id IS NOT NULL), ARRAY[]::varchar[]) AS file_urls
                   FROM record_submissions rs
                   LEFT JOIN record_submission_files rf ON rf.submission_id = rs.id
                   WHERE rs.cohort_id = ANY(%s) AND (%s = false OR rs.user_id = %s)
                   GROUP BY rs.id""",
                private_filter,
            ),
            "resumes": (
                """SELECT r.*, COALESCE(r.content->'section_status', '{}'::jsonb) AS sections
                   FROM resumes r WHERE r.cohort_id = ANY(%s)
                   AND (%s = false OR r.user_id = %s)""",
                private_filter,
            ),
            "feedbacks": (
                """SELECT f.* FROM resume_feedback f JOIN resumes r ON r.id = f.resume_id
                   WHERE r.cohort_id = ANY(%s) AND (%s = false OR r.user_id = %s)""",
                private_filter,
            ),
            "products": ("SELECT * FROM mileage_products WHERE cohort_id = ANY(%s)", cohort_filter),
            "txs": (
                "SELECT * FROM mileage_transactions WHERE cohort_id = ANY(%s) AND (%s = false OR user_id = %s)",
                private_filter,
            ),
            "purchases": (
                "SELECT * FROM purchase_requests WHERE cohort_id = ANY(%s) AND (%s = false OR user_id = %s)",
                private_filter,
            ),
            "forms": (
                """SELECT DISTINCT ON (st.id) st.*, stc.cohort_id, st.external_url AS form_url,
                          st.guide_url AS notion_guide_url
                   FROM submission_tasks st
                   JOIN submission_task_cohorts stc ON stc.task_id = st.id
                   WHERE stc.cohort_id = ANY(%s)
                   ORDER BY st.id""",
                cohort_filter,
            ),
            "inflearn": ("SELECT * FROM inflearn_packages WHERE cohort_id = ANY(%s)", cohort_filter),
            "youtube": ("SELECT * FROM youtube_recommendations WHERE cohort_id = ANY(%s)", cohort_filter),
            "sources": ("SELECT * FROM study_sources WHERE cohort_id = ANY(%s)", cohort_filter),
            "notes": (
                """SELECT n.*, COALESCE(s.legacy_id, s.id::text) AS source_key
                   FROM study_notes n LEFT JOIN study_sources s ON s.id = n.source_id
                   WHERE n.user_id = %s""",
                [user["id"]],
            ),
            "sheets": ("SELECT * FROM curriculum_sheets WHERE cohort_id = ANY(%s)", cohort_filter),
            "mileage_settings": ("SELECT * FROM mileage_settings WHERE cohort_id = ANY(%s)", cohort_filter),
            "cache": ("SELECT * FROM system_cache WHERE key LIKE 'qualExam%%'", []),
            "rooms": (
                "SELECT * FROM cohort_seating WHERE cohort_id = ANY(%s) AND (%s = false OR published = true)",
                [cohort_ids, is_student],
            ),
            "teams": ("SELECT * FROM project_teams WHERE cohort_id = ANY(%s)", cohort_filter),
            "pdfs": ("SELECT * FROM curriculum_pdfs WHERE cohort_id = ANY(%s)", cohort_filter),
            "intakes": (
                """SELECT si.* FROM student_intakes si JOIN users u ON u.id = si.user_id
                   WHERE u.cohort_id = ANY(%s) AND (%s = false OR si.user_id = %s)""",
                private_filter,
            ),
            "cart": ("SELECT * FROM mileage_cart_items WHERE user_id = %s", [user["id"]]),
            "materials": ("SELECT * FROM materials WHERE cohort_id = ANY(%s)", cohort_filter),
            "schedules": ("SELECT * FROM schedules WHERE cohort_id = ANY(%s)", cohort_filter),
            "missions": (
                "SELECT * FROM mission_progress WHERE cohort_id = ANY(%s) AND (%s = false OR user_id = %s)",
                private_filter,
            ),
            "form_responses": (
                """SELECT sr.*, COALESCE(st.legacy_id, st.id::text) AS task_id,
                          sr.external_response_id AS google_response_id
                   FROM submission_responses sr
                   JOIN submission_tasks st ON st.id = sr.task_id
                   WHERE sr.task_id IN (
                     SELECT task_id FROM submission_task_cohorts WHERE cohort_id = ANY(%s)
                   ) AND (%s = false OR sr.user_id = %s)""",
                private_filter,
            ),
            "practice": lambda practice_cur: practice_snapshot(
                practice_cur, user, [code_by_pk[pk] for pk in cohort_ids if pk in code_by_pk],
            ),
            "assess_subs": (
                """SELECT s.* FROM assessment_submissions s
                   JOIN assessments a ON a.id = s.assessment_id
                   WHERE a.cohort_id = ANY(%s) AND (%s = false OR s.user_id = %s)""",
                private_filter,
            ),
        }
        if user["role"] == "admin":
            specs["scheduled"] = (
                """SELECT sn.*, u.display_name AS author_name FROM scheduled_notices sn
                   LEFT JOIN users u ON u.id = sn.author_id WHERE sn.cohort_id = ANY(%s)
                   ORDER BY sn.created_at DESC NULLS LAST""",
                cohort_filter,
            )
            specs["logs"] = ("SELECT * FROM ai_generation_logs WHERE cohort_id = ANY(%s)", cohort_filter)
        if not is_student:
            specs["seat_presences"] = ("SELECT * FROM seat_presences WHERE cohort_id = ANY(%s)", cohort_filter)
            specs["presence_checks"] = (
                """SELECT pc.*, u.display_name AS checked_by_name FROM presence_checks pc
                   LEFT JOIN users u ON u.id = pc.checked_by
                   WHERE pc.cohort_id = ANY(%s) ORDER BY pc.checked_at DESC""",
                cohort_filter,
            )
            specs["presence_check_items"] = (
                """SELECT i.* FROM presence_check_items i
                   JOIN presence_checks pc ON pc.id = i.presence_check_id
                   WHERE pc.cohort_id = ANY(%s)""",
                cohort_filter,
            )
            specs["alert_targets"] = (
                """SELECT t.popup_id, t.user_id FROM alert_popup_targets t
                   JOIN alert_popups p ON p.id = t.popup_id WHERE p.cohort_id = ANY(%s)""",
                cohort_filter,
            )
            specs["alert_reads"] = (
                """SELECT r.popup_id, r.user_id, r.read_at FROM alert_popup_reads r
                   JOIN alert_popups p ON p.id = r.popup_id WHERE p.cohort_id = ANY(%s)""",
                cohort_filter,
            )
        # 출결 신청 — 학생은 자기 것만
        specs["attendance_issues"] = (
            """SELECT id, user_id, cohort_id, attendance_date, issue_type, status, details,
                      evidence_storage_key, reviewed_by_id, reviewed_at, created_at
               FROM attendance_issue_reports
               WHERE cohort_id = ANY(%s) AND (%s = false OR user_id = %s)
               ORDER BY attendance_date DESC, created_at DESC""",
            private_filter,
        )
        if user["role"] in ("admin", "instructor"):
            specs["assessments"] = ("SELECT * FROM assessments WHERE cohort_id = ANY(%s)", cohort_filter)
            specs["questions"] = (
                """SELECT aq.* FROM assessment_questions aq
                   JOIN assessments a ON a.id = aq.assessment_id
                   WHERE a.cohort_id = ANY(%s)""",
                cohort_filter,
            )
        else:
            specs["assessments"] = (
                "SELECT * FROM assessments WHERE cohort_id = ANY(%s) AND published = true",
                cohort_filter,
            )

        fetched = _parallel_queries(cur, specs)
        notices = fetched["notices"]
        scheduled = fetched.get("scheduled", [])
        alerts = fetched["alerts"]
        dismissals = fetched["dismissals"]
        todos = fetched["todos"]
        attendances = fetched["attendances"]
        seat_presences = fetched.get("seat_presences", [])
        presence_checks = fetched.get("presence_checks", [])
        items_by_check: dict[int, list] = {}
        for item in fetched.get("presence_check_items", []):
            items_by_check.setdefault(item["presence_check_id"], []).append({
                "userId": uid_by_pk.get(item["user_id"]),
                "state": item["state"],
                "reason": item["reason"],
            })
        for check in presence_checks:
            check["items"] = items_by_check.get(check["id"], [])
        targets_by_popup: dict[int, list] = {}
        for target in fetched.get("alert_targets", []):
            if target["user_id"] in uid_by_pk:
                targets_by_popup.setdefault(target["popup_id"], []).append(uid_by_pk[target["user_id"]])
        reads_by_popup: dict[int, list] = {}
        for read in fetched.get("alert_reads", []):
            if read["user_id"] in uid_by_pk:
                reads_by_popup.setdefault(read["popup_id"], []).append({
                    "uid": uid_by_pk[read["user_id"]],
                    "readAt": read["read_at"].isoformat() if read.get("read_at") else None,
                })
        my_alert_reads = [str(row["popup_id"]) for row in fetched.get("my_alert_reads", [])]
        attendance_issues = fetched.get("attendance_issues", [])
        submissions = fetched["submissions"]
        for submission in submissions:
            submission["file_urls"] = [
                url for url in (read_url(key) for key in submission.get("file_urls") or []) if url
            ]
        resumes = fetched["resumes"]
        feedbacks = fetched["feedbacks"]
        assessments = fetched["assessments"]
        questions = fetched.get("questions", [])
        products = fetched["products"]
        txs = fetched["txs"]
        purchases = fetched["purchases"]
        purchase_items = q(
            "SELECT * FROM purchase_request_items WHERE request_id = ANY(%s)",
            [[row["id"] for row in purchases] or [-1]],
        )
        forms = fetched["forms"]
        inflearn = fetched["inflearn"]
        youtube = fetched["youtube"]
        sources = fetched["sources"]
        notes = fetched["notes"]
        for note in notes:
            note["source_id"] = note.pop("source_key")
        sheets = fetched["sheets"]
        curriculum_rows = q(
            'SELECT * FROM curriculum_rows WHERE sheet_id = ANY(%s) ORDER BY "order"',
            [[row["id"] for row in sheets] or [-1]],
        )
        mileage_settings = fetched["mileage_settings"]
        cache = fetched["cache"]
        rooms = fetched["rooms"]
        seating_view = seating_payload(rooms, code_by_pk)
        teams = fetched["teams"]
        members = q(
            "SELECT * FROM project_team_members WHERE team_id = ANY(%s)",
            [[row["id"] for row in teams] or [-1]],
        )
        pdfs = fetched["pdfs"]
        intakes = fetched["intakes"]
        cart = fetched["cart"]
        materials = fetched["materials"]
        assignments_t = []
        schedules = fetched["schedules"]
        weekly = []
        progress = []
        missions = fetched["missions"]
        form_responses = fetched["form_responses"]
        practice = fetched["practice"]
        assess_subs = fetched["assess_subs"]
        assess_answers = q(
            "SELECT * FROM assessment_answers WHERE submission_id = ANY(%s)",
            [[row["id"] for row in assess_subs] or [-1]],
        )
        logs = fetched.get("logs", [])
        published = None
        seating = None
        if cohorts:
            room = next((r for r in rooms if r["cohort_id"] == cohorts[0]["id"]), None)
            if room and (user["role"] in ("admin", "instructor") or room.get("published")):
                layout = room.get("layout") or {}
                if isinstance(layout, str):
                    try:
                        layout = json.loads(layout)
                    except json.JSONDecodeError:
                        layout = {}
                if not isinstance(layout, dict):
                    layout = {}
                seating = {
                    "room": public_row(room, uid_by_pk, code_by_pk),
                    "cells": layout.get("cells", []),
                    "assignment": {"status": "published" if room.get("published") else "draft"},
                    "seats": layout.get("assignments", {}),
                }
                published = seating_view["publishedSeatingRooms"].get(code_by_pk.get(room["cohort_id"]))

    pub = lambda rows: _pub_list(rows, uid_by_pk, code_by_pk)
    public_users = pub(users)
    peer_fields = {
        "id", "pk", "uid", "firebaseUid", "displayName", "role", "cohortId",
        "cohortCode", "cohortName", "seatNumber", "photoStorageKey", "skills",
    }
    for raw, public_user in zip(users, public_users):
        public_user.pop("password", None)
        if is_student and raw["id"] != user["id"]:
            for key in list(public_user):
                if key not in peer_fields:
                    del public_user[key]
    public_notices = pub(notices)
    for row, public_notice in zip(notices, public_notices):
        if row.get("image_storage_key"):
            public_notice["imageUrl"] = signed_read_url(row["image_storage_key"])
    public_alerts = pub(alerts)
    if not is_student:
        for row, public_alert in zip(alerts, public_alerts):
            public_alert["targetUserIds"] = targets_by_popup.get(row["id"], [])
            public_alert["readBy"] = reads_by_popup.get(row["id"], [])
    public_checks = pub(presence_checks)
    for row, public_check in zip(presence_checks, public_checks):
        public_check["checkedBy"] = uid_by_pk.get(row["checked_by"])

    return {
        "me": {**user, "uid": user["firebase_uid"], "cohortId": user.get("cohort_code")},
        "users": public_users,
        "cohorts": pub(cohorts),
        "notices": public_notices,
        "scheduledNotices": pub(scheduled),
        "alertPopups": public_alerts,
        "alertPopupDismissals": pub(dismissals),
        "alertPopupReadIds": my_alert_reads,
        "todos": pub(todos),
        "attendances": pub(attendances),
        "seatPresences": pub(seat_presences),
        "presenceChecks": public_checks,
        "attendanceIssues": [public_request(row, uid_by_pk, read_url) for row in attendance_issues],
        "submissions": pub(submissions),
        "resumes": pub(resumes),
        "resumeFeedbacks": pub(feedbacks),
        "assessments": pub(assessments),
        "assessmentQuestions": pub(questions),
        "assessmentSubmissions": pub(assess_subs),
        "assessmentAnswers": pub(assess_answers),
        "mileageProducts": pub(products),
        "mileageTransactions": pub(txs),
        "purchaseRequests": pub(purchases),
        "purchaseRequestItems": pub(purchase_items),
        "formTasks": pub(forms),
        "formResponses": pub(form_responses),
        "inflearnPackages": pub(inflearn),
        "youtubeRecommendations": pub(youtube),
        "studySources": pub(sources),
        "studyNotes": pub(notes),
        "curriculumSheets": pub(sheets),
        "curriculumRows": pub(curriculum_rows),
        "curriculumPdfs": pub(pdfs),
        "mileageSettings": pub(mileage_settings),
        "mileageCartItems": pub(cart),
        "systemCache": pub(cache),
        "seatingRooms": seating_view["seatingRooms"],
        "seatingCells": seating_view["seatingCells"],
        "seatingAssignments": seating_view["seatingAssignments"],
        "seatAssignments": seating_view["seatAssignments"],
        "publishedSeatingRooms": seating_view["publishedSeatingRooms"],
        "projectTeams": pub(teams),
        "projectTeamMembers": pub(members),
        "studentIntakes": pub(intakes),
        "materials": pub(materials),
        "assignments": pub(assignments_t),
        "schedules": pub(schedules),
        "weeklyTasks": pub(weekly),
        "weeklyProgress": pub(progress),
        "missionProgress": pub(missions),
        "aiGenerationLogs": pub(logs),
        "publishedSeatingRoomId": published,
        "seating": seating,
        **practice,
    }
