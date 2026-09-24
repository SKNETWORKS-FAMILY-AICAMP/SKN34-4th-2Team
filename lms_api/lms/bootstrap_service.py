"""bootstrap 스냅샷 조립. Postgres only."""

from __future__ import annotations

import json

from django.db import connection

from lms.jsonutil import public_row
from lms.storage import signed_read_url


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

        notices = q(
            "SELECT * FROM notices WHERE cohort_id = ANY(%s) ORDER BY created_at DESC NULLS LAST",
            [cohort_ids],
        )
        scheduled = (
            q(
                """SELECT sn.*, u.display_name AS author_name
                   FROM scheduled_notices sn
                   LEFT JOIN users u ON u.id = sn.author_id
                   WHERE sn.cohort_id = ANY(%s)
                   ORDER BY sn.created_at DESC NULLS LAST""",
                [cohort_ids],
            )
            if user["role"] == "admin"
            else []
        )
        alerts = q(
            """SELECT p.*, u.display_name AS author_name
               FROM alert_popups p
               LEFT JOIN users u ON u.id = p.author_id
               WHERE p.cohort_id = ANY(%s)
               ORDER BY p.sort_order NULLS LAST, p.created_at DESC NULLS LAST""",
            [cohort_ids],
        )
        dismissals = q(
            "SELECT * FROM alert_popup_dismissals WHERE user_id = %s",
            [user["id"]],
        )
        todos = q("SELECT * FROM todos WHERE user_id = %s", [user["id"]])
        attendances = q(
            """SELECT a.*, a.attendance_date AS date_key FROM attendances a
               WHERE a.cohort_id = ANY(%s) AND (%s = false OR a.user_id = %s)""",
            [cohort_ids, is_student, user["id"]],
        )
        seat_presences = (
            q("SELECT * FROM seat_presences WHERE cohort_id = ANY(%s)", [cohort_ids])
            if not is_student else []
        )
        submissions = q(
            """SELECT rs.*,
                      COALESCE(array_agg(rf.storage_key ORDER BY rf.id)
                               FILTER (WHERE rf.id IS NOT NULL), ARRAY[]::varchar[]) AS file_urls
               FROM record_submissions rs
               LEFT JOIN record_submission_files rf ON rf.submission_id = rs.id
               WHERE rs.cohort_id = ANY(%s) AND (%s = false OR rs.user_id = %s)
               GROUP BY rs.id""",
            [cohort_ids, is_student, user["id"]],
        )
        resumes = q(
            """SELECT r.*, COALESCE(r.content->'section_status', '{}'::jsonb) AS sections
               FROM resumes r WHERE r.cohort_id = ANY(%s)
               AND (%s = false OR r.user_id = %s)""",
            [cohort_ids, is_student, user["id"]],
        )
        feedbacks = q(
            """SELECT f.* FROM resume_feedback f JOIN resumes r ON r.id = f.resume_id
               WHERE r.cohort_id = ANY(%s) AND (%s = false OR r.user_id = %s)""",
            [cohort_ids, is_student, user["id"]],
        )
        if user["role"] in ("admin", "instructor"):
            assessments = q("SELECT * FROM assessments WHERE cohort_id = ANY(%s)", [cohort_ids])
            questions = q(
                """SELECT aq.* FROM assessment_questions aq
                   JOIN assessments a ON a.id = aq.assessment_id
                   WHERE a.cohort_id = ANY(%s)""",
                [cohort_ids],
            )
        else:
            assessments = q(
                "SELECT * FROM assessments WHERE cohort_id = ANY(%s) AND published = true",
                [cohort_ids],
            )
            questions = []
        products = q("SELECT * FROM mileage_products WHERE cohort_id = ANY(%s)", [cohort_ids])
        txs = q(
            "SELECT * FROM mileage_transactions WHERE cohort_id = ANY(%s) AND (%s = false OR user_id = %s)",
            [cohort_ids, is_student, user["id"]],
        )
        purchases = q(
            "SELECT * FROM purchase_requests WHERE cohort_id = ANY(%s) AND (%s = false OR user_id = %s)",
            [cohort_ids, is_student, user["id"]],
        )
        forms = q(
            """SELECT st.*, stc.cohort_id, st.external_url AS form_url, st.guide_url AS notion_guide_url
               FROM submission_tasks st
               JOIN submission_task_cohorts stc ON stc.task_id = st.id
               WHERE stc.cohort_id = ANY(%s)""",
            [cohort_ids],
        )
        inflearn = q("SELECT * FROM inflearn_packages WHERE cohort_id = ANY(%s)", [cohort_ids])
        youtube = q("SELECT * FROM youtube_recommendations WHERE cohort_id = ANY(%s)", [cohort_ids])
        sources = q("SELECT * FROM study_sources WHERE cohort_id = ANY(%s)", [cohort_ids])
        notes = q("SELECT * FROM study_notes WHERE user_id = %s", [user["id"]])
        sheets = q("SELECT * FROM curriculum_sheets WHERE cohort_id = ANY(%s)", [cohort_ids])
        mileage_settings = q("SELECT * FROM mileage_settings WHERE cohort_id = ANY(%s)", [cohort_ids])
        cache = q("SELECT * FROM system_cache")
        rooms = q(
            "SELECT * FROM cohort_seating WHERE cohort_id = ANY(%s) AND (%s = false OR published = true)",
            [cohort_ids, is_student],
        )
        cells = []
        assignments = []
        seats = []
        teams = q("SELECT * FROM project_teams WHERE cohort_id = ANY(%s)", [cohort_ids])
        pdfs = q("SELECT * FROM curriculum_pdfs WHERE cohort_id = ANY(%s)", [cohort_ids])
        intakes = q(
            """SELECT si.* FROM student_intakes si
               JOIN users u ON u.id = si.user_id
               WHERE u.cohort_id = ANY(%s) AND (%s = false OR si.user_id = %s)""",
            [cohort_ids, is_student, user["id"]],
        )
        cart = q("SELECT * FROM mileage_cart_items WHERE user_id = %s", [user["id"]])
        materials = q("SELECT * FROM materials WHERE cohort_id = ANY(%s)", [cohort_ids])
        assignments_t = []
        schedules = q("SELECT * FROM schedules WHERE cohort_id = ANY(%s)", [cohort_ids])
        weekly = []
        progress = []
        missions = q(
            "SELECT * FROM mission_progress WHERE cohort_id = ANY(%s) AND (%s = false OR user_id = %s)",
            [cohort_ids, is_student, user["id"]],
        )
        form_responses = q(
            """SELECT sr.*, sr.external_response_id AS google_response_id
               FROM submission_responses sr
               WHERE sr.task_id IN (
                 SELECT task_id FROM submission_task_cohorts WHERE cohort_id = ANY(%s)
               ) AND (%s = false OR sr.user_id = %s)""",
            [cohort_ids, is_student, user["id"]],
        )
        assess_subs = q(
            """SELECT s.* FROM assessment_submissions s
               JOIN assessments a ON a.id = s.assessment_id
               WHERE a.cohort_id = ANY(%s) AND (%s = false OR s.user_id = %s)""",
            [cohort_ids, is_student, user["id"]],
        )
        logs = (
            q("SELECT * FROM ai_generation_logs WHERE cohort_id = ANY(%s)", [cohort_ids])
            if user["role"] == "admin"
            else []
        )
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
                published = str(room["cohort_id"])

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

    return {
        "me": {**user, "uid": user["firebase_uid"], "cohortId": user.get("cohort_code")},
        "users": public_users,
        "cohorts": pub(cohorts),
        "notices": public_notices,
        "scheduledNotices": pub(scheduled),
        "alertPopups": pub(alerts),
        "alertPopupDismissals": pub(dismissals),
        "todos": pub(todos),
        "attendances": pub(attendances),
        "seatPresences": pub(seat_presences),
        "submissions": pub(submissions),
        "resumes": pub(resumes),
        "resumeFeedbacks": pub(feedbacks),
        "assessments": pub(assessments),
        "assessmentQuestions": pub(questions),
        "assessmentSubmissions": pub(assess_subs),
        "mileageProducts": pub(products),
        "mileageTransactions": pub(txs),
        "purchaseRequests": pub(purchases),
        "formTasks": pub(forms),
        "formResponses": pub(form_responses),
        "inflearnPackages": pub(inflearn),
        "youtubeRecommendations": pub(youtube),
        "studySources": pub(sources),
        "studyNotes": pub(notes),
        "curriculumSheets": pub(sheets),
        "curriculumPdfs": pub(pdfs),
        "mileageSettings": pub(mileage_settings),
        "mileageCartItems": pub(cart),
        "systemCache": pub(cache),
        "seatingRooms": pub(rooms),
        "seatingCells": pub(cells),
        "seatingAssignments": pub(assignments),
        "seatAssignments": pub(seats),
        "projectTeams": pub(teams),
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
    }
