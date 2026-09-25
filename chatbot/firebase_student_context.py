"""인증된 학생 범위 안에서 Postgres/Redis/S3 문맥을 조회한다."""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Callable

from psycopg.rows import dict_row

from chatbot.database import connect
from chatbot.unit_period import calculate_unit_period_context

KST = timezone(timedelta(hours=9), name="Asia/Seoul")
DATE_RE = re.compile(
    r"(?:(\d{4})\s*(?:년|[./-])\s*)?"
    r"(\d{1,2})\s*(?:월|[./-])\s*(\d{1,2})\s*일?"
)
ALLOWED_SCOPES = {
    "student_private",
    "cohort_shared",
    "curriculum_files",
    "material_files",
    "record_files",
    "assignment_files",
    "study_room",
}
STUDY_RECENT_SETS = 5
PRACTICE_AUTO_TIME = "매일 18:30 — 그날 수업 저장소에 올라온 내용으로 자동 출제(강사가 끈 저장소는 제외)"
BLOCKED_KEYS = {
    "password", "passwordhash", "initialpassword", "accesstoken", "refreshtoken",
    "idtoken", "secret", "privatekey",
}
MAX_DOCS = 20
MAX_FIELD_CHARS = 4_000
MAX_FILES = 30
MAX_EXTRACTED_FILES = 5
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_FILE_TEXT = 8_000


def _connect():
    # Read-only context queries are independent; one missing legacy table must
    # not leave the transaction aborted for every later scope.
    return connect(row_factory=dict_row, autocommit=True)


def _redis():
    import redis

    return redis.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"),
        decode_responses=True,
        protocol=2,
    )


def _to_kst_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return (value.replace(tzinfo=KST) if value.tzinfo is None else value.astimezone(KST)).date()
    return value if isinstance(value, date) else None


def parse_schedule_date(label: str, course_start: date) -> date | None:
    match = DATE_RE.search(label.strip())
    if not match:
        return None
    year = int(match.group(1)) if match.group(1) else course_start.year
    month, day = int(match.group(2)), int(match.group(3))
    if not match.group(1) and month < course_start.month:
        year += 1
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _cohort_ids(cur, cohort: str) -> tuple[int | None, str]:
    row = cur.execute(
        "SELECT id, code FROM cohorts WHERE code = %s OR CAST(id AS text) = %s",
        (cohort, cohort),
    ).fetchone()
    if not row:
        return None, cohort
    return int(row["id"]), str(row["code"] or cohort)


def _user_id(cur, uid: str) -> int | None:
    row = cur.execute("SELECT id FROM users WHERE firebase_uid = %s", (uid,)).fetchone()
    return int(row["id"]) if row else None


def load_unit_period_context(session: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    cohort = session["cohort"]
    uid = session["uid"]
    with _connect() as conn:
        cur = conn.cursor()
        cid, _code = _cohort_ids(cur, cohort)
        user_id = _user_id(cur, uid)
        if cid is None:
            return {"unavailable_reason": "기수의 개강일 또는 종강일이 등록되지 않았습니다"}
        cohort_data = cur.execute(
            "SELECT start_date, end_date FROM cohorts WHERE id = %s", (cid,)
        ).fetchone() or {}
        start, end = _to_kst_date(cohort_data.get("start_date")), _to_kst_date(cohort_data.get("end_date"))
        if not start or not end:
            return {"unavailable_reason": "기수의 개강일 또는 종강일이 등록되지 않았습니다"}
        scheduled_dates: set[date] = set()
        sheet = cur.execute(
            "SELECT id FROM curriculum_sheets WHERE cohort_id = %s ORDER BY uploaded_at DESC NULLS LAST LIMIT 1",
            (cid,),
        ).fetchone()
        if sheet:
            for row in cur.execute(
                "SELECT date_label FROM curriculum_rows WHERE sheet_id = %s",
                (sheet["id"],),
            ):
                parsed = parse_schedule_date(str(row.get("date_label") or ""), start)
                if parsed and start <= parsed <= end:
                    scheduled_dates.add(parsed)
        attendance: dict[date, str] = {}
        if user_id:
            for row in cur.execute(
                "SELECT attendance_date, status FROM attendances WHERE cohort_id = %s AND user_id = %s",
                (cid, user_id),
            ):
                day = row["attendance_date"]
                if isinstance(day, datetime):
                    day = day.date()
                status = str(row.get("status") or "")
                if day and status:
                    attendance[day] = status
        return calculate_unit_period_context(
            start,
            end,
            today=today or datetime.now(KST).date(),
            scheduled_dates=scheduled_dates,
            attendance_records=attendance,
        )


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _safe(item)
            for key, item in value.items()
            if str(key).replace("_", "").lower() not in BLOCKED_KEYS
        }
    if isinstance(value, (list, tuple, set)):
        return [_safe(item) for item in value]
    if isinstance(value, str):
        return value if len(value) <= MAX_FIELD_CHARS else value[:MAX_FIELD_CHARS] + "…"
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _row(row: dict[str, Any] | None, id_key: str = "legacy_id") -> dict[str, Any] | None:
    if not row:
        return None
    data = dict(row)
    ident = data.get(id_key) or data.get("id")
    data["id"] = str(ident) if ident is not None else None
    return _safe(data)


def _rows(items: list[dict[str, Any]], limit: int = MAX_DOCS, id_key: str = "legacy_id") -> dict[str, Any]:
    return {
        "items": [_row(item, id_key) for item in items[:limit]],
        "truncated": len(items) > limit,
    }


def _put(target: dict[str, Any], errors: dict[str, str], key: str, load: Callable[[], Any]) -> None:
    try:
        target[key] = load()
    except Exception as exc:
        errors[key] = type(exc).__name__


def _student_private(cur, cid: int, uid: str, user_id: int | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    errors: dict[str, str] = {}
    _put(
        result, errors, "profile",
        lambda: _row(cur.execute("SELECT * FROM users WHERE firebase_uid = %s", (uid,)).fetchone(), "firebase_uid"),
    )
    if user_id:
        _put(
            result, errors, "todos",
            lambda: _rows(list(cur.execute(
                "SELECT * FROM todos WHERE user_id = %s ORDER BY created_at DESC NULLS LAST LIMIT %s",
                (user_id, MAX_DOCS + 1),
            ))),
        )
        _put(
            result, errors, "alert_dismissals",
            lambda: _rows(list(cur.execute(
                "SELECT * FROM alert_popup_dismissals WHERE user_id = %s LIMIT %s",
                (user_id, MAX_DOCS + 1),
            )), id_key="popup_id"),
        )
        _put(
            result, errors, "attendances",
            lambda: _rows(list(cur.execute(
                "SELECT * FROM attendances WHERE cohort_id = %s AND user_id = %s LIMIT %s",
                (cid, user_id, MAX_DOCS + 1),
            ))),
        )
        _put(
            result, errors, "submissions",
            lambda: _rows(list(cur.execute(
                "SELECT * FROM record_submissions WHERE cohort_id = %s AND user_id = %s LIMIT %s",
                (cid, user_id, MAX_DOCS + 1),
            ))),
        )
        _put(
            result, errors, "mission_progress",
            lambda: _row(cur.execute(
                "SELECT * FROM mission_progress WHERE cohort_id = %s AND user_id = %s",
                (cid, user_id),
            ).fetchone(), "user_id"),
        )
        _put(
            result, errors, "assessment_submissions",
            lambda: _rows(list(cur.execute(
                "SELECT id, legacy_id, assessment_id, user_id, submitted_at, auto_total_score, total_score, status "
                "FROM assessment_submissions WHERE user_id = %s LIMIT %s",
                (user_id, MAX_DOCS + 1),
            ))),
        )
        _put(
            result, errors, "form_responses",
            lambda: _rows(list(cur.execute(
                """SELECT sr.*, st.legacy_id AS task_legacy_id FROM submission_responses sr
                   JOIN submission_tasks st ON st.id = sr.task_id
                   JOIN submission_task_cohorts sc ON sc.task_id = st.id
                   WHERE sc.cohort_id = %s AND sr.user_id = %s LIMIT %s""",
                (cid, user_id, MAX_DOCS + 1),
            )), id_key="task_legacy_id"),
        )
        _put(
            result, errors, "resumes",
            lambda: _resume_pack(cur, cid, user_id),
        )
        _put(
            result, errors, "mileage",
            lambda: {
                "transactions": _rows(list(cur.execute(
                    "SELECT * FROM mileage_transactions WHERE cohort_id = %s AND user_id = %s LIMIT %s",
                    (cid, user_id, MAX_DOCS + 1),
                ))),
                "purchase_requests": _rows(list(cur.execute(
                    "SELECT * FROM purchase_requests WHERE cohort_id = %s AND user_id = %s LIMIT %s",
                    (cid, user_id, MAX_DOCS + 1),
                ))),
                "cart": _rows(list(cur.execute(
                    "SELECT * FROM mileage_cart_items WHERE user_id = %s LIMIT %s",
                    (user_id, MAX_DOCS + 1),
                )), id_key="product_id"),
            },
        )
    _put(
        result, errors, "unit_period_context",
        lambda: load_unit_period_context({"cohort": str(cid), "uid": uid}),
    )
    if errors:
        result["errors"] = errors
    return result


def _study_room(cur, cid: int, user_id: int | None) -> dict[str, Any]:
    """공부방 복습 문제 현황 — 오늘 나왔는지 · 몇 개 풀었는지 · 다시 풀 문제 수.

    문제 지문 · 모범답안 · 숨긴 테스트는 읽지 않는다(챗봇이 정답을 말하지 않게).
    학생이 만든 세트는 만든 본인 것만, 풀이 기록은 본인 것만.
    """
    today = datetime.now(KST).date()
    uid = user_id or 0  # 사용자 행이 없으면 풀이 기록 없이 세트만
    sets = list(cur.execute(
        """SELECT s.lesson_date, s.source_title, s.day_label, s.title, s.owner_id,
                  (s.created_at AT TIME ZONE 'Asia/Seoul')::date AS made_on,
                  count(p.id) AS total,
                  count(a.problem_id) FILTER (WHERE a.passed) AS passed,
                  count(a.problem_id) AS tried
           FROM practice_sets s
           JOIN practice_problems p ON p.problem_set_id = s.id
           LEFT JOIN practice_attempts a ON a.problem_id = p.id AND a.user_id = %(uid)s
           WHERE s.cohort_id = %(cid)s AND (s.owner_id IS NULL OR s.owner_id = %(uid)s)
           GROUP BY s.id
           ORDER BY s.lesson_date DESC, s.id DESC
           LIMIT %(limit)s""",
        {"uid": uid, "cid": cid, "limit": STUDY_RECENT_SETS},
    ))
    retry = cur.execute(
        """SELECT count(*) AS n FROM practice_attempts a
           JOIN practice_problems p ON p.id = a.problem_id
           JOIN practice_sets s ON s.id = p.problem_set_id
           WHERE a.user_id = %(uid)s AND NOT a.passed AND s.cohort_id = %(cid)s
             AND (s.owner_id IS NULL OR s.owner_id = %(uid)s)""",
        {"uid": uid, "cid": cid},
    ).fetchone()

    def view(s: dict[str, Any]) -> dict[str, Any]:
        return {
            "수업 날짜": _safe(s["lesson_date"]), "출제일": _safe(s["made_on"]),
            "과목": s["source_title"], "제목": s["day_label"] or s["title"],
            "누가 만들었나": "내가 만든 문제" if s["owner_id"] else "수업 복습(자동 출제)",
            "문제 수": s["total"], "통과": s["passed"], "풀어 봄": s["tried"], "남은 문제": s["total"] - s["passed"],
        }

    recent = [view(s) for s in sets]
    return {
        "오늘": today.isoformat(),
        "자동 출제": PRACTICE_AUTO_TIME,
        "오늘 나온 복습 세트": [v for v in recent if today.isoformat() in (v["수업 날짜"], v["출제일"])],
        "최근 복습 세트": recent,
        "다시 풀 문제 수": int((retry or {}).get("n") or 0),
        "보는 곳": "학습실 › 공부방 — 오늘 복습 카드 · 과목별 목록, 틀린 문제는 「다시 풀 문제」",
    }


def _resume_pack(cur, cid: int, user_id: int) -> dict[str, Any]:
    docs = list(cur.execute(
        "SELECT * FROM resumes WHERE cohort_id = %s AND user_id = %s LIMIT 6",
        (cid, user_id),
    ))
    items = []
    for resume in docs[:5]:
        item = _row(resume) or {}
        rid = resume["id"]
        item["feedback"] = _rows(list(cur.execute(
            "SELECT * FROM resume_feedback WHERE resume_id = %s LIMIT 10", (rid,)
        )))
        item["revisions"] = _rows(list(cur.execute(
            "SELECT * FROM resume_revisions WHERE resume_id = %s LIMIT 10", (rid,)
        )))
        items.append(item)
    return {"items": items, "truncated": len(docs) > 5}


def _youtube_cache(code: str) -> dict[str, Any]:
    try:
        client = _redis()
        keys = list(client.scan_iter(match=f"curriculum:yt:{code}:*", count=50))
        items = []
        for key in keys[:MAX_DOCS]:
            raw = client.get(key)
            if not raw:
                continue
            payload = json.loads(raw)
            payload["id"] = key.rsplit(":", 1)[-1]
            items.append(_safe(payload))
        return {"items": items, "truncated": len(keys) > MAX_DOCS}
    except Exception as exc:
        return {"items": [], "truncated": False, "unavailable_reason": type(exc).__name__}


def _cohort_shared(cur, cid: int, code: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    errors: dict[str, str] = {}
    tables = {
        "schedules": "SELECT * FROM schedules WHERE cohort_id = %s LIMIT %s",
        "alert_popups": "SELECT * FROM alert_popups WHERE cohort_id = %s LIMIT %s",
        "materials": "SELECT * FROM materials WHERE cohort_id = %s LIMIT %s",
        "mileage_products": "SELECT * FROM mileage_products WHERE cohort_id = %s LIMIT %s",
        "inflearn_packages": "SELECT * FROM inflearn_packages WHERE cohort_id = %s LIMIT %s",
        "youtube_recommendations": "SELECT * FROM youtube_recommendations WHERE cohort_id = %s LIMIT %s",
    }
    _put(result, errors, "cohort", lambda: _row(cur.execute("SELECT * FROM cohorts WHERE id = %s", (cid,)).fetchone(), "code"))
    for key, sql in tables.items():
        _put(result, errors, key, lambda sql=sql: _rows(list(cur.execute(sql, (cid, MAX_DOCS + 1)))))
    _put(result, errors, "youtube_curriculum_cache", lambda: _youtube_cache(code))
    _put(
        result, errors, "form_tasks",
        lambda: _rows(list(cur.execute(
            """SELECT st.* FROM submission_tasks st
               JOIN submission_task_cohorts sc ON sc.task_id = st.id
               WHERE sc.cohort_id = %s AND st.published = true LIMIT %s""",
            (cid, MAX_DOCS + 1),
        ))),
    )
    _put(
        result, errors, "assessments",
        lambda: _rows(list(cur.execute(
            "SELECT id, legacy_id, cohort_id, title, tags, max_score, start_at, end_at, thumbnail_storage_key, published, created_at, updated_at "
            "FROM assessments WHERE cohort_id = %s AND published = true LIMIT %s",
            (cid, MAX_DOCS + 1),
        ))),
    )
    _put(
        result, errors, "mileage_settings",
        lambda: _row(cur.execute(
            "SELECT * FROM mileage_settings WHERE cohort_id = %s", (cid,)
        ).fetchone(), "cohort_id"),
    )
    _put(
        result, errors, "curriculum",
        lambda: (
            snapshot if (snapshot := _row(cur.execute(
                "SELECT * FROM curriculum_pdfs WHERE cohort_id = %s AND published = true", (cid,)
            ).fetchone(), "cohort_id"))
            else None
        ),
    )
    _put(
        result, errors, "system_cache",
        lambda: _rows(list(cur.execute("SELECT * FROM system_cache LIMIT %s", (MAX_DOCS + 1,))), id_key="key"),
    )
    _put(result, errors, "seating", lambda: _seating(cur, cid))
    if errors:
        result["errors"] = errors
    return result


def _seating(cur, cid: int) -> dict[str, Any]:
    row = cur.execute(
        "SELECT layout FROM cohort_seating WHERE cohort_id = %s AND published = true", (cid,)
    ).fetchone()
    if not row:
        return {"published": False, "layout": None}
    layout = row["layout"]
    if isinstance(layout, str):
        layout = json.loads(layout)
    return {"published": True, "layout": _safe(layout)}


def _file_text(name: str, data: bytes) -> str:
    if len(data) > MAX_FILE_BYTES:
        return ""
    lower = name.lower()
    if lower.endswith(".pdf"):
        from pypdf import PdfReader

        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(data)).pages)
    elif lower.endswith((".txt", ".md", ".csv", ".json")):
        text = data.decode("utf-8", errors="replace")
    else:
        return ""
    return text[:MAX_FILE_TEXT]


def _s3_files(prefix: str, query: str, uid: str = "") -> dict[str, Any]:
    bucket = os.environ.get("AWS_S3_BUCKET") or os.environ.get("S3_BUCKET")
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if not bucket or not region:
        return {"items": [], "truncated": False, "unavailable_reason": "S3 configuration missing"}
    try:
        import boto3

        client = boto3.client(
            "s3",
            region_name=region,
        )
    except Exception as exc:
        return {"items": [], "truncated": False, "unavailable_reason": type(exc).__name__}
    blobs = []
    token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 200}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents") or []:
            key = obj["Key"]
            if key.endswith("/"):
                continue
            if uid and f"/submissions/{uid}/" not in key:
                continue
            blobs.append(obj)
            if len(blobs) > MAX_FILES:
                break
        if len(blobs) > MAX_FILES or not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    words = {word.lower() for word in re.findall(r"[0-9A-Za-z가-힣]{2,}", query)}
    blobs.sort(
        key=lambda obj: (
            sum(word in obj["Key"].lower() for word in words),
            str(obj.get("LastModified") or ""),
        ),
        reverse=True,
    )
    items = []
    for index, obj in enumerate(blobs[:MAX_FILES]):
        item = {
            "path": obj["Key"],
            "name": obj["Key"].rsplit("/", 1)[-1],
            "size": obj.get("Size"),
            "updated": _safe(obj.get("LastModified")),
        }
        if index < MAX_EXTRACTED_FILES:
            try:
                body = client.get_object(Bucket=bucket, Key=obj["Key"])["Body"].read()
                if text := _file_text(obj["Key"], body):
                    item["text_excerpt"] = text
            except Exception as exc:
                item["text_error"] = type(exc).__name__
        items.append(item)
    return {"items": items, "truncated": len(blobs) > MAX_FILES}


def load_student_context(
    *, db: Any = None, bucket: Any = None, uid: str, cohort: str, scopes: list[str], query: str,
) -> dict[str, Any]:
    """student_tools 노드에서 호출하는 학생 범위 조회 진입점. Postgres + Redis + S3."""
    del db, bucket
    selected = list(dict.fromkeys(scope for scope in scopes if scope in ALLOWED_SCOPES))
    data: dict[str, Any] = {}
    errors: dict[str, str] = {}
    with _connect() as conn:
        cur = conn.cursor()
        cid, code = _cohort_ids(cur, cohort)
        user_id = _user_id(cur, uid)
        if cid is None:
            return {
                "cohort": cohort,
                "as_of": datetime.now(KST).isoformat(),
                "requested_scopes": selected,
                "data": {},
                "errors": {"cohort": "not_found"},
            }
        loaders: dict[str, Callable[[], Any]] = {
            "student_private": lambda: _student_private(cur, cid, uid, user_id),
            "cohort_shared": lambda: _cohort_shared(cur, cid, code),
            "curriculum_files": lambda: _s3_files(f"cohorts/{code}/curriculum/", query),
            "material_files": lambda: _s3_files(f"cohorts/{code}/materials/", query),
            "record_files": lambda: _s3_files(f"cohorts/{code}/records/{uid}/", query),
            "assignment_files": lambda: _s3_files(f"cohorts/{code}/assignments/", query, uid),
            "study_room": lambda: _study_room(cur, cid, user_id),
        }
        for scope in selected:
            _put(data, errors, scope, loaders[scope])
    return {
        "cohort": code,
        "as_of": datetime.now(KST).isoformat(),
        "requested_scopes": selected,
        "data": data,
        "errors": errors,
    }


def _self_check() -> None:
    assert _safe({"name": "학생", "initialPassword": "숨김"}) == {"name": "학생"}
    assert parse_schedule_date("2026년 6월 16일", date(2026, 1, 1)) == date(2026, 6, 16)


if __name__ == "__main__":
    _self_check()
