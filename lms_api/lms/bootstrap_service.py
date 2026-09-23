"""bootstrap 스냅샷 조립. Postgres only."""

from __future__ import annotations

from django.db import connection

from lms.jsonutil import public_row
from lms.practice_service import practice_snapshot


def _dicts(cur):
    cols = [c[0] for c in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _pub_list(rows, uid_by_pk, code_by_pk):
    return [public_row(r, uid_by_pk, code_by_pk) for r in rows]


def build_bootstrap(user: dict) -> dict:
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
        attendances = q("SELECT * FROM attendances WHERE cohort_id = ANY(%s)", [cohort_ids])
        submissions = q("SELECT * FROM record_submissions WHERE cohort_id = ANY(%s)", [cohort_ids])
        # 이력서는 남의 것을 보내지 않는다. 학생은 제 것만, 강사 · 관리자는 맡은 기수 것만.
        if user["role"] in ("admin", "instructor"):
            resumes = q("SELECT * FROM resumes WHERE cohort_id = ANY(%s)", [cohort_ids])
        else:
            resumes = q("SELECT * FROM resumes WHERE user_id = %s", [user["id"]])
        feedbacks = q(
            "SELECT * FROM resume_feedback WHERE resume_id = ANY(%s)",
            [[r["id"] for r in resumes] or [-1]],
        )
        if user["role"] in ("admin", "instructor"):
            assessments = q("SELECT * FROM assessments WHERE cohort_id = ANY(%s)", [cohort_ids])
            questions = q("SELECT * FROM assessment_questions")
        else:
            assessments = q(
                "SELECT * FROM assessments WHERE cohort_id = ANY(%s) AND published = true",
                [cohort_ids],
            )
            questions = []
        products = q("SELECT * FROM mileage_products WHERE cohort_id = ANY(%s)", [cohort_ids])
        txs = q("SELECT * FROM mileage_transactions WHERE cohort_id = ANY(%s)", [cohort_ids])
        purchases = q("SELECT * FROM purchase_requests WHERE cohort_id = ANY(%s)", [cohort_ids])
        purchase_items = q(
            "SELECT * FROM purchase_request_items WHERE request_id = ANY(%s)",
            [[r["id"] for r in purchases] or [-1]],
        )
        forms = q("SELECT * FROM form_tasks WHERE cohort_id = ANY(%s)", [cohort_ids])
        inflearn = q("SELECT * FROM inflearn_packages WHERE cohort_id = ANY(%s)", [cohort_ids])
        youtube = q("SELECT * FROM youtube_recommendations WHERE cohort_id = ANY(%s)", [cohort_ids])
        sources = q("SELECT * FROM study_sources WHERE cohort_id = ANY(%s)", [cohort_ids])
        notes = q("SELECT * FROM study_notes WHERE user_id = %s", [user["id"]])
        sheets = q("SELECT * FROM curriculum_sheets WHERE cohort_id = ANY(%s)", [cohort_ids])
        sheet_ids = [s["id"] for s in sheets] or [-1]
        curriculum_rows = q(
            'SELECT * FROM curriculum_rows WHERE sheet_id = ANY(%s) ORDER BY "order"', [sheet_ids]
        )
        mileage_settings = q("SELECT * FROM mileage_settings WHERE cohort_id = ANY(%s)", [cohort_ids])
        cache = q("SELECT * FROM system_cache")
        rooms = q("SELECT * FROM seating_rooms WHERE cohort_id = ANY(%s)", [cohort_ids])
        room_ids = [r["id"] for r in rooms] or [-1]
        cells = q("SELECT * FROM seating_cells WHERE room_id = ANY(%s)", [room_ids])
        assignments = q("SELECT * FROM seating_assignments WHERE room_id = ANY(%s)", [room_ids])
        seats = q("SELECT * FROM seat_assignments WHERE room_id = ANY(%s)", [room_ids])
        teams = q("SELECT * FROM project_teams WHERE cohort_id = ANY(%s)", [cohort_ids])
        team_ids = [t["id"] for t in teams] or [-1]
        members = q("SELECT * FROM project_team_members WHERE team_id = ANY(%s)", [team_ids])
        practice = practice_snapshot(cur, user, [c["code"] for c in cohorts if c.get("code")])
        pdfs = q("SELECT * FROM curriculum_pdfs WHERE cohort_id = ANY(%s)", [cohort_ids])
        intakes = q(
            """SELECT si.* FROM student_intakes si
               JOIN users u ON u.id = si.user_id
               WHERE u.cohort_id = ANY(%s)""",
            [cohort_ids],
        )
        cart = q("SELECT * FROM mileage_cart_items WHERE user_id = %s", [user["id"]])
        materials = q("SELECT * FROM materials WHERE cohort_id = ANY(%s)", [cohort_ids])
        assignments_t = q("SELECT * FROM assignments WHERE cohort_id = ANY(%s)", [cohort_ids])
        schedules = q("SELECT * FROM schedules WHERE cohort_id = ANY(%s)", [cohort_ids])
        weekly = q("SELECT * FROM weekly_tasks WHERE cohort_id = ANY(%s)", [cohort_ids])
        progress = q("SELECT * FROM weekly_progress WHERE cohort_id = ANY(%s)", [cohort_ids])
        missions = q("SELECT * FROM mission_progress WHERE cohort_id = ANY(%s)", [cohort_ids])
        form_responses = q(
            "SELECT * FROM form_responses WHERE task_id IN (SELECT id FROM form_tasks WHERE cohort_id = ANY(%s))",
            [cohort_ids],
        )
        roll_calls = q("SELECT * FROM roll_calls WHERE cohort_id = ANY(%s)", [cohort_ids])
        roll_entries = q(
            "SELECT * FROM roll_call_entries WHERE roll_call_id = ANY(%s)",
            [[r["id"] for r in roll_calls] or [-1]],
        )
        assess_subs = q(
            """SELECT s.* FROM assessment_submissions s
               JOIN assessments a ON a.id = s.assessment_id
               WHERE a.cohort_id = ANY(%s)""",
            [cohort_ids],
        )
        assess_answers = q(
            "SELECT * FROM assessment_answers WHERE submission_id = ANY(%s)",
            [[s["id"] for s in assess_subs] or [-1]],
        )
        logs = (
            q("SELECT * FROM ai_generation_logs WHERE cohort_id = ANY(%s)", [cohort_ids])
            if user["role"] == "admin"
            else []
        )
        published = None
        seating = None
        published_by_cohort = {
            c["code"]: str(c["published_seating_room_id"])
            for c in cohorts
            if c.get("published_seating_room_id")
        }
        mine = next((c for c in cohorts if c["id"] == user.get("cohort_id")), None) or (
            cohorts[0] if cohorts else None
        )
        if mine:
            room_id = mine.get("published_seating_room_id")
            if room_id:
                assignment = next((a for a in assignments if a["room_id"] == room_id), None)
                if user["role"] in ("admin", "instructor") or (
                    assignment and assignment.get("status") == "published"
                ):
                    room = next((r for r in rooms if r["id"] == room_id), None)
                    seating = {
                        "room": public_row(room, uid_by_pk, code_by_pk) if room else None,
                        "cells": _pub_list(
                            [c for c in cells if c["room_id"] == room_id], uid_by_pk, code_by_pk
                        ),
                        "assignment": public_row(assignment, uid_by_pk, code_by_pk)
                        if assignment
                        else None,
                        "seats": _pub_list(
                            [s for s in seats if s["room_id"] == room_id], uid_by_pk, code_by_pk
                        ),
                    }
                    published = str(room_id)

    pub = lambda rows: _pub_list(rows, uid_by_pk, code_by_pk)
    return {
        "me": {**user, "uid": user["firebase_uid"], "cohortId": user.get("cohort_code")},
        "users": pub(users),
        "cohorts": pub(cohorts),
        "notices": pub(notices),
        "scheduledNotices": pub(scheduled),
        "alertPopups": pub(alerts),
        "alertPopupDismissals": pub(dismissals),
        "todos": pub(todos),
        "attendances": pub(attendances),
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
        "seatingRooms": pub(rooms),
        "seatingCells": pub(cells),
        "seatingAssignments": pub(assignments),
        "seatAssignments": pub(seats),
        "projectTeams": pub(teams),
        "projectTeamMembers": pub(members),
        # 복습 문제(practice 스키마) — 화면 모양 그대로
        **practice,
        "studentIntakes": pub(intakes),
        "materials": pub(materials),
        "assignments": pub(assignments_t),
        "schedules": pub(schedules),
        "weeklyTasks": pub(weekly),
        "weeklyProgress": pub(progress),
        "missionProgress": pub(missions),
        "aiGenerationLogs": pub(logs),
        "rollCalls": pub(roll_calls),
        "rollCallEntries": pub(roll_entries),
        "publishedSeatingRoomId": published,
        "publishedSeatingRooms": published_by_cohort,
        "seating": seating,
    }
