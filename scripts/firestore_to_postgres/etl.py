"""Read-only Firestore → PostgreSQL ETL. Does not write to Firestore."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import firebase_admin
import psycopg
from django.contrib.auth.hashers import make_password
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_document import DocumentSnapshot
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parent
REPORT = ROOT.parents[1] / "docs" / "migration-report.md"

COHORT_STATUS = {"upcoming": "planned", "archived": "closed", "active": "active", "planned": "planned", "closed": "closed"}
SKIP_INTAKE_KEYS = {"email", "displayName", "cohortId", "cohortName", "seatNumber", "personalEmail", "initialPassword", "passwordChanged"}
COPY_DROP = {
    "userDisplayName", "authorName", "cohortName", "seatNames", "commentCount",
    "feedbackCount", "responseCount", "questionCount", "uploadedByName",
    "processedByName", "createdByName", "byName", "revisionCount", "studentCount",
}
FIREBASE_STORAGE_URL = re.compile(r"https://firebasestorage\.googleapis\.com/v0/b/[^/]+/o/([^?]+)", re.I)


class Report:
    def __init__(self) -> None:
        self.fs: dict[str, int] = {}
        self.pg: dict[str, int] = {}
        self.uid_fail: list[str] = []
        self.mileage: list[dict[str, Any]] = []
        self.unmapped: dict[str, int] = {}
        self.unmapped_keys: dict[str, list[str]] = {}
        self.diffs: list[str] = []
        self.errors: list[str] = []
        self.decision3: dict[str, str] = {}
        self.unknown_fields: dict[str, list[str]] = {}

    def fs_add(self, path: str, n: int) -> None:
        self.fs[path] = self.fs.get(path, 0) + n


def _init_firebase():
    cred_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(ROOT.parents[1] / "secrets" / "firebase-adminsdk.json"),
    )
    project = os.environ.get("FIREBASE_PROJECT_ID", "skn34-3rd-2team")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred_path), {"projectId": project})
    return firestore.client()


def connect_database():
    """Connect to an existing Django-migrated database without creating or dropping schema."""
    if os.environ.get("DB_HOST"):
        missing = [key for key in ("DB_NAME", "DB_USER", "DB_PASSWORD") if not os.environ.get(key)]
        if missing:
            raise RuntimeError(f"DB_HOST is set, but these settings are missing: {', '.join(missing)}")
        return psycopg.connect(
            host=os.environ["DB_HOST"],
            port=os.environ.get("DB_PORT", "5432"),
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            sslmode=os.environ.get("DB_SSLMODE", "require"),
        )
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Set DATABASE_URL or the DB_HOST/DB_NAME/DB_USER/DB_PASSWORD variables")
    return psycopg.connect(url)


def assert_schema_ready(conn) -> None:
    required = (
        "django_migrations",
        "cohorts",
        "users",
        "submission_tasks",
        "record_submission_files",
        "skills",
        "user_job_preferences",
    )
    missing: list[str] = []
    with conn.cursor() as cur:
        for table in required:
            cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
            if cur.fetchone()[0] is None:
                missing.append(table)
    if missing:
        raise RuntimeError(
            "Django schema is not ready. Run `python manage.py migrate` first. "
            f"Missing tables: {', '.join(missing)}"
        )


def ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    to_dt = getattr(value, "to_datetime", None)
    if callable(to_dt):
        dt = to_dt()
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    dt = ts(value)
    if dt:
        return dt.date()
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def as_time(value: Any) -> time | None:
    if value is None or value == "":
        return None
    if isinstance(value, time):
        return value
    text = str(value).strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def blank(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def storage_key(value: Any) -> str | None:
    text = blank(value)
    if not text:
        return None
    match = FIREBASE_STORAGE_URL.search(text)
    if match:
        return unquote(match.group(1)).lstrip("/")
    if text.startswith("gs://"):
        parts = text.split("/", 3)
        return parts[3].lstrip("/") if len(parts) == 4 else None
    if "://" not in text:
        return text.lstrip("/")
    return None


def at_day(day: date, value: Any) -> datetime | None:
    parsed = as_time(value)
    if not parsed:
        return None
    return datetime.combine(day, parsed, tzinfo=ZoneInfo("Asia/Seoul"))


def resume_content(content: Any, sections: Any) -> tuple[dict[str, Any], list[str]]:
    merged = dict(content) if isinstance(content, dict) else {}
    conflicts: list[str] = []
    if isinstance(sections, dict):
        if "section_status" in merged and merged["section_status"] != sections:
            conflicts.append("section_status")
        else:
            merged["section_status"] = sections
    return merged, conflicts


def arr(value: Any) -> list:
    if not value:
        return []
    if isinstance(value, list):
        return value
    return list(value)


def js(value: Any) -> Jsonb:
    return Jsonb(value if value is not None else {})


def dump(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): dump(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [dump(v) for v in value]
    to_dt = getattr(value, "to_datetime", None)
    if callable(to_dt):
        return to_dt().isoformat()
    return str(value)


def stream(col) -> list[DocumentSnapshot]:
    return list(col.stream())


class SavingCursor:
    def __init__(self, cur, report: Report) -> None:
        self._cur = cur
        self._report = report

    def execute(self, sql: str, params: tuple = ()) -> Any:
        head = sql.strip().split()[0].upper()
        if head in {"SELECT", "SAVEPOINT", "RELEASE", "ROLLBACK"}:
            return self._cur.execute(sql, params)
        self._cur.execute("SAVEPOINT sp_w")
        try:
            result = self._cur.execute(sql, params)
            self._cur.execute("RELEASE SAVEPOINT sp_w")
            return result
        except Exception as exc:  # noqa: BLE001
            self._cur.execute("ROLLBACK TO SAVEPOINT sp_w")
            self._report.errors.append(f"{sql.splitlines()[0][:90]}: {exc}")
            return None

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()


class Etl:
    def __init__(self, db, conn, report: Report) -> None:
        self.db = db
        self.conn = conn
        self.r = report
        self.users: dict[str, int] = {}
        self.cohorts: dict[str, int] = {}
        self.rooms: dict[tuple[str, str], int] = {}
        self.cells: dict[tuple[int, str], int] = {}
        self.sheets: dict[str, int] = {}
        self.sched_notices: dict[str, int] = {}
        self.popups: dict[str, int] = {}
        self.products: dict[str, int] = {}
        self.assessments: dict[str, int] = {}
        self.questions: dict[str, int] = {}
        self.ai_logs: dict[str, int] = {}
        self.resumes: dict[str, int] = {}
        self.feedback: dict[str, int] = {}
        self.sources: dict[str, int] = {}
        self.yt: dict[tuple[str, str], int] = {}
        raw = conn.cursor()
        self._raw = raw
        self.cur = SavingCursor(raw, report)

    def uid(self, firebase_uid: str | None) -> int | None:
        if not firebase_uid:
            return None
        found = self.users.get(firebase_uid)
        if found is None:
            self.r.uid_fail.append(firebase_uid)
        return found

    def insert(self, sql: str, params: tuple, returning: bool = True) -> int | None:
        self._raw.execute("SAVEPOINT sp")
        try:
            self._raw.execute(sql, params)
            row = self._raw.fetchone() if returning else None
            self._raw.execute("RELEASE SAVEPOINT sp")
            return row[0] if row else None
        except Exception as exc:  # noqa: BLE001
            self._raw.execute("ROLLBACK TO SAVEPOINT sp")
            self.r.errors.append(f"{sql.splitlines()[0][:90]}: {exc}")
            return None

    def count(self, table: str) -> int:
        self._raw.execute(f"SELECT COUNT(*) FROM {table}")
        return int(self._raw.fetchone()[0])

    def migrate(self) -> None:
        self._cohorts_users()
        self._intakes_todos_cache()
        self._class_ops()
        self._seating()
        self._comms()
        self._records()
        self._ai_logs()
        self._assessments()
        self._mileage()
        self._resumes()
        self._study()
        self._ai_ops()
        self._unmapped()
        self.conn.commit()
        self._pg_counts()
        self._mileage_check()

    def _cohorts_users(self) -> None:
        docs = stream(self.db.collection("cohorts"))
        self.r.fs_add("cohorts", len(docs))
        for doc in docs:
            d = doc.to_dict() or {}
            status = COHORT_STATUS.get(str(d.get("status") or ""), str(d.get("status") or "active"))
            if d.get("status") and d.get("status") not in ("planned", "active", "closed"):
                self.r.diffs.append(f"cohorts.status {d.get('status')} → {status} ({doc.id})")
            cid = self.insert(
                """INSERT INTO cohorts (code, name, description, term_number, classroom_name, status, is_active, start_date, end_date, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (
                    doc.id, d.get("name") or doc.id, d.get("description"),
                    d.get("termNumber"), d.get("classroomName"), status,
                    bool(d.get("isActive", True)), as_date(d.get("startDate")),
                    as_date(d.get("endDate")), ts(d.get("createdAt")),
                ),
            )
            self.cohorts[doc.id] = cid
        docs = stream(self.db.collection("users"))
        self.r.fs_add("users", len(docs))
        for doc in docs:
            d = doc.to_dict() or {}
            extra = [k for k in d if k not in {
                "email", "personalEmail", "displayName", "role", "cohortId", "cohortName",
                "seatNumber", "isActive", "mustChangePassword", "motto", "skills",
                "socialLinks", "jobPreferences", "birthDate", "photoUrl", "photoStoragePath",
                "mileageBalance", "createdAt", "updatedAt", "lastLoginAt",
            }]
            if extra:
                self.r.unknown_fields.setdefault("users", [])
                for k in extra:
                    if k not in self.r.unknown_fields["users"]:
                        self.r.unknown_fields["users"].append(k)
            uid = self.insert(
                """INSERT INTO users (firebase_uid, email, password, personal_email, display_name, role, cohort_id, seat_number, is_active, must_change_password, motto, social_links, birth_date, photo_storage_key, mileage_balance, last_login, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (
                    doc.id, blank(d.get("email")), make_password(None), blank(d.get("personalEmail")),
                    d.get("displayName") or "", d.get("role") or "student",
                    self.cohorts.get(d.get("cohortId") or ""),
                    d.get("seatNumber"), bool(d.get("isActive", True)),
                    True, d.get("motto"), js(dump(d.get("socialLinks") or {})),
                    as_date(d.get("birthDate")),
                    storage_key(d.get("photoStoragePath") or d.get("photoUrl")),
                    int(d.get("mileageBalance") or 0), ts(d.get("lastLoginAt")),
                    ts(d.get("createdAt")), ts(d.get("updatedAt")),
                ),
            )
            self.users[doc.id] = uid
            for raw_skill in arr(d.get("skills")):
                name = " ".join(str(raw_skill).split()).casefold()
                if not name:
                    continue
                skill_id = self.insert(
                    """INSERT INTO skills (canonical_name, created_at) VALUES (%s, now())
                       ON CONFLICT (canonical_name) DO UPDATE SET canonical_name=EXCLUDED.canonical_name
                       RETURNING id""",
                    (name,),
                )
                if skill_id:
                    self.cur.execute(
                        """INSERT INTO user_skills (user_id, skill_id, source, updated_at)
                           VALUES (%s,%s,'legacy_profile',now()) ON CONFLICT (user_id, skill_id) DO NOTHING""",
                        (uid, skill_id),
                    )
            self.cur.execute(
                """INSERT INTO user_job_preferences (user_id, preferences, updated_at)
                   VALUES (%s,%s,now()) ON CONFLICT (user_id) DO UPDATE
                   SET preferences=EXCLUDED.preferences, updated_at=EXCLUDED.updated_at""",
                (uid, js(dump(d.get("jobPreferences") or {}))),
            )

    def _intakes_todos_cache(self) -> None:
        docs = stream(self.db.collection("studentIntakes"))
        self.r.fs_add("studentIntakes", len(docs))
        for doc in docs:
            d = doc.to_dict() or {}
            intake = d.get("intake") if isinstance(d.get("intake"), dict) else d
            user_id = self.uid(doc.id)
            if user_id is None:
                continue
            initial_password = d.get("initialPassword") or intake.get("initialPassword")
            if initial_password and not d.get("passwordChanged"):
                self.cur.execute(
                    "UPDATE users SET password=%s, must_change_password=TRUE WHERE id=%s",
                    (make_password(str(initial_password)), user_id),
                )
            self.cur.execute(
                """INSERT INTO student_intakes (user_id, education_major, current_status, weekly_study_hours, programming_level, collaboration_tools, ai_llm_experience, motivation, desired_role, post_completion_goal, awards, project_links, team_role, self_learning_style, slump_overcome_experience, is_active, created_by, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (user_id) DO NOTHING""",
                (
                    user_id, intake.get("educationMajor") or "", intake.get("currentStatus") or "",
                    intake.get("weeklyStudyHours") or "", intake.get("programmingLevel") or "",
                    intake.get("collaborationTools") or "", intake.get("aiLlmExperience") or "",
                    intake.get("motivation") or "", intake.get("desiredRole") or "",
                    intake.get("postCompletionGoal") or "", intake.get("awards") or "",
                    intake.get("projectLinks") or "", intake.get("teamRole") or "",
                    intake.get("selfLearningStyle") or "", intake.get("slumpOvercomeExperience") or "",
                    bool(d.get("isActive", True)), self.uid(d.get("createdBy")) if d.get("createdBy") else None,
                    ts(d.get("createdAt")),
                ),
            )
        todos = 0
        for user in stream(self.db.collection("users")):
            for doc in stream(user.reference.collection("todos")):
                todos += 1
                d = doc.to_dict() or {}
                self.cur.execute(
                    """INSERT INTO todos (legacy_id, user_id, title, is_completed, created_at) VALUES (%s,%s,%s,%s,%s)""",
                    (f"{user.id}/{doc.id}", self.users[user.id], d.get("title") or "", bool(d.get("isCompleted", False)), ts(d.get("createdAt"))),
                )
        self.r.fs_add("users/{uid}/todos", todos)
        cache = stream(self.db.collection("systemCache"))
        self.r.fs_add("systemCache", len(cache))
        for doc in cache:
            d = doc.to_dict() or {}
            self.cur.execute(
                "INSERT INTO system_cache (key, data, synced_at) VALUES (%s,%s,%s)",
                (doc.id, js(dump(d)), ts(d.get("syncedAt") or d.get("updatedAt"))),
            )

    def _each_cohort(self):
        for code, cid in self.cohorts.items():
            yield code, cid, self.db.collection("cohorts").document(code)

    def _class_ops(self) -> None:
        for code, cid, ref in self._each_cohort():
            docs = stream(ref.collection("schedules"))
            self.r.fs_add("cohorts/{c}/schedules", len(docs))
            for doc in docs:
                d = doc.to_dict() or {}
                self.cur.execute(
                    """INSERT INTO schedules (legacy_id, cohort_id, date_key, sessions, current_session_index)
                       VALUES (%s,%s,%s,%s,%s) ON CONFLICT (cohort_id, date_key) DO NOTHING""",
                    (f"{code}/{doc.id}", cid, as_date(d.get("dateKey") or doc.id), js(dump(d.get("sessions") or [])), d.get("currentSessionIndex")),
                )
            meta = ref.collection("curriculum").document("meta").get()
            if meta.exists:
                self.r.fs_add("…/curriculum/meta", 1)
                d = meta.to_dict() or {}
                self.cur.execute(
                    """INSERT INTO curriculum_pdfs (cohort_id, storage_key, original_filename, published, updated_by, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (cohort_id) DO NOTHING""",
                    (cid, storage_key(d.get("fullPdfUrl") or d.get("url")), d.get("fullPdfFileName") or d.get("fileName"),
                     bool(d.get("published", False)), self.uid(d.get("updatedBy")), ts(d.get("updatedAt"))),
                )
            else:
                self.r.fs_add("…/curriculum/meta", 0)
            sheets = stream(ref.collection("curriculumSheets"))
            self.r.fs_add("…/curriculumSheets", len(sheets))
            for doc in sheets:
                d = doc.to_dict() or {}
                sid = self.insert(
                    """INSERT INTO curriculum_sheets (legacy_id, cohort_id, title, file_name, storage_key, source, uploaded_by, uploaded_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                     (doc.id, cid, d.get("title"), d.get("fileName"), storage_key(d.get("storagePath")), d.get("source"),
                     self.uid(d.get("uploadedBy")), ts(d.get("uploadedAt"))),
                )
                self.sheets[doc.id] = sid
                for i, row in enumerate(arr(d.get("rows"))):
                    if not isinstance(row, dict):
                        continue
                    self.cur.execute(
                        """INSERT INTO curriculum_rows (sheet_id, day_index, date_label, subject, topic, detail, "order")
                           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        (sid, row.get("dayIndex", i), row.get("dateLabel"), row.get("subject"), row.get("topic"), row.get("detail"), row.get("order", i)),
                    )
            mats = stream(ref.collection("materials"))
            self.r.fs_add("…/materials", len(mats))
            for doc in mats:
                d = doc.to_dict() or {}
                self.cur.execute(
                    """INSERT INTO materials (legacy_id, cohort_id, title, storage_key, file_name, description, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (doc.id, cid, d.get("title"), storage_key(d.get("fileUrl") or d.get("url")), d.get("fileName"), d.get("description"), ts(d.get("createdAt"))),
                )
            att = stream(ref.collection("attendances"))
            self.r.fs_add("…/attendances", len(att))
            grouped: dict[tuple[str, str], list] = defaultdict(list)
            for doc in att:
                d = doc.to_dict() or {}
                grouped[(str(d.get("userId") or ""), str(d.get("dateKey") or ""))].append((doc, d))
            for (uid, date_key), items in grouped.items():
                user_id = self.uid(uid)
                day = as_date(date_key)
                if user_id is None or day is None:
                    continue
                merged = {}
                for _, d in items:
                    merged.update(d)
                status = merged.get("status")
                if not status and merged.get("type") == "checkIn":
                    status = "present"
                self.cur.execute(
                    """INSERT INTO attendances (legacy_id, cohort_id, user_id, attendance_date, check_in_at, check_out_at, status, data_source, created_at, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (user_id, attendance_date) DO NOTHING""",
                    (items[0][0].id, cid, user_id, day, at_day(day, merged.get("checkInTime")),
                     at_day(day, merged.get("checkOutTime")), status, merged.get("statusSource"),
                     ts(merged.get("timestamp")) or datetime.now(timezone.utc),
                     ts(merged.get("timestamp")) or datetime.now(timezone.utc)),
                )
                issue_type = merged.get("formAttendanceType") or merged.get("officialLeaveType")
                if issue_type:
                    self.cur.execute(
                        """INSERT INTO attendance_issue_reports
                           (user_id, cohort_id, attendance_date, issue_type, details, status, created_at, updated_at)
                           VALUES (%s,%s,%s,%s,%s,'submitted',%s,%s)""",
                        (user_id, cid, day, issue_type, js({
                            "officialLeaveUsed": merged.get("officialLeaveUsed"),
                            "officialLeaveOther": merged.get("officialLeaveOther"),
                        }), ts(merged.get("timestamp")) or datetime.now(timezone.utc),
                         ts(merged.get("timestamp")) or datetime.now(timezone.utc)),
                    )
            rolls = stream(ref.collection("rollCalls"))
            self.r.fs_add("…/rollCalls", len(rolls))
            for doc in rolls:
                d = doc.to_dict() or {}
                date_key = as_date(d.get("dateKey"))
                period = d.get("periodId")
                if not date_key or not period:
                    m = re.match(r"(\d{4}-\d{2}-\d{2})_p(.+)", doc.id)
                    if m:
                        date_key = as_date(m.group(1))
                        period = period or m.group(2)
                seen = set()
                for uid in arr(d.get("confirmedUserIds")):
                    user_id = self.uid(str(uid))
                    if user_id and user_id not in seen:
                        self.cur.execute(
                            """INSERT INTO seat_presences
                               (cohort_id,user_id,presence_date,period,state,updated_by,updated_at)
                               VALUES (%s,%s,%s,%s,'confirmed',%s,%s) ON CONFLICT DO NOTHING""",
                            (cid, user_id, date_key, period or '', self.uid(d.get("updatedBy")), ts(d.get("updatedAt"))),
                        )
                        seen.add(user_id)
                for uid in arr(d.get("heldUserIds")):
                    user_id = self.uid(str(uid))
                    if user_id and user_id not in seen:
                        self.cur.execute(
                            """INSERT INTO seat_presences
                               (cohort_id,user_id,presence_date,period,state,updated_by,updated_at)
                               VALUES (%s,%s,%s,%s,'held',%s,%s) ON CONFLICT DO NOTHING""",
                            (cid, user_id, date_key, period or '', self.uid(d.get("updatedBy")), ts(d.get("updatedAt"))),
                        )
                        seen.add(user_id)

    def _seating(self) -> None:
        for code, cid, ref in self._each_cohort():
            rooms = stream(ref.collection("seatingRooms"))
            self.r.fs_add("…/seatingRooms", len(rooms))
            assigns = stream(ref.collection("seatingAssignments"))
            self.r.fs_add("…/seatingAssignments", len(assigns))
            meta = ref.collection("seatingMeta").document("default").get()
            self.r.fs_add("…/seatingMeta/default", 1 if meta.exists else 0)
            published_id = (meta.to_dict() or {}).get("publishedRoomId") if meta.exists else None
            room_docs = {doc.id: (doc.to_dict() or {}) for doc in rooms}
            assignment_docs = {doc.id: (doc.to_dict() or {}) for doc in assigns}
            selected_id = published_id if published_id in room_docs else next(iter(room_docs), None)
            selected = room_docs.get(selected_id, {})
            layout = selected.get("layout") if isinstance(selected.get("layout"), dict) else selected
            assignment = assignment_docs.get(selected_id, {})
            legacy = stream(ref.collection("seating"))
            self.r.fs_add("…/seating/{layout,assignment}", len(legacy))
            if not selected_id and legacy:
                layout_doc = ref.collection("seating").document("layout").get()
                assign_doc = ref.collection("seating").document("assignment").get()
                layout = (layout_doc.to_dict() or {}) if layout_doc.exists else {}
                assignment = (assign_doc.to_dict() or {}) if assign_doc.exists else {}
                selected_id = f"{code}/legacy"
            if selected_id:
                payload = dict(dump(layout)) if isinstance(layout, dict) else {}
                payload["sourceRoomId"] = selected_id
                payload["assignments"] = dump(assignment.get("assignments") or {})
                self.cur.execute(
                    """INSERT INTO cohort_seating
                       (cohort_id,room_number,layout,published,updated_by,updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (cohort_id) DO UPDATE SET
                         room_number=EXCLUDED.room_number, layout=EXCLUDED.layout,
                         published=EXCLUDED.published, updated_by=EXCLUDED.updated_by,
                         updated_at=EXCLUDED.updated_at""",
                    (cid, payload.get("roomNumber"), js(payload), bool(published_id),
                     self.uid(assignment.get("updatedBy") or selected.get("updatedBy")),
                     ts(assignment.get("updatedAt") or selected.get("updatedAt")) or datetime.now(timezone.utc)),
                )
            teams = stream(ref.collection("projectTeams"))
            self.r.fs_add("…/projectTeams", len(teams))
            for doc in teams:
                d = doc.to_dict() or {}
                tid = self.insert(
                    """INSERT INTO project_teams (legacy_id, cohort_id, name, sort_order, color_index, updated_by, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (doc.id, cid, d.get("name"), d.get("sortOrder"), d.get("colorIndex"), self.uid(d.get("updatedBy")), ts(d.get("updatedAt"))),
                )
                for uid in arr(d.get("memberIds")):
                    user_id = self.uid(str(uid))
                    if user_id:
                        self.cur.execute("INSERT INTO project_team_members (team_id,user_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (tid, user_id))

    def _comms(self) -> None:
        posts_n = qna_n = 0
        for code, cid, ref in self._each_cohort():
            scheduled = stream(ref.collection("scheduledNotices"))
            self.r.fs_add("…/scheduledNotices", len(scheduled))
            for doc in scheduled:
                d = doc.to_dict() or {}
                sid = self.insert(
                    """INSERT INTO scheduled_notices (legacy_id, cohort_id, title, content, author_id, is_favorite, repeat_type, publish_time, publish_at, weekday, is_active, last_published_at, next_publish_at, created_at, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (doc.id, cid, d.get("title"), d.get("content"), self.uid(d.get("authorId")),
                     bool(d.get("isFavorite", False)), d.get("repeatType"), as_time(d.get("publishTime")),
                     ts(d.get("publishAt")), d.get("weekday"), bool(d.get("isActive", True)),
                     ts(d.get("lastPublishedAt")), ts(d.get("nextPublishAt")), ts(d.get("createdAt")), ts(d.get("updatedAt"))),
                )
                self.sched_notices[doc.id] = sid
            notices = stream(ref.collection("notices"))
            self.r.fs_add("…/notices", len(notices))
            for doc in notices:
                d = doc.to_dict() or {}
                indexes = d.get("_vectorIndexes")
                chunk = len(indexes) if isinstance(indexes, list) else int(d.get("vectorChunkCount") or 0)
                author_name = d.get("authorName") if d.get("source") == "discord" else None
                self.cur.execute(
                    """INSERT INTO notices (legacy_id, cohort_id, title, content, author_id, author_name, is_favorite, priority, source, channel_label, discord_message_id, discord_channel_id, discord_channel_type, scheduled_notice_id, image_storage_key, vector_chunk_count, created_at, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (doc.id, cid, d.get("title"), d.get("content"), self.uid(d.get("authorId")), author_name,
                     bool(d.get("isFavorite") or d.get("isPinned")), int(d.get("priority") or 0), d.get("source") or "app",
                     d.get("channelLabel"), blank(d.get("discordMessageId")), d.get("discordChannelId"), d.get("discordChannelType"),
                     self.sched_notices.get(d.get("scheduledNoticeId") or ""), storage_key(d.get("imageUrl")), chunk,
                     ts(d.get("createdAt")), ts(d.get("updatedAt"))),
                )
            vm = stream(ref.collection("vectorMetadata"))
            self.r.fs_add("…/vectorMetadata/notices", len(vm))
            pops = stream(ref.collection("alertPopups"))
            self.r.fs_add("…/alertPopups", len(pops))
            for doc in pops:
                d = doc.to_dict() or {}
                pid = self.insert(
                    """INSERT INTO alert_popups (legacy_id, cohort_id, title, content, author_id, is_active, sort_order, link_url, start_time, end_time, created_at, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (doc.id, cid, d.get("title"), d.get("content"), self.uid(d.get("authorId")),
                     bool(d.get("isActive", True)), d.get("sortOrder"), d.get("linkUrl"),
                     as_time(d.get("startTime")), as_time(d.get("endTime")), ts(d.get("createdAt")), ts(d.get("updatedAt"))),
                )
                self.popups[doc.id] = pid
            posts_n += len(stream(ref.collection("posts")))
            qna_n += len(stream(ref.collection("qna")))
        self.r.fs_add("…/posts", posts_n)
        self.r.fs_add("…/qna", qna_n)
        self.r.decision3["posts / post_comments"] = "생략 (0건)" if posts_n == 0 else "생성"
        self.r.decision3["qna_threads / qna_messages"] = "생략 (0건)" if qna_n == 0 else "생성"
        dismiss = 0
        for user in stream(self.db.collection("users")):
            for doc in stream(user.reference.collection("alertPopupDismissals")):
                dismiss += 1
                popup_id = self.popups.get(doc.id)
                user_id = self.users.get(user.id)
                if popup_id and user_id:
                    d = doc.to_dict() or {}
                    self.cur.execute(
                        "INSERT INTO alert_popup_dismissals (user_id,popup_id,date_key) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                        (user_id, popup_id, as_date(d.get("dateKey"))),
                    )
        self.r.fs_add("users/{uid}/alertPopupDismissals", dismiss)

    def _records(self) -> None:
        for code, cid, ref in self._each_cohort():
            assigns = stream(ref.collection("assignments"))
            self.r.fs_add("…/assignments", len(assigns))
            sub_n = sum(len(stream(doc.reference.collection("submissions"))) for doc in assigns)
            self.r.fs_add("…/assignments/{id}/submissions", sub_n)
            if assigns or sub_n:
                self.r.decision3["legacy assignments"] = f"초기 통합 제외 ({len(assigns)} tasks / {sub_n} responses)"
            recs = stream(ref.collection("submissions"))
            self.r.fs_add("…/submissions", len(recs))
            for doc in recs:
                d = doc.to_dict() or {}
                user_id = self.uid(d.get("userId"))
                if not user_id:
                    continue
                details = {
                    key: dump(d.get(source)) for key, source in (
                        ("cert_type", "certType"), ("start_at", "startAt"), ("end_at", "endAt"),
                        ("week_number", "weekNumber"), ("week_label", "weekLabel"), ("link", "link"),
                        ("quiz_score", "quizScore"), ("learning_date", "learningDate"),
                        ("learning_content", "learningContent"), ("is_team_study", "isTeamStudy"),
                    ) if d.get(source) is not None
                }
                submitted_at = ts(d.get("submittedAt")) or datetime.now(timezone.utc)
                record_id = self.insert(
                    """INSERT INTO record_submissions
                       (legacy_id,cohort_id,user_id,type,status,title,details,review_comment,reviewed_by,reviewed_at,submitted_at,created_at,updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (doc.id, cid, user_id, d.get("type") or "blog", d.get("status") or "pending", d.get("title"),
                     js(details), d.get("reviewComment"), self.uid(d.get("reviewedBy")), ts(d.get("reviewedAt")),
                     submitted_at, ts(d.get("createdAt")) or submitted_at, ts(d.get("updatedAt")) or submitted_at),
                )
                for file_value in arr(d.get("fileUrls")):
                    key = storage_key(file_value)
                    if key and record_id:
                        self.cur.execute(
                            """INSERT INTO record_submission_files
                               (submission_id,storage_key,original_filename,uploaded_at)
                               VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                            (record_id, key, key.rsplit('/', 1)[-1], submitted_at),
                        )
            wtasks = stream(ref.collection("weeklyTasks"))
            self.r.fs_add("…/weeklyTasks", len(wtasks))
            up = stream(ref.collection("userProgress"))
            self.r.fs_add("…/userProgress", len(up))
            forms = stream(ref.collection("formTasks"))
            self.r.fs_add("…/formTasks", len(forms))
            resp_n = 0
            for doc in forms:
                d = doc.to_dict() or {}
                tid = self.insert(
                    """INSERT INTO submission_tasks
                       (legacy_id,title,description,submission_type,external_url,guide_url,due_at,published,created_at,updated_at)
                       VALUES (%s,%s,%s,'external_form',%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (doc.id, d.get("title"), d.get("description"), d.get("formUrl"), d.get("notionGuideUrl"),
                      ts(d.get("dueAt")), bool(d.get("published", True)), ts(d.get("createdAt")), ts(d.get("updatedAt"))),
                )
                self.cur.execute(
                    """INSERT INTO submission_task_cohorts (task_id,cohort_id)
                       VALUES (%s,%s) ON CONFLICT DO NOTHING""",
                    (tid, cid),
                )
                for resp in stream(doc.reference.collection("responses")):
                    resp_n += 1
                    rd = resp.to_dict() or {}
                    user_id = self.uid(resp.id if not rd.get("userId") else rd.get("userId"))
                    if user_id:
                        self.cur.execute(
                            """INSERT INTO submission_responses
                               (task_id,user_id,source,external_response_id,response,submitted_at)
                               VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                            (tid, user_id, rd.get("source"), blank(rd.get("googleResponseId")),
                             js(dump(rd.get("response") or {})), ts(rd.get("submittedAt"))),
                        )
            self.r.fs_add("…/formTasks/{id}/responses", resp_n)

    def _ai_logs(self) -> None:
        docs = stream(self.db.collection("aiGenerationLogs"))
        self.r.fs_add("aiGenerationLogs", len(docs))
        detail_keys = {
            "sheetId", "dayFrom", "dayTo", "mcCount", "saCount", "generatedCount", "rowCount",
            "drafts", "reasoningEffort", "mode", "intent", "topK", "jobCount", "appliedCount",
            "requestIdHash", "reviewMode", "route", "namespaces", "studentScopes", "blocked",
            "retrievalMs", "llmMs",
        }
        for doc in docs:
            d = doc.to_dict() or {}
            details = {k: dump(d.get(k)) for k in detail_keys if k in d}
            lid = self.insert(
                """INSERT INTO ai_generation_logs (legacy_id, type, cohort_id, created_by, prompt_version, model, status, error_message, latency_ms, token_in, token_out, details, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (doc.id, d.get("type"), self.cohorts.get(d.get("cohortId") or ""), self.uid(d.get("createdBy")),
                 d.get("promptVersion"), d.get("model"), d.get("status"), d.get("errorMessage"),
                 d.get("latencyMs"), d.get("tokenIn"), d.get("tokenOut"), js(details), ts(d.get("createdAt"))),
            )
            self.ai_logs[doc.id] = lid

    def _assessments(self) -> None:
        for code, cid, ref in self._each_cohort():
            items = stream(ref.collection("assessments"))
            self.r.fs_add("…/assessments", len(items))
            qn = 0
            for doc in items:
                d = doc.to_dict() or {}
                src = d.get("curriculumSource") or d.get("notionSource") or {}
                sheet_id = self.sheets.get(src.get("sheetId") or src.get("moduleId") or "")
                aid = self.insert(
                    """INSERT INTO assessments (legacy_id, cohort_id, title, tags, max_score, start_at, end_at, thumbnail_storage_key, published, created_by, created_at, updated_at, curriculum_sheet_id, day_from, day_to, subject_filter)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (doc.id, cid, d.get("title"), js(arr(d.get("tags"))), d.get("maxScore"), ts(d.get("startAt")), ts(d.get("endAt")),
                     storage_key(d.get("thumbnailPath") or d.get("thumbnailUrl")), bool(d.get("published", False)), self.uid(d.get("createdBy")),
                     ts(d.get("createdAt")), ts(d.get("updatedAt")), sheet_id, src.get("dayFrom") or src.get("snFrom"),
                     src.get("dayTo") or src.get("snTo"), src.get("subjectFilter") or src.get("moduleName")),
                )
                self.assessments[doc.id] = aid
                for q in stream(doc.reference.collection("questions")):
                    qn += 1
                    qd = q.to_dict() or {}
                    qid = self.insert(
                        """INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points, choices, correct_index, accepted_answers, explanation, origin, ai_log_id, ai_draft_id, prompt_version, source_day, source_topic)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (q.id, aid, qd.get("order"), qd.get("type"), qd.get("prompt"), qd.get("points"),
                         js(arr(qd.get("choices"))), qd.get("correctIndex"), js(arr(qd.get("acceptedAnswers"))),
                         qd.get("explanation"), qd.get("origin") or "manual", self.ai_logs.get(qd.get("aiLogId") or ""),
                         qd.get("aiDraftId"), qd.get("promptVersion"), qd.get("sourceDay"), qd.get("sourceTopic")),
                    )
                    self.questions[q.id] = qid
            self.r.fs_add("…/assessments/{id}/questions", qn)
            subs = stream(ref.collection("assessmentSubmissions"))
            self.r.fs_add("…/assessmentSubmissions", len(subs))
            for doc in subs:
                d = doc.to_dict() or {}
                aid = self.assessments.get(d.get("assessmentId") or "")
                if not aid and "_" in doc.id:
                    aid = self.assessments.get(doc.id.rsplit("_", 1)[0])
                user_id = self.uid(d.get("userId"))
                if not aid or not user_id:
                    continue
                sid = self.insert(
                    """INSERT INTO assessment_submissions (legacy_id, assessment_id, user_id, auto_total_score, total_score, status, submitted_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (doc.id, aid, user_id, d.get("autoTotalScore"), d.get("totalScore"), d.get("status"), ts(d.get("submittedAt"))),
                )
                answers = d.get("answers") or {}
                if isinstance(answers, dict):
                    for qid, ans in answers.items():
                        if not isinstance(ans, dict):
                            ans = {"value": ans}
                        pg_q = self.questions.get(qid)
                        if not pg_q:
                            continue
                        self.cur.execute(
                            """INSERT INTO assessment_answers
                               (submission_id,question_id,value,auto_score,final_score,is_correct)
                               VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                            (sid, pg_q, js(dump(ans.get("value"))), ans.get("autoScore"), ans.get("finalScore"), ans.get("isCorrect")),
                        )
                for adj in arr(d.get("scoreAdjustments")):
                    if not isinstance(adj, dict):
                        continue
                    self.cur.execute(
                        """INSERT INTO assessment_score_adjustments (submission_id, question_id, previous, next, adjusted_by, adjusted_at, note)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        (sid, self.questions.get(adj.get("questionId") or ""), adj.get("previous"), adj.get("next"),
                         self.uid(adj.get("adjustedBy") or adj.get("by")), ts(adj.get("adjustedAt") or adj.get("at")), adj.get("note")),
                    )

    def _mileage(self) -> None:
        for code, cid, ref in self._each_cohort():
            txs = stream(ref.collection("mileageTransactions"))
            self.r.fs_add("…/mileageTransactions", len(txs))
            for doc in txs:
                d = doc.to_dict() or {}
                user_id = self.uid(d.get("userId"))
                if not user_id:
                    continue
                self.cur.execute(
                    """INSERT INTO mileage_transactions (legacy_id, cohort_id, user_id, amount, reason, type, related_id, adjusted_by, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (doc.id, cid, user_id, int(d.get("amount") or 0), d.get("reason"), d.get("type"),
                     None if d.get("relatedId") is None else str(d.get("relatedId")), self.uid(d.get("adjustedBy")), ts(d.get("createdAt"))),
                )
            cfg = ref.collection("mileageSettings").document("config").get()
            settings_docs = stream(ref.collection("mileageSettings"))
            self.r.fs_add("…/mileageSettings/config", len(settings_docs))
            if cfg.exists:
                d = cfg.to_dict() or {}
                self.cur.execute(
                    """INSERT INTO mileage_settings
                       (cohort_id,category_limits,accrual_rules,updated_by,updated_at)
                       VALUES (%s,%s,%s,%s,%s) ON CONFLICT (cohort_id) DO NOTHING""",
                    (cid, js(d.get("categoryLimits") or {}), js(d.get("accrualRules") or {}), self.uid(d.get("updatedBy")), ts(d.get("updatedAt"))),
                )
            products = stream(ref.collection("mileageProducts"))
            self.r.fs_add("…/mileageProducts", len(products))
            for doc in products:
                d = doc.to_dict() or {}
                pid = self.insert(
                    """INSERT INTO mileage_products (legacy_id, cohort_id, name, description, image_url, category, pricing_type, fixed_price, is_active, sort_order, created_at, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (doc.id, cid, d.get("name"), d.get("description"), d.get("imageUrl"), d.get("category"),
                     d.get("pricingType"), d.get("fixedPrice"), bool(d.get("isActive", True)), d.get("sortOrder"),
                     ts(d.get("createdAt")), ts(d.get("updatedAt"))),
                )
                self.products[doc.id] = pid
            reqs = stream(ref.collection("purchaseRequests"))
            self.r.fs_add("…/purchaseRequests", len(reqs))
            for doc in reqs:
                d = doc.to_dict() or {}
                user_id = self.uid(d.get("userId"))
                if not user_id:
                    continue
                rid = self.insert(
                    """INSERT INTO purchase_requests (legacy_id, cohort_id, user_id, total_amount, status, student_note, manager_memo, manager_purchase_link, processed_by, processed_at, created_at, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (doc.id, cid, user_id, d.get("totalAmount"), d.get("status"), d.get("studentNote"), d.get("managerMemo"),
                     d.get("managerPurchaseLink"), self.uid(d.get("processedBy")), ts(d.get("processedAt")),
                     ts(d.get("createdAt")), ts(d.get("updatedAt"))),
                )
                for item in arr(d.get("items")):
                    if not isinstance(item, dict):
                        continue
                    self.cur.execute(
                        """INSERT INTO purchase_request_items (request_id, product_id, product_name, category, pricing_type, unit_price, quantity, purchase_link)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (rid, self.products.get(item.get("productId") or ""), item.get("productName"), item.get("category"),
                         item.get("pricingType"), item.get("unitPrice"), item.get("quantity"), item.get("purchaseLink")),
                    )
            carts = stream(ref.collection("mileageCart"))
            self.r.fs_add("…/mileageCart", len(carts))
            for doc in carts:
                d = doc.to_dict() or {}
                user_id = self.uid(doc.id)
                if not user_id:
                    continue
                for item in arr(d.get("items")):
                    if not isinstance(item, dict):
                        continue
                    pid = self.products.get(item.get("productId") or "")
                    if not pid:
                        continue
                    self.cur.execute(
                        """INSERT INTO mileage_cart_items
                           (user_id,product_id,quantity,unit_price,purchase_link,updated_at)
                           VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                        (user_id, pid, item.get("quantity") or 1, item.get("unitPrice"), item.get("purchaseLink"), ts(d.get("updatedAt"))),
                    )
            missions = stream(ref.collection("missionProgress"))
            self.r.fs_add("…/missionProgress", len(missions))
            for doc in missions:
                d = doc.to_dict() or {}
                user_id = self.uid(doc.id)
                if not user_id:
                    continue
                self.cur.execute(
                    """INSERT INTO mission_progress
                       (cohort_id,user_id,study_cert_count,study_cert_granted,quiz_pass_count,quiz_granted,
                        coding_pcce,coding_pccp,coding_pcsql,coding_granted,blog_weeks,blog_units_granted,
                        study_week_keys,study_granted,updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT DO NOTHING""",
                    (cid, user_id, int(d.get("studyCertCount") or 0), int(d.get("studyCertGranted") or 0),
                     int(d.get("quizPassCount") or 0), int(d.get("quizGranted") or 0),
                     bool(d.get("codingPcce")), bool(d.get("codingPccp")), bool(d.get("codingPcsql")),
                     int(d.get("codingGranted") or 0), js(arr(d.get("blogWeeks"))), js(arr(d.get("blogUnitsGranted"))),
                     js([str(x) for x in arr(d.get("studyWeekKeys"))]), bool(d.get("studyGranted")), ts(d.get("updatedAt"))),
                )

    def _resumes(self) -> None:
        fb_n = rev_n = 0
        tailored_n = 0
        for code, cid, ref in self._each_cohort():
            items = stream(ref.collection("resumes"))
            self.r.fs_add("…/resumes", len(items))
            pending_reads = []
            for doc in items:
                d = doc.to_dict() or {}
                user_id = self.uid(d.get("userId"))
                if not user_id:
                    continue
                merged_content, conflicts = resume_content(d.get("content"), d.get("sections"))
                if conflicts:
                    self.r.diffs.append(
                        f"resume {doc.id}: content/sections 충돌 키는 content 우선 ({', '.join(conflicts)})"
                    )
                rid = self.insert(
                    """INSERT INTO resumes
                       (legacy_id,cohort_id,user_id,title,status,content,is_base_resume,linked_job_id,revision_count,created_at,updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,%s,%s) RETURNING id""",
                    (doc.id, cid, user_id, d.get("title"), d.get("status"), js(dump(merged_content)),
                     bool(d.get("isBaseResume", False)), blank(d.get("linkedJobId")),
                     ts(d.get("createdAt")), ts(d.get("updatedAt"))),
                )
                self.resumes[doc.id] = rid
                pending_reads.append((rid, d, user_id))
                for fb in stream(doc.reference.collection("feedback")):
                    fb_n += 1
                    fd = fb.to_dict() or {}
                    fid = self.insert(
                        """INSERT INTO resume_feedback (legacy_id, resume_id, section_key, content, author_id, created_at)
                           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (fb.id, rid, fd.get("sectionKey") or fd.get("section"), fd.get("content"), self.uid(fd.get("authorId")), ts(fd.get("createdAt"))),
                    )
                    self.feedback[fb.id] = fid
                for revision_no, rev in enumerate(stream(doc.reference.collection("revisions")), start=1):
                    rev_n += 1
                    rd = rev.to_dict() or {}
                    revision_content, revision_conflicts = resume_content(rd.get("content"), rd.get("sections"))
                    if revision_conflicts:
                        self.r.diffs.append(
                            f"resume revision {rev.id}: content/sections 충돌 키는 content 우선 "
                            f"({', '.join(revision_conflicts)})"
                        )
                    self.cur.execute(
                        """INSERT INTO resume_revisions
                           (legacy_id,resume_id,revision_no,content,created_by_id,created_at)
                           VALUES (%s,%s,%s,%s,%s,%s)""",
                        (rev.id, rid, revision_no, js(dump(revision_content)),
                         self.uid(rd.get("createdBy") or d.get("userId")),
                         ts(rd.get("savedAt") or rd.get("createdAt")) or datetime.now(timezone.utc)),
                    )
                for child in doc.reference.collections():
                    if child.id in {"feedback", "revisions"}:
                        continue
                    n = len(stream(child))
                    self.r.unmapped[f"resumes/{doc.id}/{child.id}"] = self.r.unmapped.get(f"resumes/*/ {child.id}", 0)
                    key = f"resumes/*/{child.id}"
                    self.r.unmapped[key] = self.r.unmapped.get(key, 0) + n
                    if child.id == "tailoredResumes":
                        for tdoc in stream(child):
                            tailored_n += 1
                            td = tdoc.to_dict() or {}
                            tuid = self.uid(td.get("userId") or d.get("userId"))
                            if not tuid:
                                continue
                            tailored_content, tailored_conflicts = resume_content(td.get("content"), td.get("sections"))
                            if tailored_conflicts:
                                self.r.diffs.append(
                                    f"tailored resume {tdoc.id}: content/sections 충돌 키는 content 우선 "
                                    f"({', '.join(tailored_conflicts)})"
                                )
                            self.insert(
                                """INSERT INTO resumes
                                   (legacy_id,cohort_id,user_id,title,status,content,is_base_resume,base_resume_id,linked_job_id,revision_count,created_at,updated_at)
                                   VALUES (%s,%s,%s,%s,%s,%s,false,%s,%s,0,%s,%s) RETURNING id""",
                                (f"{doc.id}/tailored/{tdoc.id}", cid, tuid, td.get("title"), td.get("status"),
                                 js(dump(tailored_content)), rid,
                                 blank(td.get("linkedJobId")), ts(td.get("createdAt")), ts(td.get("updatedAt"))),
                            )
            for rid, d, user_id in pending_reads:
                for fb_id in arr(d.get("readFeedbackIds")):
                    fid = self.feedback.get(str(fb_id))
                    if fid:
                        self.cur.execute(
                            """INSERT INTO resume_feedback_reads (resume_id,user_id,feedback_id,read_at)
                               VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                            (rid, user_id, fid, datetime.now(timezone.utc)),
                        )
                for fb_id in arr(d.get("reviewerReadFeedbackIds")):
                    fid = self.feedback.get(str(fb_id))
                    if fid:
                        # reviewer ids unknown; keep student+reviewer in one table per user if we had reviewer uid. skip unknown.
                        pass
        self.r.fs_add("…/resumes/{id}/feedback", fb_n)
        self.r.fs_add("…/resumes/{id}/revisions", rev_n)
        if tailored_n:
            self.r.diffs.append(
                f"undocumented path tailoredResumes ({tailored_n} docs) flattened into resumes (ERD base_resume_id). aiReviews/aiApplications not loaded."
            )

    def _study(self) -> None:
        user_notes = 0
        for code, cid, ref in self._each_cohort():
            pkgs = stream(ref.collection("inflearnPackages"))
            self.r.fs_add("…/inflearnPackages", len(pkgs))
            for doc in pkgs:
                d = doc.to_dict() or {}
                self.cur.execute(
                    """INSERT INTO inflearn_packages (legacy_id, cohort_id, title, subject, type, summary, units, courses, is_published, sort_order, published_at, created_at, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (doc.id, cid, d.get("title"), d.get("subject"), d.get("type"), d.get("summary"),
                     js(dump(d.get("units") or [])), js(dump(d.get("courses") or [])), bool(d.get("isPublished") or d.get("published")),
                     d.get("sortOrder"), ts(d.get("publishedAt")), ts(d.get("createdAt")), ts(d.get("updatedAt"))),
                )
            recs = stream(ref.collection("youtubeRecommendations"))
            self.r.fs_add("…/youtubeRecommendations", len(recs))
            for doc in recs:
                d = doc.to_dict() or {}
                vid = d.get("videoId") or doc.id
                yid = self.insert(
                    """INSERT INTO youtube_recommendations (legacy_id, cohort_id, video_id, title, youtube_url, thumbnail_url, description, tags, is_published, sort_order, created_at, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (doc.id, cid, vid, d.get("title"), d.get("youtubeUrl") or d.get("url"), d.get("thumbnailUrl"),
                     d.get("description"), arr(d.get("tags")), bool(d.get("isPublished", False)), d.get("sortOrder"),
                     ts(d.get("createdAt")), ts(d.get("updatedAt"))),
                )
                self.yt[(code, vid)] = yid
            evs = stream(ref.collection("recommendationEvents"))
            self.r.fs_add("…/recommendationEvents", len(evs))
            for doc in evs:
                d = doc.to_dict() or {}
                self.cur.execute(
                    """INSERT INTO recommendation_events (legacy_id, cohort_id, user_id, recommendation_id, youtube_video_id, user_skills, matched_tags, action, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (doc.id, cid, self.uid(d.get("userId")), self.yt.get((code, str(d.get("youtubeVideoId") or d.get("videoId") or ""))),
                     d.get("youtubeVideoId") or d.get("videoId"), js(arr(d.get("userSkills"))), js(arr(d.get("matchedTags"))),
                     d.get("action"), ts(d.get("createdAt"))),
                )
            cache = stream(ref.collection("youtubeCurriculumCache"))
            self.r.fs_add("…/youtubeCurriculumCache", len(cache))
            srcs = stream(ref.collection("studySources"))
            self.r.fs_add("…/studySources", len(srcs))
            for doc in srcs:
                d = doc.to_dict() or {}
                sid = self.insert(
                    """INSERT INTO study_sources (legacy_id, cohort_id, title, repo_url, branch, allowed_prefixes, is_active, sort_order, created_at, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (doc.id, cid, d.get("title"), d.get("repoUrl") or d.get("url"), d.get("branch"),
                     arr(d.get("allowedPrefixes")), bool(d.get("isActive", True)), d.get("sortOrder"),
                     ts(d.get("createdAt")), ts(d.get("updatedAt"))),
                )
                self.sources[doc.id] = sid
            legacy_notes = stream(ref.collection("studyNotes"))
            self.r.fs_add("…/studyNotes", len(legacy_notes))
            kept = 0
            for doc in legacy_notes:
                d = doc.to_dict() or {}
                user_id = self.uid(d.get("userId"))
                if not user_id:
                    self.r.diffs.append(f"legacy studyNotes {doc.id} dropped (no userId)")
                    continue
                kept += 1
                self.cur.execute(
                    """INSERT INTO study_notes (legacy_id, user_id, source_id, status, scope_type, scope_value, scope_key, report_markdown, review_markdown, error_message, message, files, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (f"legacy/{doc.id}", user_id, self.sources.get(d.get("sourceId") or ""), d.get("status"),
                     d.get("scopeType"), js(dump(d.get("scopeValue"))) if d.get("scopeValue") is not None else None,
                     d.get("scopeKey"), d.get("reportMarkdown"), d.get("reviewMarkdown"), d.get("errorMessage"),
                     d.get("message"), js(dump(d.get("files") or [])), ts(d.get("createdAt"))),
                )
            self.r.decision3["레거시 studyNotes"] = f"study_notes 합침 {kept}건 / 원본 {len(legacy_notes)}건"
        for user in stream(self.db.collection("users")):
            for doc in stream(user.reference.collection("studyNotes")):
                user_notes += 1
                d = doc.to_dict() or {}
                self.cur.execute(
                    """INSERT INTO study_notes (legacy_id, user_id, source_id, status, scope_type, scope_value, scope_key, report_markdown, review_markdown, error_message, message, files, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (doc.id, self.users[user.id], self.sources.get(d.get("sourceId") or ""), d.get("status"),
                     d.get("scopeType"), js(dump(d.get("scopeValue"))) if d.get("scopeValue") is not None else None,
                     d.get("scopeKey"), d.get("reportMarkdown"), d.get("reviewMarkdown"), d.get("errorMessage"),
                     d.get("message"), js(dump(d.get("files") or [])), ts(d.get("createdAt"))),
                )
        self.r.fs_add("users/{uid}/studyNotes", user_notes)
        seating_legacy = self.r.fs.get("…/seating/{layout,assignment}", 0)
        self.r.decision3["레거시 seating"] = "cohort_seating.layout JSONB로 변환" if seating_legacy else "생략 (신규 seatingRooms 사용)"

    def _ai_ops(self) -> None:
        fbs = stream(self.db.collection("aiQuestionFeedback"))
        self.r.fs_add("aiQuestionFeedback", len(fbs))
        for doc in fbs:
            d = doc.to_dict() or {}
            self.cur.execute(
                """INSERT INTO ai_question_feedback (legacy_id, log_id, draft_id, cohort_id, outcome, type, prompt_version, assessment_id, question_id, source_day, source_topic, actor_id, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (doc.id, self.ai_logs.get(d.get("logId") or ""), d.get("draftId"), self.cohorts.get(d.get("cohortId") or ""),
                 d.get("outcome"), d.get("type"), d.get("promptVersion"), self.assessments.get(d.get("assessmentId") or ""),
                 self.questions.get(d.get("questionId") or ""), d.get("sourceDay"), d.get("sourceTopic"),
                 self.uid(d.get("actorId")), ts(d.get("createdAt")), ts(d.get("updatedAt"))),
            )
        runs = stream(self.db.collection("aiEvalRuns"))
        self.r.fs_add("aiEvalRuns", len(runs))
        for doc in runs:
            d = doc.to_dict() or {}
            self.cur.execute(
                """INSERT INTO ai_eval_runs (legacy_id, prompt_version, model, source, total_cases, passed, accuracy, avg_latency_ms, failed_ids, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (doc.id, d.get("promptVersion"), d.get("model"), d.get("source"), d.get("totalCases"), d.get("passed"),
                 d.get("accuracy"), d.get("avgLatencyMs"), js([str(x) for x in arr(d.get("failedIds"))]), ts(d.get("createdAt"))),
            )

    def _unmapped(self) -> None:
        profiles = stream(self.db.collection("jobRequirementProfiles"))
        self.r.unmapped["jobRequirementProfiles"] = len(profiles)
        if profiles:
            self.r.unmapped_keys["jobRequirementProfiles"] = sorted((profiles[0].to_dict() or {}).keys())
        self.r.diffs.append("jobRequirementProfiles / resumes/*/aiReviews / resumes/*/aiApplications 는 ERD 54경로에 없어 테이블을 만들지 않았다.")

    def _pg_counts(self) -> None:
        mapping = {
            "users": "users",
            "cohorts": "cohorts",
            "student_intakes": "studentIntakes",
            "todos": "users/{uid}/todos",
            "alert_popup_dismissals": "users/{uid}/alertPopupDismissals",
            "study_notes": "users/{uid}/studyNotes + legacy",
            "system_cache": "systemCache",
            "schedules": "cohorts/{c}/schedules",
            "curriculum_pdfs": "…/curriculum/meta",
            "curriculum_sheets": "…/curriculumSheets",
            "materials": "…/materials",
            "attendances": "…/attendances",
            "seat_presences": "…/rollCalls",
            "cohort_seating": "…/seatingRooms",
            "project_teams": "…/projectTeams",
            "notices": "…/notices",
            "scheduled_notices": "…/scheduledNotices",
            "alert_popups": "…/alertPopups",
            "record_submissions": "…/submissions",
            "record_submission_files": "…/submissions.fileUrls",
            "submission_tasks": "…/formTasks",
            "submission_responses": "…/formTasks/{id}/responses",
            "assessments": "…/assessments",
            "assessment_questions": "…/assessments/{id}/questions",
            "assessment_submissions": "…/assessmentSubmissions",
            "mileage_transactions": "…/mileageTransactions",
            "mileage_products": "…/mileageProducts",
            "purchase_requests": "…/purchaseRequests",
            "mileage_cart_items": "…/mileageCart",
            "mission_progress": "…/missionProgress",
            "resumes": "…/resumes",
            "resume_feedback": "…/resumes/{id}/feedback",
            "resume_revisions": "…/resumes/{id}/revisions",
            "inflearn_packages": "…/inflearnPackages",
            "youtube_recommendations": "…/youtubeRecommendations",
            "recommendation_events": "…/recommendationEvents",
            "study_sources": "…/studySources",
            "ai_generation_logs": "aiGenerationLogs",
            "ai_question_feedback": "aiQuestionFeedback",
            "ai_eval_runs": "aiEvalRuns",
        }
        for table in mapping:
            self.r.pg[table] = self.count(table)

    def _mileage_check(self) -> None:
        self._raw.execute(
            """SELECT u.firebase_uid, u.mileage_balance, COALESCE(SUM(t.amount),0)
               FROM users u LEFT JOIN mileage_transactions t ON t.user_id = u.id
               GROUP BY u.id HAVING u.mileage_balance IS DISTINCT FROM COALESCE(SUM(t.amount),0)"""
        )
        for uid, bal, total in self._raw.fetchall():
            self.r.mileage.append({"firebase_uid": uid, "mileage_balance": bal, "sum_amount": int(total)})


def write_report(r: Report) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Firestore → PostgreSQL 이전 리포트",
        "",
        "운영 Firestore는 읽기만 했다. jobs 스키마와 youtube_curriculum_cache 테이블은 만들지 않았다.",
        "",
        "## 결정 3",
    ]
    for k, v in r.decision3.items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## 경로별 건수", "", "| Firestore 경로 | FS | Postgres 테이블 | PG |", "| --- | ---: | --- | ---: |"]
    pairs = [
        ("users", "users"), ("cohorts", "cohorts"), ("studentIntakes", "student_intakes"),
        ("users/{uid}/todos", "todos"), ("users/{uid}/alertPopupDismissals", "alert_popup_dismissals"),
        ("…/attendances", "attendances"), ("…/rollCalls", "seat_presences"), ("…/notices", "notices"),
        ("…/resumes", "resumes"), ("…/resumes/{id}/feedback", "resume_feedback"),
        ("…/resumes/{id}/revisions", "resume_revisions"), ("…/submissions", "record_submissions"),
        ("…/assessmentSubmissions", "assessment_submissions"), ("…/assessments/{id}/questions", "assessment_questions"),
        ("aiGenerationLogs", "ai_generation_logs"), ("aiQuestionFeedback", "ai_question_feedback"),
        ("…/mileageTransactions", "mileage_transactions"), ("…/mileageProducts", "mileage_products"),
        ("…/projectTeams", "project_teams"), ("…/studySources", "study_sources"),
        ("…/formTasks", "submission_tasks"), ("…/seatingRooms", "cohort_seating"),
        ("systemCache", "system_cache"), ("aiEvalRuns", "ai_eval_runs"),
    ]
    for fs, table in pairs:
        lines.append(f"| `{fs}` | {r.fs.get(fs, 0)} | `{table}` | {r.pg.get(table, 0)} |")
    lines += ["", "## 전체 Firestore 인벤토리", ""]
    for path, n in sorted(r.fs.items()):
        lines.append(f"- `{path}`: {n}")
    lines += ["", "## firebase_uid 매핑 실패 (중복 제거)", ""]
    fails = sorted(set(r.uid_fail))
    lines.append(f"{len(fails)}건" if fails else "없음")
    for u in fails[:50]:
        lines.append(f"- `{u}`")
    lines += ["", "## mileage_balance vs SUM(amount)", ""]
    if not r.mileage:
        lines.append("전원 일치")
    else:
        lines.append("잔액을 수정하지 않았다.")
        for row in r.mileage:
            lines.append(f"- `{row['firebase_uid']}` balance={row['mileage_balance']} sum={row['sum_amount']}")
    lines += ["", "## 발견·미매핑 (테이블 생성 안 함)", ""]
    for k, n in sorted(r.unmapped.items()):
        keys = r.unmapped_keys.get(k, [])
        extra = f" keys={keys}" if keys else ""
        lines.append(f"- `{k}`: {n}{extra}")
    lines += ["", "## 문서와 코드 차이", ""]
    for d in r.diffs:
        lines.append(f"- {d}")
    if r.unknown_fields:
        lines.append("- users 문서의 추가 필드: " + ", ".join(r.unknown_fields.get("users", [])))
    lines += ["", "## ETL 오류", ""]
    if not r.errors:
        lines.append("없음")
    else:
        for e in r.errors[:100]:
            lines.append(f"- {e}")
    lines += [
        "",
        "## 다음에 사람이 해야 할 일",
        "",
        "1. Pinecone `notice` 네임스페이스 재적재 (벡터 ID `{기수코드}_n{notices.id}_{청크번호}`)",
        "2. youtubeCurriculumCache → Redis TTL",
        "3. Storage URL은 Firestore 값을 그대로 둠. S3 복사는 후속",
        "4. Django models.py / API, 챗봇 쿼리를 Postgres로 교체",
        "5. job_matching_bot SQLite → jobs 스키마",
        "6. 미매핑 컬렉션(jobRequirementProfiles, aiReviews, aiApplications) 스키마 결정",
        "7. Flutter/React가 Firestore를 보지 않게 repository를 API로 교체",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    db = _init_firebase()
    report = Report()
    with connect_database() as conn:
        assert_schema_ready(conn)
        etl = Etl(db, conn, report)
        etl.migrate()
    write_report(report)
    print(f"report: {REPORT}")
    print(f"pg users={report.pg.get('users')} fs users={report.fs.get('users')}")
    print(f"mileage mismatches={len(report.mileage)} uid_fail={len(set(report.uid_fail))} errors={len(report.errors)}")
    return 1 if report.errors or report.uid_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
