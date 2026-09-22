"""Named mutations. firestore.rules 권한 + 서버만 write 는 관리자."""

from __future__ import annotations

from django.db import connection, transaction

from lms.permissions import can_access_cohort
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
        "skills": "skills",
        "socialLinks": "social_links",
        "birthDate": "birth_date",
        "personalEmail": "personal_email",
        "jobPreferences": "job_preferences",
        "photoUrl": "photo_url",
        "photoStoragePath": "photo_storage_path",
        "mustChangePassword": "must_change_password",
        "password": "password",
        "lastLoginAt": "last_login",
    }
    for src, col in mapping.items():
        if src in p:
            fields.append(f"{col} = %s")
            args.append(p[src])
    if not fields:
        return {"ok": True}
    fields.append("updated_at = now()")
    args.append(uid)
    cur.execute(f"UPDATE users SET {', '.join(fields)} WHERE firebase_uid = %s", args)
    return {"ok": True}


def op_add_todo(cur, user, p):
    uid = resolve_user(cur, p.get("uid") or user["firebase_uid"])
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
    cur.execute("UPDATE todos SET is_completed = NOT is_completed WHERE id = %s", [row["id"]])


def op_delete_todo(cur, user, p):
    row = resolve_row(cur, "todos", p["todoId"])
    if row:
        cur.execute("DELETE FROM todos WHERE id = %s", [row["id"]])


def op_create_notice(cur, user, p):
    _require_staff(user)
    cohort_id = resolve_cohort(cur, p.get("cohortId"), user)
    if not can_access_cohort(user, cohort_id) and user["role"] != "admin":
        raise PermissionError("cohort")
    cur.execute("SELECT code FROM cohorts WHERE id = %s", [cohort_id])
    code = cur.fetchone()[0]
    cur.execute(
        """INSERT INTO notices (cohort_id, title, content, author_id, author_name, is_favorite, priority, created_at, updated_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s, now(), now()) RETURNING id""",
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


def _prepare_row(cur, user, table: str, payload: dict, columns: set[str]) -> dict:
    import json

    data = {}
    skip = {"id", "pk", "legacy_id"}
    for key, value in payload.items():
        if key in ("table", "action", "op"):
            continue
        col = _camel_to_snake(key)
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
        if col == "cohort_id" and value not in (None, ""):
            resolved = resolve_cohort(cur, value, user)
            if resolved:
                data[col] = resolved
                continue
        if col not in columns or col in skip:
            continue
        if isinstance(value, (dict, list)):
            data[col] = json.dumps(value)
        else:
            data[col] = value
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


def op_upsert_sql(cur, user, p):
    """Allowlisted 테이블 INSERT/UPDATE/DELETE."""
    table = p["table"]
    allowed = {
        "scheduled_notices", "alert_popups", "alert_popup_dismissals",
        "record_submissions", "resumes", "resume_feedback", "attendances",
        "roll_calls", "inflearn_packages", "study_sources", "study_notes",
        "youtube_recommendations", "assessments", "assessment_questions",
        "assessment_submissions", "curriculum_sheets", "form_tasks", "form_responses",
        "mileage_settings", "mileage_products", "mileage_cart_items",
        "purchase_requests", "mileage_transactions", "seating_rooms",
        "seating_assignments", "seat_assignments", "seating_cells",
        "project_teams", "curriculum_pdfs", "student_intakes", "cohorts",
        "assignments", "materials", "schedules", "weekly_tasks", "weekly_progress",
        "mission_progress", "recommendation_events",
    }
    if table not in allowed:
        raise ValueError("table not allowed")
    if table in ("mileage_transactions", "assessment_submissions", "study_notes", "attendances") and user["role"] not in ("admin", "instructor"):
        if p.get("action") not in ("insert",) or table not in ("assessment_submissions", "attendances"):
            if user["role"] != "admin":
                raise PermissionError("server-only write")
    action = p.get("action")
    if action == "delete":
        _require_staff(user)
        row = resolve_row(cur, table, p["id"])
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
    if updating:
        row = resolve_row(cur, table, row_id)
        if not row:
            raise KeyError(table)
        if not data:
            return {"id": str(row["id"])}
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
        return {"id": str(row["id"])}

    if "created_at" in columns:
        data.pop("created_at", None)
    if "updated_at" in columns:
        data.pop("updated_at", None)
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
    cur.execute(
        f"INSERT INTO {table} ({', '.join(all_cols)}) VALUES ({', '.join(placeholders)}) RETURNING id",
        [data[c] for c in cols],
    )
    fetched = cur.fetchone()
    if not fetched:
        return {"ok": True}
    pk = fetched[0]
    if "legacy_id" in columns:
        cur.execute(f"UPDATE {table} SET legacy_id = %s WHERE id = %s", [str(pk), pk])
    return {"id": str(pk)}


def op_create_user(cur, user, p):
    _require_admin(user)
    import uuid

    firebase_uid = p.get("uid") or p.get("firebaseUid") or f"local-{uuid.uuid4().hex[:20]}"
    cohort_id = resolve_cohort(cur, p.get("cohortId"), user)
    import json
    cur.execute(
        """INSERT INTO users (firebase_uid, email, password, display_name, role, cohort_id,
               seat_number, is_active, must_change_password, motto, skills, social_links,
               job_preferences, mileage_balance, created_at, updated_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0, now(), now())
           RETURNING id""",
        [
            firebase_uid,
            (p.get("email") or "").strip().lower(),
            p.get("password") or "",
            p.get("displayName") or "",
            p.get("role") or "student",
            cohort_id,
            p.get("seatNumber"),
            bool(p.get("isActive", True)),
            bool(p.get("mustChangePassword", True)),
            p.get("motto"),
            json.dumps(p.get("skills") or []),
            json.dumps(p.get("socialLinks") or {}),
            json.dumps(p.get("jobPreferences") or {"targetRoles": [], "regions": [], "employmentTypes": []}),
        ],
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
    count = publish_scheduled_notices(ids=ids)
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
           VALUES (%s,%s,%s,'adjust',%s,%s, now())""",
        [row[1], row[0], amount, p.get("reason") or "", user["id"]],
    )
    cur.execute("UPDATE users SET mileage_balance = mileage_balance + %s WHERE id = %s", [amount, row[0]])


def op_save_curriculum_pdf(cur, user, p):
    _require_staff(user)
    cohort_id = resolve_cohort(cur, p.get("cohortId"), user)
    cur.execute(
        """INSERT INTO curriculum_pdfs (cohort_id, full_pdf_url, full_pdf_file_name, published, updated_by, updated_at)
           VALUES (%s,%s,%s,%s,%s, now())
           ON CONFLICT (cohort_id) DO UPDATE SET full_pdf_url = EXCLUDED.full_pdf_url,
             full_pdf_file_name = EXCLUDED.full_pdf_file_name, published = EXCLUDED.published,
             updated_by = EXCLUDED.updated_by, updated_at = now()""",
        [cohort_id, p.get("pdfUrl"), p.get("fileName"), True, user["id"]],
    )


def op_clear_curriculum_pdf(cur, user, p):
    _require_staff(user)
    cohort_id = resolve_cohort(cur, p.get("cohortId"), user)
    cur.execute(
        "UPDATE curriculum_pdfs SET full_pdf_url=NULL, full_pdf_file_name=NULL, published=false, updated_at=now() WHERE cohort_id=%s",
        [cohort_id],
    )


def op_publish_seating(cur, user, p):
    _require_staff(user)
    cohort_id = resolve_cohort(cur, p.get("cohortId"), user)
    room = resolve_row(cur, "seating_rooms", p["roomId"])
    if not room:
        raise KeyError("room")
    cur.execute(
        """UPDATE seating_assignments SET status = 'draft'
           FROM seating_rooms r
           WHERE seating_assignments.room_id = r.id AND r.cohort_id = %s AND seating_assignments.status = 'published'""",
        [cohort_id],
    )
    cur.execute(
        """INSERT INTO seating_assignments (room_id, status, published_by, published_at, updated_by, updated_at)
           VALUES (%s,'published',%s, now(), %s, now())
           ON CONFLICT (room_id) DO UPDATE SET status='published', published_by=EXCLUDED.published_by,
             published_at=now(), updated_by=EXCLUDED.updated_by, updated_at=now()""",
        [room["id"], user["id"], user["id"]],
    )
    cur.execute("UPDATE cohorts SET published_seating_room_id = %s WHERE id = %s", [room["id"], cohort_id])


OPS = {
    "updateProfile": op_update_profile,
    "createUser": op_create_user,
    "createCohort": op_create_cohort,
    "updateCohort": op_update_cohort,
    "addTodo": op_add_todo,
    "toggleTodo": op_toggle_todo,
    "deleteTodo": op_delete_todo,
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
