"""Named mutations. firestore.rules 권한 + 서버만 write 는 관리자."""

from __future__ import annotations

from datetime import date

from django.contrib.auth.hashers import make_password
from django.db import connection, transaction

from lms.permissions import can_access_cohort
from lms.practice_service import PRACTICE_OPS
from lms.services import schedule_notice_vector


def _one(cur):
    row = cur.fetchone()
    if not row:
        return None
    cols = [c[0] for c in cur.description]
    return dict(zip(cols, row))


def resolve_cohort(cur, cohort_key, user) -> int | None:
    if cohort_key is None or cohort_key == "":
        if user.get("cohort_id"):
            return user.get("cohort_id")
    else:
        cur.execute("SELECT id FROM cohorts WHERE code = %s", [str(cohort_key)])
        row = cur.fetchone()
        if row:
            return row[0]
        try:
            cur.execute("SELECT id FROM cohorts WHERE id = %s", [int(cohort_key)])
            row = cur.fetchone()
            if row:
                return row[0]
        except (TypeError, ValueError):
            pass
    if user.get("role") == "admin":
        cur.execute("SELECT id FROM cohorts ORDER BY id LIMIT 1")
        row = cur.fetchone()
        return row[0] if row else None
    return user.get("cohort_id")


def resolve_user(cur, firebase_uid: str) -> int | None:
    cur.execute("SELECT id FROM users WHERE firebase_uid = %s", [firebase_uid])
    row = cur.fetchone()
    return row[0] if row else None


def resolve_row(cur, table: str, public_id, extra_where: str = "", extra_args=()):
    args = [str(public_id), *extra_args]
    cur.execute(f"SELECT * FROM {table} WHERE legacy_id = %s {extra_where}", args)
    row = _one(cur)
    if row:
        return row
    try:
        cur.execute(f"SELECT * FROM {table} WHERE id = %s {extra_where}", [int(public_id), *extra_args])
        return _one(cur)
    except (TypeError, ValueError):
        return None


def _require_admin(user):
    if user.get("role") != "admin":
        raise PermissionError("admin only")


def _require_staff(user):
    if user.get("role") not in ("admin", "instructor"):
        raise PermissionError("staff only")


def dispatch(user: dict, op: str, payload: dict) -> dict:
    handler = OPS.get(op)
    if handler is None:
        raise ValueError(f"unknown op {op}")
    with transaction.atomic():
        with connection.cursor() as cur:
            return handler(cur, user, payload) or {"ok": True}


def op_update_profile(cur, user, p):
    uid = p.get("uid") or user["firebase_uid"]
    if user["role"] != "admin" and uid != user["firebase_uid"]:
        raise PermissionError("owner only")
    fields = []
    args = []
    mapping = {
        "motto": "motto",
        "socialLinks": "social_links",
        "birthDate": "birth_date",
        "personalEmail": "personal_email",
        "photoStoragePath": "photo_storage_key",
        "mustChangePassword": "must_change_password",
        "lastLoginAt": "last_login",
    }
    for src, col in mapping.items():
        if src in p:
            fields.append(f"{col} = %s")
            args.append(p[src])
    if "password" in p:
        fields.append("password = %s")
        args.append(make_password(str(p["password"])))
    target_user_id = resolve_user(cur, uid)
    if target_user_id is None:
        raise KeyError("user")
    if "skills" in p:
        cur.execute("DELETE FROM user_skills WHERE user_id = %s", [target_user_id])
        for raw_skill in p.get("skills") or []:
            name = " ".join(str(raw_skill).split()).casefold()
            if not name:
                continue
            cur.execute(
                """INSERT INTO skills (canonical_name,created_at) VALUES (%s,now())
                   ON CONFLICT (canonical_name) DO UPDATE SET canonical_name=EXCLUDED.canonical_name
                   RETURNING id""",
                [name],
            )
            skill_id = cur.fetchone()[0]
            cur.execute(
                """INSERT INTO user_skills (user_id,skill_id,source,updated_at)
                   VALUES (%s,%s,'profile',now()) ON CONFLICT DO NOTHING""",
                [target_user_id, skill_id],
            )
    if "jobPreferences" in p:
        import json
        cur.execute(
            """INSERT INTO user_job_preferences (user_id,preferences,updated_at)
               VALUES (%s,%s,now()) ON CONFLICT (user_id) DO UPDATE
               SET preferences=EXCLUDED.preferences,updated_at=now()""",
            [target_user_id, json.dumps(p.get("jobPreferences") or {})],
        )
    if not fields:
        return {"ok": True}
    fields.append("updated_at = now()")
    args.append(uid)
    cur.execute(f"UPDATE users SET {', '.join(fields)} WHERE firebase_uid = %s", args)
    return {"ok": True}


def op_add_todo(cur, user, p):
    requested_uid = p.get("uid") or user["firebase_uid"]
    if user["role"] != "admin" and requested_uid != user["firebase_uid"]:
        raise PermissionError("todo owner only")
    uid = resolve_user(cur, requested_uid)
    if uid is None:
        raise KeyError("user")
    cur.execute(
        "INSERT INTO todos (legacy_id, user_id, title, is_completed, created_at) VALUES (%s,%s,%s,false, now()) RETURNING id",
        [None, uid, p.get("title") or ""],
    )
    pk = cur.fetchone()[0]
    cur.execute("UPDATE todos SET legacy_id = %s WHERE id = %s", [str(pk), pk])
    return {"id": str(pk)}


def op_toggle_todo(cur, user, p):
    row = resolve_row(cur, "todos", p["todoId"])
    if not row:
        raise KeyError("todo")
    if user["role"] != "admin" and row["user_id"] != user["id"]:
        raise PermissionError("todo owner only")
    cur.execute("UPDATE todos SET is_completed = NOT is_completed WHERE id = %s", [row["id"]])


def op_delete_todo(cur, user, p):
    row = resolve_row(cur, "todos", p["todoId"])
    if row:
        if user["role"] != "admin" and row["user_id"] != user["id"]:
            raise PermissionError("todo owner only")
        cur.execute("DELETE FROM todos WHERE id = %s", [row["id"]])


def op_set_seat_presence(cur, user, p):
    _require_staff(user)
    student_uid = str(p.get("userId") or "")
    state = p.get("state")
    if state not in ("confirmed", "held"):
        raise ValueError("invalid seat presence state")
    try:
        presence_date = date.fromisoformat(str(p["dateKey"]))
        period = int(p["period"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid seat presence date or period") from exc
    if period not in (9, 10, 11, 12, 14, 15, 16, 17):
        raise ValueError("invalid seat presence period")
    cur.execute(
        "SELECT id, cohort_id FROM users WHERE firebase_uid = %s AND role = 'student' AND is_active = true",
        [student_uid],
    )
    student = cur.fetchone()
    if not student:
        raise KeyError("student")
    student_id, cohort_id = student
    if not can_access_cohort(user, cohort_id):
        raise PermissionError("cohort only")
    cur.execute(
        """INSERT INTO seat_presences
               (cohort_id, user_id, presence_date, period, state, updated_by, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, now())
               ON CONFLICT (cohort_id, user_id, presence_date, period)
               DO UPDATE SET state = EXCLUDED.state, updated_by = EXCLUDED.updated_by,
                             updated_at = now()
               RETURNING id""",
        [cohort_id, student_id, presence_date, str(period), state, user["id"]],
    )
    return {"id": str(cur.fetchone()[0])}


def op_create_notice(cur, user, p):
    _require_staff(user)
    cohort_id = resolve_cohort(cur, p.get("cohortId"), user)
    if not can_access_cohort(user, cohort_id) and user["role"] != "admin":
        raise PermissionError("cohort")
    cur.execute("SELECT code FROM cohorts WHERE id = %s", [cohort_id])
    code = cur.fetchone()[0]
    cur.execute(
        """INSERT INTO notices (cohort_id, title, content, author_id, author_name, is_favorite, priority, vector_chunk_count, created_at, updated_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,0, now(), now()) RETURNING id""",
        [cohort_id, p.get("title") or "", p.get("content") or "", user["id"],
         p.get("authorName") or user["display_name"], bool(p.get("isFavorite")), int(p.get("priority") or 0)],
    )
    pk = cur.fetchone()[0]
    cur.execute("UPDATE notices SET legacy_id = %s WHERE id = %s", [str(pk), pk])
    schedule_notice_vector(
        cohort_code=code, notice_id=pk,
        data={"title": p.get("title"), "content": p.get("content"), "author_id": user["id"],
              "author_name": p.get("authorName") or user["display_name"],
              "is_favorite": bool(p.get("isFavorite")), "priority": int(p.get("priority") or 0)},
        previous_chunk_count=0,
    )
    return {"id": str(pk)}


def op_update_notice(cur, user, p):
    row = resolve_row(cur, "notices", p["noticeId"])
    if not row:
        raise KeyError("notice")
    if user["role"] != "admin" and not (user["role"] == "instructor" and row.get("author_id") == user["id"]):
        raise PermissionError("notice")
    title = p.get("title", row["title"])
    content = p.get("content", row["content"])
    fav = p.get("isFavorite", row["is_favorite"])
    cur.execute(
        "UPDATE notices SET title=%s, content=%s, is_favorite=%s, updated_at=now() WHERE id=%s",
        [title, content, bool(fav), row["id"]],
    )
    cur.execute("SELECT code FROM cohorts WHERE id = %s", [row["cohort_id"]])
    code = cur.fetchone()[0]
    schedule_notice_vector(
        cohort_code=code, notice_id=row["id"],
        data={"title": title, "content": content, "author_id": row.get("author_id")},
        previous_chunk_count=row.get("vector_chunk_count") or 0,
    )


def op_delete_notice(cur, user, p):
    _require_admin(user)
    row = resolve_row(cur, "notices", p["noticeId"])
    if not row:
        return
    cur.execute("SELECT code FROM cohorts WHERE id = %s", [row["cohort_id"]])
    code = cur.fetchone()[0]
    cur.execute("DELETE FROM notices WHERE id = %s", [row["id"]])
    schedule_notice_vector(cohort_code=code, notice_id=row["id"], data=None,
                           previous_chunk_count=row.get("vector_chunk_count") or 0)


def _camel_to_snake(name: str) -> str:
    out = []
    for ch in name:
        if ch.isupper():
            out.append("_")
            out.append(ch.lower())
        else:
            out.append(ch)
    return "".join(out)


def _table_columns(cur, table: str) -> set[str]:
    cur.execute(
        """SELECT column_name FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = %s""",
        [table],
    )
    return {r[0] for r in cur.fetchall()}


def _array_columns(cur, table: str) -> set[str]:
    """text[] 같은 배열 칸 — 목록을 JSON 글자로 바꾸면 안 되고 그대로 넣어야 한다."""
    cur.execute(
        """SELECT column_name FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = %s AND data_type = 'ARRAY'""",
        [table],
    )
    return {r[0] for r in cur.fetchall()}


# 화면 id(legacy_id)로 오는 관계 칸 → 그 표의 번호. parent_id 는 같은 표를 가리킨다.
_REF_TABLES = {
    "resume_id": "resumes",
    "assessment_id": "assessments",
    "submission_id": "assessment_submissions",
    "question_id": "assessment_questions",
    "request_id": "purchase_requests",
    "product_id": "mileage_products",
    "task_id": "form_tasks",
    "source_id": "study_sources",
    "sheet_id": "curriculum_sheets",
    "room_id": "seating_rooms",
    "parent_id": "",
}


def _prepare_row(cur, user, table: str, payload: dict, columns: set[str]) -> dict:
    import json

    arrays = _array_columns(cur, table)
    data = {}
    skip = {"id", "pk", "legacy_id"}
    for key, value in payload.items():
        if key in ("table", "action", "op"):
            continue
        col = _camel_to_snake(key)
        if table == "attendances":
            col = {"date_key": "attendance_date", "status_source": "data_source"}.get(col, col)
        if col in ("uid", "firebase_uid") and "user_id" in columns and "user_id" not in data:
            resolved = resolve_user(cur, str(value)) if value else None
            if resolved:
                data["user_id"] = resolved
            continue
        if col in ("user_id", "author_id", "created_by", "updated_by", "reviewed_by",
                    "adjusted_by", "published_by", "uploaded_by") and value not in (None, ""):
            if isinstance(value, str) and not str(value).isdigit():
                resolved = resolve_user(cur, value)
                if resolved:
                    data[col] = resolved
                    continue
        if col in _REF_TABLES and value not in (None, "") and not str(value).isdigit():
            ref = resolve_row(cur, _REF_TABLES[col] if col != "parent_id" else table, value)
            if ref:
                data[col] = ref["id"]
            continue
        if col == "cohort_id" and value not in (None, ""):
            resolved = resolve_cohort(cur, value, user)
            if resolved:
                data[col] = resolved
                continue
        if col not in columns or col in skip:
            continue
        if isinstance(value, list) and col in arrays:
            data[col] = value
        elif isinstance(value, (dict, list)):
            data[col] = json.dumps(value)
        else:
            data[col] = value
    if table == "resumes" and "sections" in payload:
        current_content = payload.get("content")
        if not isinstance(current_content, dict) and payload.get("id"):
            existing = resolve_row(cur, "resumes", payload["id"])
            current_content = (existing or {}).get("content")
        merged_content = dict(current_content) if isinstance(current_content, dict) else {}
        merged_content["section_status"] = payload.get("sections") or {}
        data["content"] = json.dumps(merged_content)
    if "cohort_id" in columns and "cohort_id" not in data:
        resolved = resolve_cohort(cur, payload.get("cohortId"), user)
        if resolved:
            data["cohort_id"] = resolved
    if "user_id" in columns and "user_id" not in data and user.get("id"):
        if payload.get("action") == "insert" and user.get("role") == "student":
            data["user_id"] = user["id"]
    if "author_id" in columns and "author_id" not in data:
        data["author_id"] = user["id"]
    return data


def _validate_resume_write(cur, user, data: dict, row: dict | None) -> None:
    owner_id = row["user_id"] if row else data.get("user_id") or user["id"]
    if user["role"] != "admin" and owner_id != user["id"]:
        raise PermissionError("resume owner only")
    if row and "user_id" in data and data["user_id"] != owner_id:
        raise ValueError("resume owner cannot be changed")
    if row and "cohort_id" in data and data["cohort_id"] != row["cohort_id"]:
        raise ValueError("resume cohort cannot be changed")
    if not row and user["role"] != "admin":
        data["user_id"] = user["id"]
        data["cohort_id"] = user["cohort_id"]

    base_id = data.get("base_resume_id", row.get("base_resume_id") if row else None)
    is_base = data.get("is_base_resume", row.get("is_base_resume") if row else False)
    if is_base and base_id:
        raise ValueError("base resume cannot have a parent")
    if base_id:
        parent = resolve_row(cur, "resumes", base_id)
        if not parent or not parent["is_base_resume"] or parent["user_id"] != owner_id:
            raise ValueError("base resume must belong to the same user")
        if row and parent["id"] == row["id"]:
            raise ValueError("resume cannot reference itself")
        data["base_resume_id"] = parent["id"]

    job_id = data.get("linked_job_id")
    if job_id:
        cur.execute("SELECT 1 FROM jobs.jobs WHERE job_id = %s", [str(job_id)])
        if not cur.fetchone():
            raise ValueError("linked job does not exist")


def _validate_record_submission_write(user, data: dict, row: dict | None) -> None:
    cohort_id = row["cohort_id"] if row else data.get("cohort_id") or user.get("cohort_id")
    if cohort_id is None:
        raise ValueError("submission cohort required")
    if user["role"] != "admin" and not can_access_cohort(user, cohort_id):
        raise PermissionError("cohort only")
    if row and "user_id" in data and data["user_id"] != row["user_id"]:
        raise ValueError("submission owner cannot be changed")
    if row and "cohort_id" in data and data["cohort_id"] != row["cohort_id"]:
        raise ValueError("submission cohort cannot be changed")
    if user["role"] == "student":
        owner_id = row["user_id"] if row else data.get("user_id") or user["id"]
        if owner_id != user["id"]:
            raise PermissionError("submission owner only")
        if any(key in data for key in ("reviewed_by", "reviewed_at", "review_comment")):
            raise PermissionError("review fields are staff only")
        if "status" in data and data["status"] not in ("draft", "submitted"):
            raise PermissionError("review status is staff only")
        if not row:
            data["user_id"] = user["id"]
            data["cohort_id"] = user["cohort_id"]


def op_upsert_sql(cur, user, p):
    """Allowlisted 테이블 INSERT/UPDATE/DELETE."""
    table = p["table"]
    allowed = {
        "scheduled_notices", "alert_popups", "alert_popup_dismissals",
        "record_submissions", "resumes", "resume_feedback", "attendances",
        "seat_presences", "inflearn_packages", "study_sources", "study_notes",
        "youtube_recommendations", "assessments", "assessment_questions",
        "assessment_submissions", "curriculum_sheets", "submission_tasks", "submission_responses",
        "mileage_settings", "mileage_products", "mileage_cart_items",
        "purchase_requests", "mileage_transactions", "cohort_seating",
        "project_teams", "curriculum_pdfs", "student_intakes", "cohorts",
        "materials", "schedules",
        "mission_progress", "recommendation_events",
    }
    if table not in allowed:
        raise ValueError("table not allowed")
    # The generic writer accepts every matching DB column. Until per-domain
    # validation exists, students must not submit scores, prices, approval
    # states or another user's IDs through it.
    if user["role"] == "student" and table not in {
        "record_submissions", "resumes", "alert_popup_dismissals",
    }:
        raise PermissionError("student write requires a dedicated command")
    if table == "cohorts":
        _require_admin(user)
    elif table in {
        "scheduled_notices", "alert_popups", "inflearn_packages",
        "youtube_recommendations", "assessments", "assessment_questions",
        "curriculum_sheets", "submission_tasks", "mileage_settings",
        "mileage_products", "mileage_transactions", "cohort_seating",
        "project_teams", "curriculum_pdfs", "materials", "schedules",
        "seat_presences", "student_intakes", "attendances",
        "resume_feedback", "study_sources",
    }:
        _require_staff(user)
    if table in ("mileage_transactions", "assessment_submissions", "study_notes", "attendances") and user["role"] not in ("admin", "instructor"):
        if p.get("action") not in ("insert",) or table not in ("assessment_submissions", "attendances"):
            if user["role"] != "admin":
                raise PermissionError("server-only write")
    action = p.get("action")
    if action == "delete":
        row = resolve_row(cur, table, p["id"])
        if table == "resumes":
            if row and user["role"] != "admin" and row["user_id"] != user["id"]:
                raise PermissionError("resume owner only")
        elif table == "record_submissions":
            _require_staff(user)
            if row and user["role"] != "admin" and not can_access_cohort(user, row["cohort_id"]):
                raise PermissionError("cohort only")
        else:
            _require_staff(user)
        if row:
            cur.execute(f"DELETE FROM {table} WHERE id = %s", [row["id"]])
        return {"ok": True}
    if table == "scheduled_notices":
        return op_upsert_scheduled(cur, user, p)
    if table == "alert_popups":
        return op_upsert_alert(cur, user, p)
    if table == "alert_popup_dismissals":
        return op_dismiss_alert(cur, user, p)

    columns = _table_columns(cur, table)
    data = _prepare_row(cur, user, table, p, columns)
    row_id = p.get("id")
    updating = bool(row_id) and action != "insert"
    row = resolve_row(cur, table, row_id) if updating else None
    if updating and not row:
        updating = False
    if updating:
        if not row:
            raise KeyError(table)
        if table == "resumes":
            _validate_resume_write(cur, user, data, row)
        elif table == "record_submissions":
            _validate_record_submission_write(user, data, row)
        if not data:
            return {"id": str(row.get("legacy_id") or row["id"])}
        if "updated_at" in columns:
            data["updated_at"] = None
        assignments = []
        args = []
        for col, value in data.items():
            if col == "updated_at":
                assignments.append("updated_at = now()")
            else:
                assignments.append(f"{col} = %s")
                args.append(value)
        args.append(row["id"])
        cur.execute(f"UPDATE {table} SET {', '.join(assignments)} WHERE id = %s", args)
        # 화면이 쥔 id 를 그대로 돌려준다(번호를 돌려주면 화면이 다른 행으로 본다)
        return {"id": str(row.get("legacy_id") or row["id"])}

    if table == "resumes":
        _validate_resume_write(cur, user, data, None)
    elif table == "record_submissions":
        _validate_record_submission_write(user, data, None)
    if "created_at" in columns:
        data.pop("created_at", None)
    if "updated_at" in columns:
        data.pop("updated_at", None)
    # 화면이 새 행에 붙여 둔 id(예: r-ab12cd)를 legacy_id 로 보관한다. bootstrap 이 legacy_id 를 공개 id 로
    # 보내므로, 저장 뒤 다시 받아도 화면이 쥔 id 가 그대로 이어진다(새 이력서를 만들자마자 「찾을 수 없음」이던 문제).
    if row_id and "legacy_id" in columns and "legacy_id" not in data:
        data["legacy_id"] = str(row_id)
    cols = list(data.keys())
    extras = []
    extra_vals = []
    if "created_at" in columns:
        extras.append("created_at")
        extra_vals.append("now()")
    if "updated_at" in columns:
        extras.append("updated_at")
        extra_vals.append("now()")
    all_cols = cols + extras
    placeholders = ["%s"] * len(cols) + extra_vals
    conflict_clause = ""
    if table == "attendances" and action == "insert":
        # The attendance screen sends an insert for each status change. Keep
        # the same daily row instead of violating uq_attendance_user_date.
        mutable = [col for col in cols if col not in ("user_id", "attendance_date")]
        updates = [f"{col} = EXCLUDED.{col}" for col in mutable]
        updates.append("updated_at = now()")
        conflict_clause = (
            " ON CONFLICT (user_id, attendance_date) DO UPDATE SET "
            + ", ".join(updates)
        )
    cur.execute(
        f"INSERT INTO {table} ({', '.join(all_cols)}) VALUES ({', '.join(placeholders)})"
        f"{conflict_clause} RETURNING id",
        [data[c] for c in cols],
    )
    fetched = cur.fetchone()
    if not fetched:
        return {"ok": True}
    pk = fetched[0]
    if "legacy_id" in columns and not data.get("legacy_id"):
        # 화면이 id 를 주지 않았을 때만 번호를 legacy_id 로 — 준 id 는 위에서 넣었다
        cur.execute(f"UPDATE {table} SET legacy_id = %s WHERE id = %s", [str(pk), pk])
    return {"id": data.get("legacy_id") or str(pk)}


def op_create_user(cur, user, p):
    _require_admin(user)
    import uuid

    firebase_uid = p.get("uid") or p.get("firebaseUid") or f"local-{uuid.uuid4().hex[:20]}"
    cohort_id = resolve_cohort(cur, p.get("cohortId"), user)
    import json
    cur.execute(
        """INSERT INTO users (firebase_uid, email, password, display_name, role, cohort_id,
               seat_number, is_active, must_change_password, motto, social_links,
               mileage_balance, created_at, updated_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0, now(), now())
           RETURNING id""",
        [
            firebase_uid,
            (p.get("email") or "").strip().lower(),
            make_password(p.get("password")) if p.get("password") else make_password(None),
            p.get("displayName") or "",
            p.get("role") or "student",
            cohort_id,
            p.get("seatNumber"),
            bool(p.get("isActive", True)),
            bool(p.get("mustChangePassword", True)),
            p.get("motto"),
            json.dumps(p.get("socialLinks") or {}),
        ],
    )
    created_user_id = cur.fetchone()[0]
    for raw_skill in p.get("skills") or []:
        name = " ".join(str(raw_skill).split()).casefold()
        if not name:
            continue
        cur.execute(
            """INSERT INTO skills (canonical_name,created_at) VALUES (%s,now())
               ON CONFLICT (canonical_name) DO UPDATE SET canonical_name=EXCLUDED.canonical_name RETURNING id""",
            [name],
        )
        cur.execute(
            """INSERT INTO user_skills (user_id,skill_id,source,updated_at)
               VALUES (%s,%s,'profile',now()) ON CONFLICT DO NOTHING""",
            [created_user_id, cur.fetchone()[0]],
        )
    import json
    cur.execute(
        """INSERT INTO user_job_preferences (user_id,preferences,updated_at) VALUES (%s,%s,now())""",
        [created_user_id, json.dumps(p.get("jobPreferences") or {})],
    )
    return {"id": firebase_uid, "uid": firebase_uid}


def op_create_cohort(cur, user, p):
    _require_admin(user)
    code = p.get("cohortId") or p.get("code")
    if not code:
        raise ValueError("cohort code required")
    cur.execute(
        """INSERT INTO cohorts (code, name, description, status, is_active, term_number,
               classroom_name, created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s, now()) RETURNING id""",
        [
            code,
            p.get("name") or code,
            p.get("description"),
            p.get("status") or "active",
            bool(p.get("isActive", True)),
            p.get("termNumber"),
            p.get("classroomName"),
        ],
    )
    pk = cur.fetchone()[0]
    return {"id": str(pk), "cohortId": code}


def op_update_cohort(cur, user, p):
    _require_admin(user)
    code = p.get("cohortId") or p.get("code")
    cur.execute("SELECT id FROM cohorts WHERE code = %s", [code])
    row = cur.fetchone()
    if not row:
        raise KeyError("cohort")
    fields = []
    args = []
    mapping = {
        "name": "name",
        "description": "description",
        "status": "status",
        "isActive": "is_active",
        "termNumber": "term_number",
        "classroomName": "classroom_name",
    }
    for src, col in mapping.items():
        if src in p:
            fields.append(f"{col} = %s")
            args.append(p[src])
    if not fields:
        return {"ok": True}
    args.append(row[0])
    cur.execute(f"UPDATE cohorts SET {', '.join(fields)} WHERE id = %s", args)
    return {"ok": True}


def _hhmm(value) -> str | None:
    if value in (None, ""):
        return None
    text = str(value)
    return text[:5] if len(text) >= 5 else text


def op_upsert_scheduled(cur, user, p):
    _require_staff(user)
    from lms.publish import compute_next_publish_at

    cohort_id = resolve_cohort(cur, p.get("cohortId"), user)
    if user["role"] != "admin" and not can_access_cohort(user, cohort_id):
        raise PermissionError("cohort")
    title = p.get("title") or ""
    content = p.get("content") or ""
    repeat_type = (p.get("repeatType") or "once").lower()
    publish_time = _hhmm(p.get("publishTime")) or "09:00"
    weekday = int(p.get("weekday") or 1)
    is_active = bool(p.get("isActive", True))
    is_favorite = bool(p.get("isFavorite", False))
    publish_at_raw = p.get("publishAt")
    publish_at = None
    if publish_at_raw:
        from django.utils import timezone as dj_tz
        from django.utils.dateparse import parse_datetime

        if hasattr(publish_at_raw, "year"):
            publish_at = publish_at_raw
        else:
            publish_at = parse_datetime(str(publish_at_raw).replace("Z", "+00:00"))
        if publish_at is not None and dj_tz.is_naive(publish_at):
            publish_at = dj_tz.make_aware(publish_at, dj_tz.get_current_timezone())
    next_at = (
        compute_next_publish_at(repeat_type, publish_time, publish_at, weekday) if is_active else None
    )
    row_id = p.get("id")
    if row_id and p.get("action") != "insert":
        row = resolve_row(cur, "scheduled_notices", row_id)
        if not row:
            raise KeyError("scheduled_notice")
        cur.execute(
            """UPDATE scheduled_notices
               SET title=%s, content=%s, is_favorite=%s, repeat_type=%s, publish_time=%s,
                   publish_at=%s, weekday=%s, is_active=%s, next_publish_at=%s, updated_at=now()
               WHERE id=%s""",
            [title, content, is_favorite, repeat_type, publish_time, publish_at, weekday,
             is_active, next_at, row["id"]],
        )
        return {"id": str(row["id"])}
    cur.execute(
        """INSERT INTO scheduled_notices
           (cohort_id, title, content, author_id, is_favorite, repeat_type, publish_time,
            publish_at, weekday, is_active, next_publish_at, created_at, updated_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now(), now()) RETURNING id""",
        [cohort_id, title, content, user["id"], is_favorite, repeat_type, publish_time,
         publish_at, weekday, is_active, next_at],
    )
    pk = cur.fetchone()[0]
    cur.execute("UPDATE scheduled_notices SET legacy_id = %s WHERE id = %s", [str(pk), pk])
    return {"id": str(pk)}


def op_upsert_alert(cur, user, p):
    _require_staff(user)
    cohort_id = resolve_cohort(cur, p.get("cohortId"), user)
    if user["role"] != "admin" and not can_access_cohort(user, cohort_id):
        raise PermissionError("cohort")
    title = p.get("title") or ""
    content = p.get("content") or ""
    is_active = bool(p.get("isActive", True))
    sort_order = int(p.get("sortOrder") or 0)
    link_url = p.get("linkUrl") or None
    start_time = _hhmm(p.get("startTime"))
    end_time = _hhmm(p.get("endTime"))
    row_id = p.get("id")
    if row_id and p.get("action") != "insert":
        row = resolve_row(cur, "alert_popups", row_id)
        if not row:
            raise KeyError("alert_popup")
        cur.execute(
            """UPDATE alert_popups
               SET title=%s, content=%s, is_active=%s, sort_order=%s, link_url=%s,
                   start_time=%s, end_time=%s, updated_at=now()
               WHERE id=%s""",
            [title, content, is_active, sort_order, link_url, start_time, end_time, row["id"]],
        )
        return {"id": str(row["id"])}
    cur.execute(
        """INSERT INTO alert_popups
           (cohort_id, title, content, author_id, is_active, sort_order, link_url,
            start_time, end_time, created_at, updated_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now(), now()) RETURNING id""",
        [cohort_id, title, content, user["id"], is_active, sort_order, link_url, start_time, end_time],
    )
    pk = cur.fetchone()[0]
    cur.execute("UPDATE alert_popups SET legacy_id = %s WHERE id = %s", [str(pk), pk])
    return {"id": str(pk)}


def op_dismiss_alert(cur, user, p):
    popup = resolve_row(cur, "alert_popups", p.get("popupId") or p.get("id"))
    if not popup:
        raise KeyError("alert_popup")
    date_key = p.get("dateKey")
    cur.execute(
        """INSERT INTO alert_popup_dismissals (user_id, popup_id, date_key)
           VALUES (%s,%s,%s)
           ON CONFLICT (user_id, popup_id) DO UPDATE SET date_key = EXCLUDED.date_key""",
        [user["id"], popup["id"], date_key],
    )
    return {"ok": True}


def op_publish_scheduled(cur, user, p):
    _require_staff(user)
    from lms.publish import publish_scheduled_notices

    ids = p.get("ids") or p.get("scheduledIds")
    count = publish_scheduled_notices(
        ids=ids, cohort_id=None if user["role"] == "admin" else user.get("cohort_id") or -1,
    )
    return {"ok": True, "published": count}


def op_touch_last_login(cur, user, p):
    cur.execute("UPDATE users SET last_login = now() WHERE firebase_uid = %s", [user["firebase_uid"]])


def op_mileage_adjust(cur, user, p):
    _require_admin(user)
    cur.execute("SELECT id, cohort_id FROM users WHERE firebase_uid = %s FOR UPDATE", [p["uid"]])
    row = cur.fetchone()
    if not row:
        raise KeyError("user")
    amount = int(p.get("amount") or 0)
    cur.execute(
        """INSERT INTO mileage_transactions (cohort_id, user_id, amount, type, reason, adjusted_by, created_at)
           VALUES (%s,%s,%s,'admin_adjust',%s,%s, now())""",
        [row[1], row[0], amount, p.get("reason") or "", user["id"]],
    )
    cur.execute("UPDATE users SET mileage_balance = mileage_balance + %s WHERE id = %s", [amount, row[0]])


def op_save_curriculum_pdf(cur, user, p):
    _require_staff(user)
    cohort_id = resolve_cohort(cur, p.get("cohortId"), user)
    cur.execute(
        """INSERT INTO curriculum_pdfs (cohort_id, storage_key, original_filename, published, updated_by, updated_at)
           VALUES (%s,%s,%s,%s,%s, now())
           ON CONFLICT (cohort_id) DO UPDATE SET storage_key = EXCLUDED.storage_key,
              original_filename = EXCLUDED.original_filename, published = EXCLUDED.published,
              updated_by = EXCLUDED.updated_by, updated_at = now()""",
        [cohort_id, p.get("storageKey"), p.get("fileName"), True, user["id"]],
    )


def op_clear_curriculum_pdf(cur, user, p):
    _require_staff(user)
    cohort_id = resolve_cohort(cur, p.get("cohortId"), user)
    cur.execute(
        "UPDATE curriculum_pdfs SET storage_key=NULL, original_filename=NULL, published=false, updated_at=now() WHERE cohort_id=%s",
        [cohort_id],
    )


def op_publish_seating(cur, user, p):
    _require_staff(user)
    cohort_id = resolve_cohort(cur, p.get("cohortId"), user)
    cur.execute(
        "UPDATE cohort_seating SET published=true, updated_by=%s, updated_at=now() WHERE cohort_id=%s",
        [user["id"], cohort_id],
    )
    if cur.rowcount == 0:
        raise KeyError("seating")


OPS = {
    **PRACTICE_OPS,
    "updateProfile": op_update_profile,
    "createUser": op_create_user,
    "createCohort": op_create_cohort,
    "updateCohort": op_update_cohort,
    "addTodo": op_add_todo,
    "toggleTodo": op_toggle_todo,
    "deleteTodo": op_delete_todo,
    "setSeatPresence": op_set_seat_presence,
    "createNotice": op_create_notice,
    "updateNotice": op_update_notice,
    "deleteNotice": op_delete_notice,
    "touchLastLogin": op_touch_last_login,
    "mileageAdjust": op_mileage_adjust,
    "saveCurriculumPdf": op_save_curriculum_pdf,
    "clearCurriculumPdf": op_clear_curriculum_pdf,
    "publishSeating": op_publish_seating,
    "upsert": op_upsert_sql,
    "publishScheduledNotices": op_publish_scheduled,
    "upsertScheduledNotice": op_upsert_scheduled,
    "upsertAlertPopup": op_upsert_alert,
    "dismissAlertPopup": op_dismiss_alert,
}

# 좌석 배치 쓰기(강의실 틀 · 배치 · 프로젝트 팀)는 따로 둔다 — 위 도우미를 쓰므로 맨 끝에서 불러온다.
from lms.seating_commands import SEATING_OPS  # noqa: E402

OPS.update(SEATING_OPS)

# 복습 문제 쓰기(풀이 기록 · 신고 · 강사 결정) — practice 스키마
from lms.practice_service import PRACTICE_OPS  # noqa: E402

OPS.update(PRACTICE_OPS)

# 기록실 · 평가 · 설문 · 마일리지 · 학습실 · 자리 확인 쓰기 — 여러 표를 함께 고치는 것들
from lms.content_commands import CONTENT_OPS  # noqa: E402

OPS.update(CONTENT_OPS)
