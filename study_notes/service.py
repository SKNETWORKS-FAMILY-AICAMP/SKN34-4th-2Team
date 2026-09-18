"""Firestore 소스/노트 문서를 다루는 공부방 서비스.

    cohorts/{cohortId}/studySources/{sourceId}   관리자가 등록한 수업 저장소 (기수 공용)
    users/{uid}/studyNotes/{noteId}              학생이 만든 개인 노트
"""

from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import HTTPException
from google.cloud import firestore as gcf
from google.cloud.firestore import Client, DocumentReference

from study_notes.git_tools import (
    GitToolError,
    RepoCache,
    is_learning_file,
    notebook_to_text,
    parse_repo_url,
    path_allowed,
    sanitize_branch,
    sanitize_path,
)
from study_notes.pipeline import MAX_CHARS_PER_FILE, Material, generate_study_note

ScopeType = Literal["date", "prefix", "files"]
MAX_FILES = 8
GENERATING_LOCK = timedelta(minutes=10)


@dataclass(frozen=True)
class Caller:
    uid: str
    role: str
    cohort_id: str | None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


@dataclass(frozen=True)
class StudySource:
    id: str
    title: str
    repo_url: str
    branch: str
    allowed_prefixes: list[str]


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail=message)


# ── 권한 ────────────────────────────────────────────────────────────


def load_caller(db: Client, uid: str) -> Caller:
    snap = db.collection("users").document(uid).get()
    if not snap.exists:
        raise HTTPException(status_code=403, detail="사용자 정보를 찾을 수 없습니다.")
    data = snap.to_dict() or {}
    if data.get("isActive") is False:
        raise HTTPException(status_code=403, detail="비활성 계정입니다.")
    cohort = data.get("cohortId")
    return Caller(uid=uid, role=str(data.get("role") or ""), cohort_id=str(cohort) if cohort else None)


def assert_cohort_access(caller: Caller, cohort_id: str) -> None:
    if caller.is_admin or caller.cohort_id == cohort_id:
        return
    raise HTTPException(status_code=403, detail="해당 기수에 접근할 수 없습니다.")


# ── 소스 ────────────────────────────────────────────────────────────


def _normalize_prefixes(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        value = str(item).strip().replace("\\", "/").strip("/")
        if value and ".." not in value:
            out.append(value)
    return out


def load_active_source(db: Client, cohort_id: str, source_id: str) -> StudySource:
    snap = (
        db.collection("cohorts").document(cohort_id)
        .collection("studySources").document(source_id).get()
    )
    if not snap.exists:
        raise HTTPException(status_code=404, detail="공부 소스를 찾을 수 없습니다.")
    data = snap.to_dict() or {}
    if data.get("isActive") is False:
        raise HTTPException(status_code=409, detail="비활성 수업 저장소입니다.")
    repo_url = str(data.get("repoUrl") or "")
    try:
        parse_repo_url(repo_url)
        branch = sanitize_branch(str(data.get("branch") or "main"))
    except GitToolError as exc:
        raise _bad_request(str(exc)) from exc
    return StudySource(
        id=snap.id,
        title=str(data.get("title") or ""),
        repo_url=repo_url,
        branch=branch,
        allowed_prefixes=_normalize_prefixes(data.get("allowedPrefixes")),
    )


def repo_cache(cohort_id: str, source: StudySource) -> RepoCache:
    return RepoCache(cohort_id, source.id, parse_repo_url(source.repo_url), source.branch)


def note_ref(db: Client, uid: str, note_id: str) -> DocumentReference:
    return db.collection("users").document(uid).collection("studyNotes").document(note_id)


# ── 범위(scope) ─────────────────────────────────────────────────────


def parse_scope_type(raw: str) -> ScopeType:
    if raw in ("date", "prefix", "files"):
        return raw  # type: ignore[return-value]
    raise _bad_request("scopeType은 date, prefix, files만 가능합니다.")


def normalize_scope_value(scope_type: ScopeType, raw: Any) -> str | list[str]:
    try:
        if scope_type == "files":
            if not isinstance(raw, list) or not raw:
                raise _bad_request("파일을 1개 이상 선택하세요.")
            if len(raw) > MAX_FILES:
                raise _bad_request(f"한 번에 최대 {MAX_FILES}개 파일만 정리할 수 있습니다. 범위를 좁혀 주세요.")
            paths = sorted({sanitize_path(str(item)) for item in raw})
            return paths
        value = str(raw or "").strip()
        if not value:
            raise _bad_request("범위를 선택하세요.")
        if scope_type == "date":
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise _bad_request("날짜는 YYYY-MM-DD 형식이어야 합니다.")
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError as exc:
                raise _bad_request("존재하지 않는 날짜입니다.") from exc
            return value
        return sanitize_path(value).rstrip("/")
    except GitToolError as exc:
        raise _bad_request(str(exc)) from exc


def _assert_prefix_allowed(allowed: list[str], path: str) -> None:
    if not path_allowed(path.rstrip("/"), allowed):
        raise _bad_request("허용된 폴더 밖의 경로는 정리할 수 없습니다.")


def assert_scope_allowed(source: StudySource, scope_type: ScopeType, value: str | list[str]) -> None:
    if scope_type == "prefix":
        _assert_prefix_allowed(source.allowed_prefixes, str(value))
    elif scope_type == "files":
        for path in value:  # type: ignore[union-attr]
            if not is_learning_file(path):
                raise _bad_request("분석 가능한 파일은 .ipynb, .py, .md 뿐입니다.")
            _assert_prefix_allowed(source.allowed_prefixes, path)


def build_scope_key(scope_type: ScopeType, value: str | list[str]) -> str:
    if scope_type == "date":
        return str(value)
    if scope_type == "prefix":
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("_")[:80]
        return f"prefix_{safe or 'root'}"
    digest = hashlib.sha1("\n".join(value).encode("utf-8")).hexdigest()[:12]  # type: ignore[arg-type]
    return f"files_{digest}"


def build_note_id(source_id: str, scope_type: ScopeType, value: str | list[str]) -> str:
    safe_source = re.sub(r"[/\s]", "_", source_id)
    return f"{safe_source}_{build_scope_key(scope_type, value)}"


def scope_label(scope_type: ScopeType, value: str | list[str]) -> str:
    if scope_type == "date":
        return f"{value} 수업"
    if scope_type == "prefix":
        return f"폴더 {value}"
    names = [str(path).rsplit("/", 1)[-1] for path in value]  # type: ignore[union-attr]
    return "파일 " + ", ".join(names)


# ── 직렬화 ──────────────────────────────────────────────────────────


def serialize_note(note_id: str, data: dict[str, Any], caller: Caller) -> dict[str, Any]:
    status = str(data.get("status") or "missing")
    base = {
        "noteId": note_id,
        "status": status,
        "sourceId": data.get("sourceId") or "",
        "scopeType": data.get("scopeType"),
        "scopeValue": data.get("scopeValue"),
        "errorMessage": data.get("errorMessage"),
    }
    if status == "ready":
        return {
            **base,
            "reportMarkdown": str(data.get("reportMarkdown") or ""),
            "reviewMarkdown": str(data.get("reviewMarkdown") or ""),
            "files": data.get("files") or [],
        }
    if status == "generating":
        return {**base, "message": "정리 중입니다."}
    return base


# ── 조회 ────────────────────────────────────────────────────────────


def list_source_tree(db: Client, caller: Caller, cohort_id: str, source_id: str) -> dict[str, Any]:
    assert_cohort_access(caller, cohort_id)
    source = load_active_source(db, cohort_id, source_id)
    cache = repo_cache(cohort_id, source)
    try:
        cache.sync()
        dates = cache.recent_lesson_dates(source.allowed_prefixes)
        entries = cache.list_tree(source.allowed_prefixes)
    except GitToolError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "dates": dates,
        "entries": [{"path": p, "type": "blob"} for p in entries],
        "truncated": False,
    }


def get_note(
    db: Client,
    caller: Caller,
    cohort_id: str,
    *,
    note_id: str | None,
    source_id: str | None,
    scope_type: str | None,
    scope_value: Any,
) -> dict[str, Any]:
    assert_cohort_access(caller, cohort_id)
    resolved = (note_id or "").strip()
    if not resolved and source_id and scope_type:
        st = parse_scope_type(scope_type)
        resolved = build_note_id(source_id, st, normalize_scope_value(st, scope_value))
    if not resolved:
        raise _bad_request("noteId 또는 sourceId+scope가 필요합니다.")
    snap = note_ref(db, caller.uid, resolved).get()
    if not snap.exists:
        return {"noteId": resolved, "status": "missing"}
    return serialize_note(snap.id, snap.to_dict() or {}, caller)


# ── 생성 ────────────────────────────────────────────────────────────


def _lock_expired(data: dict[str, Any]) -> bool:
    started = data.get("generatingStartedAt")
    if not isinstance(started, datetime):
        return True
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - started > GENERATING_LOCK


def _claim(db: Client, ref: DocumentReference, source: StudySource, scope_type: ScopeType,
           scope_value: str | list[str], scope_key: str, uid: str) -> tuple[str, dict[str, Any]]:
    transaction = db.transaction()

    @gcf.transactional
    def run(tx: gcf.Transaction) -> tuple[str, dict[str, Any]]:
        snap = ref.get(transaction=tx)
        if snap.exists:
            current = snap.to_dict() or {}
            if current.get("status") == "ready":
                return "ready", current
            if current.get("status") == "generating" and not _lock_expired(current):
                return "generating", current
        tx.set(ref, {
            "sourceId": source.id,
            "scopeType": scope_type,
            "scopeValue": scope_value,
            "scopeKey": scope_key,
            "status": "generating",
            "generatingByUid": uid,
            "ownerUid": uid,
            "generatingStartedAt": gcf.SERVER_TIMESTAMP,
            "updatedAt": gcf.SERVER_TIMESTAMP,
            "errorMessage": gcf.DELETE_FIELD,
        }, merge=True)
        return "start", {}

    return run(transaction)


def _collect(cache: RepoCache, source: StudySource, scope_type: ScopeType,
             scope_value: str | list[str]) -> tuple[list[str], list[dict[str, str]], bool]:
    """(commits, files[{path, commit}], too_broad)"""
    head = cache.sync()
    if scope_type == "date":
        shas, changed = cache.changed_files_on(str(scope_value), source.allowed_prefixes)
        files = [{"path": f.path, "commit": f.commit} for f in changed]
        return shas, files, len(files) > MAX_FILES
    if scope_type == "prefix":
        paths = cache.list_tree([str(scope_value)])
        files = [{"path": p, "commit": head} for p in paths]
        return [head], files, len(files) > MAX_FILES
    files = [{"path": p, "commit": head} for p in scope_value]  # type: ignore[union-attr]
    return [head], files, False


def _load_materials(cache: RepoCache, files: list[dict[str, str]]) -> list[Material]:
    def one(item: dict[str, str]) -> Material:
        raw = cache.read_file(item["commit"], item["path"])
        text = notebook_to_text(raw) if item["path"].lower().endswith(".ipynb") else raw
        return {
            "path": item["path"],
            "commit": item["commit"][:8],
            "content": text[:MAX_CHARS_PER_FILE],
            "truncated": len(text) > MAX_CHARS_PER_FILE,
        }

    workers = min(4, max(1, len(files)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, files))


def generate_note(db: Client, caller: Caller, cohort_id: str, source_id: str,
                  scope_type_raw: str, scope_value_raw: Any) -> dict[str, Any]:
    assert_cohort_access(caller, cohort_id)
    source = load_active_source(db, cohort_id, source_id)
    scope_type = parse_scope_type(scope_type_raw)
    scope_value = normalize_scope_value(scope_type, scope_value_raw)
    assert_scope_allowed(source, scope_type, scope_value)

    scope_key = build_scope_key(scope_type, scope_value)
    note_id = f"{source.id}_{scope_key}"
    ref = note_ref(db, caller.uid, note_id)

    kind, current = _claim(db, ref, source, scope_type, scope_value, scope_key, caller.uid)
    if kind == "ready":
        return serialize_note(note_id, current, caller)
    if kind == "generating":
        return {
            "noteId": note_id,
            "status": "generating",
            "message": "이미 정리 중입니다. 잠시 후 다시 열어 주세요.",
        }

    try:
        cache = repo_cache(cohort_id, source)
        commits, files, too_broad = _collect(cache, source, scope_type, scope_value)
        if too_broad:
            ref.delete()
            return {
                "status": "too_broad",
                "noteId": note_id,
                "message": f"파일을 선택하세요. 한 번에 최대 {MAX_FILES}개까지 정리할 수 있습니다.",
                "files": files,
            }
        if not files:
            raise HTTPException(status_code=404, detail="이 범위에서 분석 가능한 .ipynb/.py/.md 파일이 없습니다.")

        materials = _load_materials(cache, files)
        report, review = generate_study_note(
            scope_label=scope_label(scope_type, scope_value),
            commits=commits,
            materials=materials,
        )
        ref.set({
            "sourceId": source.id,
            "cohortId": cohort_id,
            "ownerUid": caller.uid,
            "scopeType": scope_type,
            "scopeValue": scope_value,
            "scopeKey": scope_key,
            "status": "ready",
            "commits": commits,
            "files": files,
            "reportMarkdown": report,
            "reviewMarkdown": review,
            "errorMessage": gcf.DELETE_FIELD,
            "generatedAt": gcf.SERVER_TIMESTAMP,
            "updatedAt": gcf.SERVER_TIMESTAMP,
            "generatingByUid": gcf.DELETE_FIELD,
            "generatingStartedAt": gcf.DELETE_FIELD,
        }, merge=True)
        return {
            "noteId": note_id,
            "status": "ready",
            "sourceId": source.id,
            "scopeType": scope_type,
            "scopeValue": scope_value,
            "reportMarkdown": report,
            "reviewMarkdown": review,
            "files": files,
        }
    except Exception as exc:
        if isinstance(exc, HTTPException):
            message = str(exc.detail)
        elif isinstance(exc, GitToolError):
            message = str(exc)
        else:
            message = f"AI 수업 노트 생성 실패: {str(exc)[:200]}"
        ref.set({
            "status": "failed",
            "errorMessage": message[:500],
            "updatedAt": gcf.SERVER_TIMESTAMP,
            "generatingByUid": gcf.DELETE_FIELD,
            "generatingStartedAt": gcf.DELETE_FIELD,
        }, merge=True)
        if isinstance(exc, HTTPException):
            raise
        status = 502 if isinstance(exc, GitToolError) else 500
        raise HTTPException(status_code=status, detail=message) from exc
