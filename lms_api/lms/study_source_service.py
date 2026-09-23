"""공부방 수업 저장소 — 기수에 연결한 GitHub 조직·계정에서 저장소를 찾아 자동으로 올린다.

- 관리자·강사가 기수에 GitHub 조직(예: skn-ai34-260616)이나 강사 개인 계정을 연결한다(study.github_owners).
- 찾기: AI 서버(/api/v1/study-notes/proxy/repos)가 그 주인의 저장소 목록을 주면, study_sources 에 없는 것만
  바로 공개(is_active = true)로 넣는다. 이미 있는 저장소는 건드리지 않는다 — 숨긴 저장소는 숨긴 채로 남는다.
- 언제: 저장소 관리 화면을 열 때(10분에 한 번까지), 「저장소 새로 찾기」, Celery beat 한 시간마다(lms.tasks).
- 강사는 자기 기수만, 관리자는 모든 기수.
"""

from __future__ import annotations

import re
from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

from lms.study_note_service import StudyNoteError, _call, _dicts, _one

SYNC_EVERY = timedelta(minutes=10)
REPOS_TIMEOUT = 60
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
# 저장소 주소 비교 — 대소문자 · 끝 / · .git 차이는 같은 저장소다
SAME_REPO_SQL = "lower(regexp_replace(rtrim(repo_url, '/'), '\\.git$', ''))"


class StudySourceError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _repo_key(url: str) -> str:
    return re.sub(r"\.git$", "", url.strip().rstrip("/")).lower()


def _check_schema(cur) -> None:
    cur.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name = 'study'")
    if not cur.fetchone():
        raise StudySourceError(503, "study 스키마가 없습니다. scripts/firestore_to_postgres/study_schema.sql 을 실행하세요.")


def _cohort(cur, user: dict, cohort_code: str) -> dict:
    """저장소를 관리할 기수. 강사는 자기 기수만."""
    if user.get("role") not in ("admin", "instructor"):
        raise StudySourceError(403, "강사·관리자만 수업 저장소를 관리할 수 있습니다.")
    code = (cohort_code or user.get("cohort_code") or "").strip()
    if user.get("role") == "instructor" and code != user.get("cohort_code"):
        raise StudySourceError(403, "자기 기수의 저장소만 관리할 수 있습니다.")
    cur.execute("SELECT id, code FROM cohorts WHERE code = %s", [code])
    row = _one(cur)
    if not row:
        raise StudySourceError(404, "기수를 찾을 수 없습니다.")
    return row


def _owners(cur, code: str) -> list[dict]:
    cur.execute(
        "SELECT id, owner, last_synced_at, last_error FROM study.github_owners WHERE cohort_code = %s ORDER BY id",
        [code],
    )
    return [
        {
            "id": str(r["id"]),
            "owner": r["owner"],
            "lastSyncedAt": r["last_synced_at"].isoformat() if r["last_synced_at"] else None,
            "lastError": r["last_error"] or "",
        }
        for r in _dicts(cur)
    ]


# ── 연결 ──────────────────────────────────────────────────────────


def list_owners(user: dict, cohort_code: str) -> dict:
    with connection.cursor() as cur:
        _check_schema(cur)
        cohort = _cohort(cur, user, cohort_code)
        return {"cohortId": cohort["code"], "owners": _owners(cur, cohort["code"])}


def add_owner(user: dict, cohort_code: str, owner: str) -> dict:
    owner = (owner or "").strip().removeprefix("https://github.com/").strip("/")
    if not LOGIN_RE.match(owner):
        raise StudySourceError(422, "GitHub 조직·계정 이름을 적어 주세요(예: skn-ai34-260616).")
    with transaction.atomic(), connection.cursor() as cur:
        _check_schema(cur)
        cohort = _cohort(cur, user, cohort_code)
        cur.execute(
            """INSERT INTO study.github_owners (cohort_code, owner, added_by_uid) VALUES (%s, %s, %s)
               ON CONFLICT (cohort_code, lower(owner)) DO NOTHING""",
            [cohort["code"], owner, user.get("firebase_uid") or ""],
        )
    # 연결하자마자 한 번 찾는다 — 화면에 바로 저장소가 보이게
    return sync_cohort(user, cohort["code"], force=True)


def remove_owner(user: dict, owner_id: str) -> dict:
    """연결만 끊는다. 이미 올라간 저장소와 학생 노트는 그대로 — 필요하면 저장소를 숨긴다."""
    with transaction.atomic(), connection.cursor() as cur:
        _check_schema(cur)
        cur.execute("SELECT cohort_code FROM study.github_owners WHERE id::text = %s", [str(owner_id)])
        row = _one(cur)
        if not row:
            raise StudySourceError(404, "연결을 찾을 수 없습니다.")
        cohort = _cohort(cur, user, row["cohort_code"])
        cur.execute("DELETE FROM study.github_owners WHERE id::text = %s", [str(owner_id)])
        return {"cohortId": cohort["code"], "owners": _owners(cur, cohort["code"])}


# ── 찾기 ──────────────────────────────────────────────────────────


def _sync_code(code: str, *, force: bool) -> tuple[list[str], list[dict]]:
    """(새로 올린 저장소 이름, 주인별 오류). 권한 확인은 부르는 쪽이 했다."""
    with connection.cursor() as cur:
        cur.execute("SELECT id FROM cohorts WHERE code = %s", [code])
        cohort = _one(cur)
        cur.execute("SELECT * FROM study.github_owners WHERE cohort_code = %s ORDER BY id", [code])
        owners = _dicts(cur)
    if not cohort:
        return [], []
    now = timezone.now()
    added: list[str] = []
    errors: list[dict] = []
    for owner in owners:
        last = owner.get("last_synced_at")
        if not force and last and now - last < SYNC_EVERY and not owner.get("last_error"):
            continue
        try:
            repos = _call("/proxy/repos", {"owner": owner["owner"]}, REPOS_TIMEOUT).get("repos") or []
            error = ""
        except StudyNoteError as exc:
            repos, error = [], exc.detail
            errors.append({"owner": owner["owner"], "error": error})
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute(f"SELECT {SAME_REPO_SQL} AS k FROM study_sources WHERE cohort_id = %s", [cohort["id"]])
            known = {r["k"] for r in _dicts(cur)}
            cur.execute("SELECT COALESCE(max(sort_order), 0) AS n FROM study_sources WHERE cohort_id = %s", [cohort["id"]])
            order = _one(cur)["n"] or 0
            for repo in repos:
                url = str(repo.get("repoUrl") or "")
                if not url or _repo_key(url) in known:
                    continue
                order += 1
                cur.execute(
                    """INSERT INTO study_sources (cohort_id, title, repo_url, branch, allowed_prefixes, is_active,
                                                  sort_order, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, '{}', true, %s, now(), now())""",
                    [cohort["id"], repo.get("name") or url.rsplit("/", 1)[-1], url, repo.get("branch") or "main", order],
                )
                known.add(_repo_key(url))
                added.append(str(repo.get("name") or url))
            cur.execute(
                "UPDATE study.github_owners SET last_synced_at = now(), last_error = %s WHERE id = %s",
                [error[:500], owner["id"]],
            )
    return added, errors


def sync_cohort(user: dict, cohort_code: str, *, force: bool = False) -> dict:
    """기수에 연결한 조직·계정에서 새 저장소를 찾아 올린다. force 가 아니면 10분 안에 찾은 주인은 건너뛴다."""
    with connection.cursor() as cur:
        _check_schema(cur)
        cohort = _cohort(cur, user, cohort_code)
    added, errors = _sync_code(cohort["code"], force=force)
    with connection.cursor() as cur:
        return {"cohortId": cohort["code"], "added": added, "errors": errors, "owners": _owners(cur, cohort["code"])}


def sync_all() -> dict:
    """Celery beat 가 부른다 — 연결이 있는 모든 기수"""
    with connection.cursor() as cur:
        cur.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name = 'study'")
        if not cur.fetchone():
            return {}
        cur.execute("SELECT DISTINCT cohort_code FROM study.github_owners")
        codes = [r[0] for r in cur.fetchall()]
    result = {}
    for code in codes:
        added, errors = _sync_code(code, force=True)
        result[code] = {"added": added, "errors": errors}
    return result


# ── 숨기기 ─────────────────────────────────────────────────────────


def update_source(user: dict, source_key: str, *, is_active: bool | None = None, title: str | None = None) -> dict:
    """공개 · 숨김, 이름 바꾸기. 숨긴 저장소는 학생 목록에서 빠지고 새 노트를 만들 수 없다(만든 노트는 남는다)."""
    with transaction.atomic(), connection.cursor() as cur:
        cur.execute(
            """SELECT s.id, s.legacy_id, c.code FROM study_sources s JOIN cohorts c ON c.id = s.cohort_id
               WHERE s.legacy_id = %s OR s.id::text = %s ORDER BY (s.legacy_id = %s) DESC NULLS LAST LIMIT 1""",
            [source_key, source_key, source_key],
        )
        row = _one(cur)
        if not row:
            raise StudySourceError(404, "저장소를 찾을 수 없습니다.")
        _cohort(cur, user, row["code"])
        if title is not None and not title.strip():
            raise StudySourceError(422, "이름을 적어 주세요.")
        cur.execute(
            """UPDATE study_sources SET is_active = COALESCE(%s, is_active), title = COALESCE(%s, title), updated_at = now()
               WHERE id = %s RETURNING id, legacy_id, title, is_active""",
            [is_active, title.strip() if title is not None else None, row["id"]],
        )
        out = _one(cur)
    return {"id": str(out["legacy_id"] or out["id"]), "title": out["title"], "isActive": out["is_active"]}
