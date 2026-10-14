"""폴더 올리기(GitHub 없이) — Django 쪽. 강사가 올린 수업 파일을 AI 서버의 「서버 안 git 저장소」에 넣는다.

AI 서버(study_notes/upload_plan.py · upload_repo.py)가 계획과 커밋을 한다. 여기서는
- 권한(강사는 자기 기수, 관리자는 모든 기수 — 수업 저장소 관리와 같다)
- 기수 달력: 기간 · 공휴일(lms/holidays.py) · 커리큘럼(curriculum_rows, 날짜를 읽은 줄만). 커리큘럼 · 공휴일은 힌트일 뿐이라
  AI 서버가 막지 않고 묻는다
- 과목 만들기: study_sources 에 repo_url = upload://<기수>/<과목> (테이블은 그대로)
- 보관: 올릴 때마다 저장소 전체(git bundle)를 S3(lms.storage)에 둔다. AI 서버를 새로 띄워 저장소가 사라졌으면
  그 과목을 쓰는 AI 호출 앞에서 보관본으로 되살린다(ensure_repo — study_note_service._call 이 부른다)
- 일정 어긋남: 실제로 문제를 낸 수업 날짜 ↔ 커리큘럼(강사 · 관리자 수업 저장소 화면)

화면은 한 번에 파일 100개까지 보낸다(Django DATA_UPLOAD_MAX_NUMBER_FILES). 처음 가져오기처럼 많으면 나눠서 여러 번 부른다 —
같은 날짜를 두 번 올려도 그날 커밋이 둘일 뿐 「그날 파일」은 같다.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import threading
import time
from datetime import date, timedelta
from typing import Any

from django.db import connection, transaction
from django.utils import timezone

from lms import storage
from lms.external_feeds import _curriculum_rows, _label_date
from lms.holidays import holidays_of
from lms.study_note_service import StudyNoteError, _dicts, _one, _post, _public_id, _source_payload
from lms.study_source_service import SAME_REPO_SQL, StudySourceError, _cohort, _repo_key

logger = logging.getLogger(__name__)

PLAN_TIMEOUT = 90
COMMIT_TIMEOUT = 300
CHECK_TIMEOUT = 30
RESTORE_TIMEOUT = 180
MAX_FILES = 100
MAX_REQUEST_BYTES = 60 * 1024 * 1024
# 과목 이름 — 폴더 이름 그대로(한글 · 공백 가능). 저장소 주소의 한 칸이라 / \ 와 .. 는 안 된다
NAME_RE = re.compile(r"^(?!\.)[^/\\\x00-\x1f]{1,80}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# 서버 안 저장소가 있는지 이 시간 안에 이미 봤으면 다시 묻지 않는다
CHECK_EVERY = 600.0
_checked: dict[str, float] = {}
_check_lock = threading.Lock()


def upload_url(cohort_code: str, name: str) -> str:
    return f"upload://{cohort_code}/{name}"


def is_upload(repo_url: str | None) -> bool:
    return str(repo_url or "").startswith("upload://")


def bundle_key(cohort_code: str, source_id: str) -> str:
    return f"study-uploads/{cohort_code}/{source_id}.bundle"


def _subject_name(row: dict) -> str:
    """계획이 과목을 견주는 이름 — 폴더 올리기는 주소의 과목 칸, GitHub 은 저장소 이름(화면 제목은 바꿀 수 있어 안 쓴다)"""
    url = str(row.get("repo_url") or "")
    if is_upload(url):
        return url.split("/", 3)[-1]
    return _repo_key(url).rsplit("/", 1)[-1]


# ── 보관본으로 되살리기 ─────────────────────────────────────────────


def ensure_repo(cohort_code: str, source: dict, *, force: bool = False) -> None:
    """폴더 올리기 과목이면 AI 서버에 저장소가 있는지 보고, 없으면 S3 보관본으로 되살린다. GitHub 과목은 아무것도 안 한다.
    source — AI 로 보내는 모양(_source_payload). 실패해도 막지 않는다 — 읽는 호출은 「빈 저장소」로 알리고,
    올리기는 AI 서버가 저장소 없는 커밋을 거절한다(409). force — 10분 안에 봤어도 다시 본다(올리기 · 오늘 수업 계획)."""
    if not is_upload(source.get("repoUrl")):
        return
    key = f"{cohort_code}:{source.get('id')}"
    with _check_lock:
        if not force and time.monotonic() - _checked.get(key, -CHECK_EVERY) < CHECK_EVERY:
            return
    body = {"cohortId": cohort_code, "source": source}
    try:
        if _post("/proxy/upload/head", body, CHECK_TIMEOUT).get("head") is None:
            data = storage.get_object(bundle_key(cohort_code, str(source.get("id"))))
            if data:
                _post("/proxy/upload/restore", {**body, "bundle": base64.b64encode(data).decode()}, RESTORE_TIMEOUT)
                logger.info("restored upload repo %s", key)
    except (StudyNoteError, OSError, ValueError):
        logger.exception("upload repo check failed: %s", key)
        return
    with _check_lock:
        _checked[key] = time.monotonic()


def forget(cohort_code: str, source_id: str) -> None:
    with _check_lock:
        _checked.pop(f"{cohort_code}:{source_id}", None)


# ── 기수 달력 ───────────────────────────────────────────────────────


def calendar(cur, cohort: dict, *, extra_days: list[str] | None = None, today: date | None = None) -> dict:
    """AI 서버 계획에 붙이는 달력 — 기간 · 공휴일 · 커리큘럼(날짜를 읽은 줄만, 못 읽은 줄 수)"""
    today = today or timezone.localdate()
    cur.execute("SELECT start_date, end_date FROM cohorts WHERE id = %s", [cohort["id"]])
    row = _one(cur) or {}
    start = row.get("start_date") or today - timedelta(days=365)
    end = row.get("end_date") or today + timedelta(days=365)
    holidays: dict[str, str] = {}
    for year in range(start.year, end.year + 1):
        holidays.update(holidays_of(year))
    curriculum, unreadable = [], 0
    for r in _curriculum_rows(cur, cohort["id"]) or []:
        day = _label_date(r.get("date_label") or "")
        topic = (r.get("topic") or r.get("subject") or "").strip()
        if day is None:
            unreadable += 1 if (r.get("date_label") or "").strip() else 0
            continue
        if topic:
            curriculum.append({"date": day.isoformat(), "topic": topic, "unit": (r.get("subject") or "").strip()})
    return {
        "today": today.isoformat(),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "holidays": holidays,
        "curriculum": curriculum,
        "unreadable": unreadable,
        "extraDays": [d for d in extra_days or [] if DATE_RE.match(str(d))][:100],
    }


def _sources(cur, cohort_id: int) -> list[dict]:
    cur.execute("SELECT * FROM study_sources WHERE cohort_id = %s ORDER BY sort_order NULLS LAST, id", [cohort_id])
    out = []
    for row in _dicts(cur):
        payload = _source_payload(row)
        payload["title"] = _subject_name(row)
        payload["kind"] = "upload" if is_upload(row.get("repo_url")) else "github"
        out.append(payload)
    return out


# ── 계획 ────────────────────────────────────────────────────────────


def plan(user: dict, body: dict) -> dict:
    """올리기 전 계획 — 파일 목록(내용 없음)을 AI 서버에 넘긴다. 처음 가져오기(import) · 오늘 수업 올리기(daily)"""
    mode = body.get("mode")
    if mode not in ("import", "daily"):
        raise StudySourceError(422, "mode 는 import · daily 중 하나예요.")
    files = body.get("files") or []
    if not isinstance(files, list) or not files:
        raise StudySourceError(422, "올릴 파일이 없어요.")
    with connection.cursor() as cur:
        cohort = _cohort(cur, user, str(body.get("cohortId") or ""))
        cal = calendar(cur, cohort, extra_days=body.get("extraDays"))
        sources = _sources(cur, cohort["id"])
    target = str(body.get("target") or "") or None
    if mode == "daily" and not any(s["id"] == target and s["kind"] == "upload" for s in sources):
        raise StudySourceError(404, "폴더로 올린 과목을 골라 주세요.")
    for s in sources:
        if s["kind"] == "upload" and (mode == "import" or s["id"] == target):
            ensure_repo(cohort["code"], s, force=s["id"] == target)
    payload = {
        "cohortId": cohort["code"],
        "mode": mode,
        "what": body.get("what") or None,
        "date": body.get("date") or None,
        "target": target,
        "files": files,
        "sources": sources,
        "topics": body.get("topics") or {},
        "starts": body.get("starts") or {},
        "calendar": cal,
    }
    try:
        return _post("/proxy/upload/plan", payload, PLAN_TIMEOUT)
    except StudyNoteError as exc:
        raise StudySourceError(exc.status, exc.detail) from exc


# ── 올리기(커밋) ─────────────────────────────────────────────────────


def _manifest(raw: str, count: int) -> tuple[list[str], dict[str, list[int]], list[int]]:
    """{"paths": [파일마다 저장소 안 경로], "days": [{"date", "files": [번호]}], "past": [번호]} — 번호는 보낸 파일 순서"""
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise StudySourceError(422, "올리기 목록(manifest)을 읽지 못했어요.") from exc
    paths = [str(p) for p in data.get("paths") or []]
    if len(paths) != count:
        raise StudySourceError(422, "파일 수와 경로 수가 달라요.")
    days: dict[str, list[int]] = {}
    for item in data.get("days") or []:
        day = str(item.get("date") or "")
        if not DATE_RE.match(day):
            raise StudySourceError(422, f"수업 날짜가 올바르지 않아요: {day}")
        days.setdefault(day, []).extend(int(i) for i in item.get("files") or [])
    past = [int(i) for i in data.get("past") or []]
    used = [i for ids in days.values() for i in ids] + past
    if any(i < 0 or i >= count for i in used):
        raise StudySourceError(422, "올리기 목록의 파일 번호가 올바르지 않아요.")
    return paths, days, past


def _new_source(cur, cohort: dict, name: str) -> dict:
    """폴더 올리기 과목을 만든다. 같은 이름의 폴더 과목이 있으면 그것, GitHub 과목과 같은 이름이면 막는다
    (복습 문제 · 출제 기록이 저장소 이름으로 묶여 있어 섞인다 — 폴더 이름을 바꿔 올리게 한다)"""
    if not NAME_RE.match(name) or ".." in name:
        raise StudySourceError(422, "과목 이름(폴더 이름)이 올바르지 않아요.")
    url = upload_url(cohort["code"], name)
    cur.execute(f"SELECT * FROM study_sources WHERE cohort_id = %s AND {SAME_REPO_SQL} = %s", [cohort["id"], _repo_key(url)])
    row = _one(cur)
    if row:
        return row
    cur.execute("SELECT repo_url FROM study_sources WHERE cohort_id = %s", [cohort["id"]])
    if any(_subject_name({"repo_url": r["repo_url"]}).lower() == name.lower() for r in _dicts(cur)):
        raise StudySourceError(409, f"「{name}」은 GitHub로 연결된 과목과 이름이 같아요. 폴더 이름을 바꿔 다시 올려 주세요.")
    cur.execute("SELECT COALESCE(max(sort_order), 0) AS n FROM study_sources WHERE cohort_id = %s", [cohort["id"]])
    order = (_one(cur)["n"] or 0) + 1
    cur.execute(
        """INSERT INTO study_sources (cohort_id, title, repo_url, branch, allowed_prefixes, is_active,
                                      sort_order, created_at, updated_at)
           VALUES (%s, %s, %s, 'main', '{}', true, %s, now(), now()) RETURNING *""",
        [cohort["id"], name, url, order],
    )
    return _one(cur)


def commit(user: dict, *, cohort_code: str, source_key: str, name: str, manifest: str, files: list) -> dict:
    """확정한 파일을 올린다. source_key 가 있으면 그 과목에, 없으면 name 으로 과목을 만든다(이미 있으면 그 과목).
    files — 화면이 보낸 파일(UploadedFile) 순서대로, manifest 가 경로 · 날짜를 적는다."""
    if not files:
        raise StudySourceError(422, "올릴 파일이 없어요.")
    if len(files) > MAX_FILES:
        raise StudySourceError(413, f"한 번에 {MAX_FILES}개까지 올릴 수 있어요. 나눠서 올려 주세요.")
    paths, days, past = _manifest(manifest, len(files))
    if days and max(days) > timezone.localdate().isoformat():
        raise StudySourceError(400, "앞으로 올 날짜로는 올릴 수 없어요.")
    bodies: list[bytes] = []
    total = 0
    for f in files:
        data = f.read()
        total += len(data)
        if total > MAX_REQUEST_BYTES:
            raise StudySourceError(413, "한 번에 보내는 파일이 너무 커요. 나눠서 올려 주세요.")
        bodies.append(data)
    created = False
    with transaction.atomic(), connection.cursor() as cur:
        cohort = _cohort(cur, user, cohort_code)
        if source_key:
            cur.execute(
                "SELECT * FROM study_sources WHERE cohort_id = %s AND (legacy_id = %s OR id::text = %s)",
                [cohort["id"], source_key, source_key],
            )
            source = _one(cur)
            if not source:
                raise StudySourceError(404, "과목을 찾을 수 없어요.")
            if not is_upload(source["repo_url"]):
                raise StudySourceError(400, "GitHub로 연결된 과목에는 올릴 수 없어요.")
        else:
            cur.execute("SELECT count(*) AS n FROM study_sources WHERE cohort_id = %s", [cohort["id"]])
            before = _one(cur)["n"]
            source = _new_source(cur, cohort, (name or "").strip())
            cur.execute("SELECT count(*) AS n FROM study_sources WHERE cohort_id = %s", [cohort["id"]])
            created = _one(cur)["n"] > before
    payload_source = _source_payload(source)
    code = cohort["code"]

    def pack(ids: list[int]) -> list[dict]:
        return [{"path": paths[i], "content": base64.b64encode(bodies[i]).decode()} for i in dict.fromkeys(ids)]

    body = {"cohortId": code, "source": payload_source,
            "days": [{"date": d, "files": pack(ids)} for d, ids in sorted(days.items()) if ids],
            "past": pack(past), "create": created}
    # 올리기 앞에선 꼭 다시 본다 — 그 사이 AI 서버를 새로 띄웠으면 보관본으로 되살린 뒤에 이어 커밋해야 기록이 이어진다
    ensure_repo(code, payload_source, force=True)
    try:
        try:
            result = _post("/proxy/upload/commit", body, COMMIT_TIMEOUT)
        except StudyNoteError as exc:
            if exc.status != 409 or created:
                raise
            # 저장소가 없고 되살리지도 못했다. 보관본이 있으면 멈춘다(빈 저장소로 시작하면 보관본이 덮여 기록을 잃는다).
            # 보관본이 아예 없으면(첫 보관이 실패했던 과목) 잃을 것이 없으니 새로 시작한다
            if storage.get_object(bundle_key(code, _public_id(source))) is not None:
                raise StudySourceError(503, "보관해 둔 수업 자료로 저장소를 되살리지 못했어요. 잠시 뒤 다시 올려 주세요.") from exc
            result = _post("/proxy/upload/commit", {**body, "create": True}, COMMIT_TIMEOUT)
    except StudyNoteError as exc:
        if created:
            with connection.cursor() as cur:
                cur.execute("DELETE FROM study_sources WHERE id = %s", [source["id"]])
        raise StudySourceError(exc.status, exc.detail) from exc
    if result.get("bundle"):
        try:
            storage.put_object(bundle_key(code, _public_id(source)), base64.b64decode(result["bundle"]), "application/octet-stream")
        except Exception:  # noqa: BLE001 — 올리기는 끝났다. 보관만 못 했으니 다음 올리기 때 다시 보관한다
            logger.exception("upload bundle save failed: %s", source["id"])
    with connection.cursor() as cur:
        cur.execute("UPDATE study_sources SET updated_at = now() WHERE id = %s", [source["id"]])
    forget(code, _public_id(source))
    return {
        "source": {"id": _public_id(source), "title": source["title"], "repoUrl": source["repo_url"], "created": created},
        "commits": result.get("commits") or [],
        "head": result.get("head"),
    }


# ── 일정 어긋남 ─────────────────────────────────────────────────────


def schedule(user: dict, cohort_code: str) -> dict:
    """커리큘럼 ↔ 실제 수업 날짜(문제를 낸 날). 커리큘럼이 틀렸을 수도, 실제가 밀렸을 수도 있어 어긋난 것만 보여 준다."""
    with connection.cursor() as cur:
        cohort = _cohort(cur, user, cohort_code)
        cal = calendar(cur, cohort)
        cur.execute(
            """SELECT source_title, array_agg(DISTINCT lesson_date::text ORDER BY lesson_date::text) AS dates
               FROM practice_sets WHERE cohort_id = %s AND owner_id IS NULL AND lesson_date IS NOT NULL
               GROUP BY source_title""",
            [cohort["id"]],
        )
        subjects = {r["source_title"]: {"dates": list(r["dates"] or [])} for r in _dicts(cur)}
    if not cal["curriculum"]:
        return {"cohortId": cohort["code"], "issues": [], "topics": [], "message": "업로드된 커리큘럼이 없어요."}
    try:
        out = _post("/proxy/upload/schedule", {"calendar": cal, "subjects": subjects}, PLAN_TIMEOUT)
    except StudyNoteError as exc:
        raise StudySourceError(exc.status, exc.detail) from exc
    return {"cohortId": cohort["code"], **out}
