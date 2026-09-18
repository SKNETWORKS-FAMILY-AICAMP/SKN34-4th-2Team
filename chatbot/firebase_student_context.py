"""인증된 학생 범위 안에서 Firestore/Storage 문맥을 조회한다."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Callable

from firebase_admin import firestore

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
}
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


def load_unit_period_context(session: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    db, cohort, uid = session["db"], session["cohort"], session["uid"]
    cohort_data = db.collection("cohorts").document(cohort).get().to_dict() or {}
    start, end = _to_kst_date(cohort_data.get("startDate")), _to_kst_date(cohort_data.get("endDate"))
    if not start or not end:
        return {"unavailable_reason": "기수의 개강일 또는 종강일이 등록되지 않았습니다"}

    scheduled_dates: set[date] = set()
    sheets = list(
        db.collection("cohorts").document(cohort).collection("curriculumSheets")
        .order_by("uploadedAt", direction=firestore.Query.DESCENDING).limit(1).stream()
    )
    if sheets:
        for row in (sheets[0].to_dict() or {}).get("rows", []):
            parsed = parse_schedule_date(str(row.get("dateLabel") or ""), start)
            if parsed and start <= parsed <= end:
                scheduled_dates.add(parsed)

    attendance: dict[date, str] = {}
    records = (
        db.collection("cohorts").document(cohort).collection("attendances")
        .where("userId", "==", uid).stream()
    )
    for document in records:
        data = document.to_dict() or {}
        try:
            day = date.fromisoformat(str(data.get("dateKey") or ""))
        except ValueError:
            continue
        status = str(data.get("status") or ("present" if data.get("type") == "checkIn" else ""))
        if status:
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


def _snapshot(document: Any) -> dict[str, Any] | None:
    if not document.exists:
        return None
    return {"id": document.id, **_safe(document.to_dict() or {})}


def _documents(query: Any, limit: int = MAX_DOCS) -> dict[str, Any]:
    documents = list(query.limit(limit + 1).stream())
    return {
        "items": [_snapshot(document) for document in documents[:limit]],
        "truncated": len(documents) > limit,
    }


def _put(target: dict[str, Any], errors: dict[str, str], key: str, load: Callable[[], Any]) -> None:
    try:
        target[key] = load()
    except Exception as exc:
        errors[key] = type(exc).__name__


def _student_private(db: Any, cohort: str, uid: str) -> dict[str, Any]:
    cohort_ref = db.collection("cohorts").document(cohort)
    user_ref = db.collection("users").document(uid)
    result: dict[str, Any] = {}
    errors: dict[str, str] = {}

    _put(result, errors, "profile", lambda: _snapshot(user_ref.get()))
    _put(result, errors, "todos", lambda: _documents(user_ref.collection("todos")))
    _put(result, errors, "alert_dismissals", lambda: _documents(user_ref.collection("alertPopupDismissals")))
    _put(
        result, errors, "attendances",
        lambda: _documents(cohort_ref.collection("attendances").where("userId", "==", uid)),
    )
    _put(
        result, errors, "submissions",
        lambda: _documents(cohort_ref.collection("submissions").where("userId", "==", uid)),
    )
    _put(
        result, errors, "user_progress",
        lambda: _snapshot(cohort_ref.collection("userProgress").document(uid).get()),
    )
    _put(
        result, errors, "mission_progress",
        lambda: _snapshot(cohort_ref.collection("missionProgress").document(uid).get()),
    )
    _put(
        result, errors, "assessment_submissions",
        lambda: _documents(cohort_ref.collection("assessmentSubmissions").where("userId", "==", uid)),
    )
    def form_responses() -> dict[str, Any]:
        tasks = list(cohort_ref.collection("formTasks").limit(MAX_DOCS + 1).stream())
        items = []
        for task in tasks[:MAX_DOCS]:
            response = task.reference.collection("responses").document(uid).get()
            if response.exists:
                items.append({"taskId": task.id, **(_snapshot(response) or {})})
        return {"items": items, "truncated": len(tasks) > MAX_DOCS}

    def assignment_submissions() -> dict[str, Any]:
        items = []
        assignments = list(cohort_ref.collection("assignments").limit(MAX_DOCS + 1).stream())
        for assignment in assignments[:MAX_DOCS]:
            submission = assignment.reference.collection("submissions").document(uid).get()
            if submission.exists:
                items.append({"assignmentId": assignment.id, **(_snapshot(submission) or {})})
        return {"items": items, "truncated": len(assignments) > MAX_DOCS}

    def qna_threads() -> dict[str, Any]:
        threads = list(cohort_ref.collection("qna").where("studentId", "==", uid).limit(MAX_DOCS + 1).stream())
        items = []
        for thread in threads[:MAX_DOCS]:
            item = _snapshot(thread) or {}
            item["messages"] = _documents(thread.reference.collection("messages"), 10)
            items.append(item)
        return {"items": items, "truncated": len(threads) > MAX_DOCS}

    def resumes() -> dict[str, Any]:
        docs = list(cohort_ref.collection("resumes").where("userId", "==", uid).limit(6).stream())
        items = []
        for resume in docs[:5]:
            item = _snapshot(resume) or {}
            item["feedback"] = _documents(resume.reference.collection("feedback"), 10)
            item["revisions"] = _documents(resume.reference.collection("revisions"), 10)
            items.append(item)
        return {"items": items, "truncated": len(docs) > 5}

    def mileage() -> dict[str, Any]:
        return {
            "transactions": _documents(cohort_ref.collection("mileageTransactions").where("userId", "==", uid)),
            "purchase_requests": _documents(cohort_ref.collection("purchaseRequests").where("userId", "==", uid)),
            "cart": _snapshot(cohort_ref.collection("mileageCart").document(uid).get()),
        }

    _put(result, errors, "form_responses", form_responses)
    _put(result, errors, "assignment_submissions", assignment_submissions)
    _put(result, errors, "qna", qna_threads)
    _put(result, errors, "resumes", resumes)
    _put(result, errors, "mileage", mileage)
    _put(
        result, errors, "unit_period_context",
        lambda: load_unit_period_context({"db": db, "cohort": cohort, "uid": uid}),
    )
    if errors:
        result["errors"] = errors
    return result


def _cohort_shared(db: Any, cohort: str) -> dict[str, Any]:
    cohort_ref = db.collection("cohorts").document(cohort)
    result: dict[str, Any] = {}
    errors: dict[str, str] = {}
    collections = {
        "schedules": "schedules",
        "alert_popups": "alertPopups",
        "materials": "materials",
        "assignments": "assignments",
        "mileage_products": "mileageProducts",
        "weekly_tasks": "weeklyTasks",
        "inflearn_packages": "inflearnPackages",
        "youtube_recommendations": "youtubeRecommendations",
        "youtube_curriculum_cache": "youtubeCurriculumCache",
    }
    _put(result, errors, "cohort", lambda: _snapshot(cohort_ref.get()))
    for key, collection in collections.items():
        _put(result, errors, key, lambda collection=collection: _documents(cohort_ref.collection(collection)))

    def posts() -> dict[str, Any]:
        docs = list(cohort_ref.collection("posts").limit(MAX_DOCS + 1).stream())
        items = []
        for post in docs[:MAX_DOCS]:
            item = _snapshot(post) or {}
            item["comments"] = _documents(post.reference.collection("comments"), 10)
            items.append(item)
        return {"items": items, "truncated": len(docs) > MAX_DOCS}

    _put(result, errors, "posts", posts)
    _put(
        result, errors, "form_tasks",
        lambda: _documents(cohort_ref.collection("formTasks").where("published", "==", True)),
    )
    _put(
        result, errors, "assessments",
        lambda: _documents(cohort_ref.collection("assessments").where("published", "==", True)),
    )
    _put(
        result, errors, "mileage_settings",
        lambda: _snapshot(cohort_ref.collection("mileageSettings").document("config").get()),
    )
    _put(
        result, errors, "curriculum",
        lambda: (
            snapshot if (snapshot := _snapshot(cohort_ref.collection("curriculum").document("meta").get()))
            and snapshot.get("published") is True else None
        ),
    )
    _put(result, errors, "system_cache", lambda: _documents(db.collection("systemCache")))

    def seating() -> dict[str, Any]:
        seating_ref = cohort_ref.collection("seating")
        meta = _snapshot(cohort_ref.collection("seatingMeta").document("default").get())
        room_id = str((meta or {}).get("publishedRoomId") or "")
        assignment = (
            _snapshot(cohort_ref.collection("seatingAssignments").document(room_id).get())
            if room_id else None
        )
        legacy_assignment = _snapshot(seating_ref.document("assignment").get())
        published = (assignment or {}).get("status") == "published"
        legacy_published = (legacy_assignment or {}).get("status") == "published"
        return {
            "meta": meta,
            "room": _snapshot(cohort_ref.collection("seatingRooms").document(room_id).get()) if published else None,
            "assignment": assignment if published else None,
            "legacy_assignment": legacy_assignment if legacy_published else None,
            "legacy_layout": _snapshot(seating_ref.document("layout").get()) if legacy_published else None,
        }

    _put(result, errors, "seating", seating)
    if errors:
        result["errors"] = errors
    return result


def _file_text(blob: Any) -> str:
    size = int(blob.size or 0)
    if size > MAX_FILE_BYTES:
        return ""
    data = blob.download_as_bytes()
    name = blob.name.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(data)).pages)
    elif name.endswith((".txt", ".md", ".csv", ".json")):
        text = data.decode("utf-8", errors="replace")
    else:
        return ""
    return text[:MAX_FILE_TEXT]


def _storage_files(bucket: Any, prefix: str, query: str, uid: str = "") -> dict[str, Any]:
    if bucket is None:
        return {"items": [], "truncated": False, "unavailable_reason": "Storage bucket 미설정"}
    blobs = []
    options = {} if uid else {"max_results": MAX_FILES + 1}
    for blob in bucket.list_blobs(prefix=prefix, **options):
        if blob.name.endswith("/") or (uid and f"/submissions/{uid}/" not in blob.name):
            continue
        blobs.append(blob)
        if len(blobs) > MAX_FILES:
            break
    words = {word.lower() for word in re.findall(r"[0-9A-Za-z가-힣]{2,}", query)}
    blobs.sort(
        key=lambda blob: (
            sum(word in blob.name.lower() for word in words),
            str(blob.updated or ""),
        ),
        reverse=True,
    )
    items = []
    for index, blob in enumerate(blobs[:MAX_FILES]):
        item = {
            "path": blob.name,
            "name": blob.name.rsplit("/", 1)[-1],
            "size": blob.size,
            "content_type": blob.content_type,
            "updated": _safe(blob.updated),
        }
        if index < MAX_EXTRACTED_FILES:
            try:
                if text := _file_text(blob):
                    item["text_excerpt"] = text
            except Exception as exc:
                item["text_error"] = type(exc).__name__
        items.append(item)
    # ponytail: 질문당 파일 30개/본문 5개 상한이며 과제 파일은 prefix를 순차 탐색한다;
    # 목록 지연이 관측되면 assignmentId별 prefix 인덱스로 교체.
    return {"items": items, "truncated": len(blobs) > MAX_FILES}


def load_student_context(
    *, db: Any, bucket: Any, uid: str, cohort: str, scopes: list[str], query: str,
) -> dict[str, Any]:
    """student_tools 노드에서 호출하는 학생 범위 조회 진입점."""
    selected = list(dict.fromkeys(scope for scope in scopes if scope in ALLOWED_SCOPES))
    data: dict[str, Any] = {}
    errors: dict[str, str] = {}
    loaders: dict[str, Callable[[], Any]] = {
        "student_private": lambda: _student_private(db, cohort, uid),
        "cohort_shared": lambda: _cohort_shared(db, cohort),
        "curriculum_files": lambda: _storage_files(bucket, f"cohorts/{cohort}/curriculum/", query),
        "material_files": lambda: _storage_files(bucket, f"cohorts/{cohort}/materials/", query),
        "record_files": lambda: _storage_files(bucket, f"cohorts/{cohort}/records/{uid}/", query),
        "assignment_files": lambda: _storage_files(
            bucket, f"cohorts/{cohort}/assignments/", query, uid,
        ),
    }
    for scope in selected:
        _put(data, errors, scope, loaders[scope])
    return {
        "cohort": cohort,
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
