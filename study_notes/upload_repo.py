"""폴더 올리기 — GitHub 없이 올린 수업 자료를 서버 안 git 저장소에 날짜별 커밋으로 넣는다.

강사가 git 을 쓰지 않아도 「수업 날짜 = 커밋 날짜, 그날 수업 = 그날 바뀐 파일」을 그대로 만든다.
그래서 노트 · 복습 문제 · 과목 요약은 GitHub 저장소와 같은 코드(git_tools.RepoCache)로 읽는다.

- 저장소 주소는 `upload://<기수>/<과목>`(study_sources.repo_url — 테이블은 그대로). git_tools.parse_repo_url 이 알아본다.
- 저장소 자리는 GitHub 캐시와 같은 cache_root/<기수>/<소스 id>. 원격(origin)이 없어 브랜치는 refs/heads/main.
- 커밋 날짜는 그날 18:00(KST) — 작성 · 커밋 날짜를 같게 둔다. 지난 날짜로 늦게 올려도 읽는 쪽이 날짜를 직접 거른다.
- 내용이 지난번과 같은 파일은 넣지 않는다. 폴더에서 빠진 파일은 지우지 않는다(실수로 빠뜨린 걸 지운 것으로 보지 않게).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from study_notes.git_tools import (
    GitToolError,
    RepoCache,
    _lock_for,
    _sync_cache,
    is_learning_file,
    run_git,
    sanitize_path,
)

BRANCH = "main"
LESSON_HOUR = "18:00:00"
AUTHOR = ("LMS 폴더 올리기", "upload@lms.local")
# 한 번에 받는 파일 — 화면이 이보다 많으면 나눠 보낸다
MAX_FILES = 300
MAX_FILE_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class DayCommit:
    date: str
    sha: str | None
    changed: list[str]
    skipped: list[str]


def _git(repo: Path, args: list[str], *, when: str | None = None) -> str:
    """서버 안 저장소 전용 git — 작성자 · 날짜를 이번 호출에만 넣는다(전역 git 설정 · 프로세스 환경은 그대로)"""
    env = {
        "GIT_AUTHOR_NAME": AUTHOR[0], "GIT_AUTHOR_EMAIL": AUTHOR[1],
        "GIT_COMMITTER_NAME": AUTHOR[0], "GIT_COMMITTER_EMAIL": AUTHOR[1],
    }
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when
    return run_git(args, cwd=repo, extra_env=env)


def ensure_repo(cache: RepoCache) -> Path:
    """없으면 빈 저장소를 만든다. (나중에: 보관해 둔 사본에서 되살리기)"""
    repo = cache.dir
    if not (repo / ".git").exists():
        repo.mkdir(parents=True, exist_ok=True)
        run_git(["init", "-q", "-b", BRANCH], cwd=repo)
    return repo


def has_commits(repo: Path) -> bool:
    try:
        run_git(["rev-parse", "--verify", "-q", f"refs/heads/{BRANCH}"], cwd=repo)
        return True
    except GitToolError:
        return False


def _same_as_head(repo: Path, path: str, body: bytes) -> bool:
    """지난번(HEAD)과 내용이 같은가 — 작업 폴더가 아니라 커밋된 내용과 견준다"""
    if not has_commits(repo):
        return False
    try:
        head_blob = run_git(["rev-parse", f"refs/heads/{BRANCH}:{path}"], cwd=repo).strip()
    except GitToolError:
        return False
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    new_blob = run_git(["hash-object", "--", path], cwd=repo).strip()
    return new_blob == head_blob


def commit_day(cache: RepoCache, date: str, files: dict[str, bytes], message: str = "") -> DayCommit:
    """그날 수업 파일을 그 날짜 커밋 하나로. 바뀐 게 없으면 커밋하지 않는다(sha=None).

    files — {저장소 안 경로: 내용}. 수업 파일(.ipynb · .py …)만 받는다.
    """
    if len(files) > MAX_FILES:
        raise GitToolError(f"한 번에 {MAX_FILES}개까지 올릴 수 있어요. 나눠서 올려 주세요.")
    clean: dict[str, bytes] = {}
    for raw_path, body in files.items():
        path = sanitize_path(raw_path)
        if path.startswith(".git/") or "/.git/" in path:
            raise GitToolError("파일 경로가 올바르지 않습니다.")
        if not is_learning_file(path):
            continue
        if len(body) > MAX_FILE_BYTES:
            raise GitToolError(f"{path} 가 너무 커요({MAX_FILE_BYTES // 1024 // 1024}MB 까지).")
        clean[path] = body

    with _lock_for(str(cache.dir)):
        repo = ensure_repo(cache)
        changed: list[str] = []
        skipped: list[str] = []
        for path, body in sorted(clean.items()):
            if _same_as_head(repo, path, body):
                skipped.append(path)
                continue
            target = repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            changed.append(path)
        if not changed:
            return DayCommit(date, None, [], skipped)
        _git(repo, ["add", "--", *changed])
        when = f"{date}T{LESSON_HOUR}+09:00"
        _git(repo, ["commit", "-q", "-m", message or f"{date} 수업 파일 {len(changed)}개"], when=when)
        sha = run_git(["rev-parse", f"refs/heads/{BRANCH}"], cwd=repo).strip()
        _sync_cache.pop(str(cache.dir), None)
        return DayCommit(date, sha, changed, skipped)


def import_days(cache: RepoCache, days: dict[str, dict[str, bytes]]) -> list[DayCommit]:
    """처음 가져오기 — 날짜별 파일 묶음을 오래된 날부터 차례로 커밋한다"""
    return [commit_day(cache, date, days[date]) for date in sorted(days)]
