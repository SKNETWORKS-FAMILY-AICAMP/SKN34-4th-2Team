"""폴더 올리기 — GitHub 없이 올린 수업 자료를 서버 안 git 저장소에 날짜별 커밋으로 넣는다.

강사가 git 을 쓰지 않아도 「수업 날짜 = 커밋 날짜, 그날 수업 = 그날 바뀐 파일」을 그대로 만든다.
그래서 노트 · 복습 문제 · 과목 요약은 GitHub 저장소와 같은 코드(git_tools.RepoCache)로 읽는다.

- 저장소 주소는 `upload://<기수>/<과목>`(study_sources.repo_url — 테이블은 그대로). git_tools.parse_repo_url 이 알아본다.
- 저장소 자리는 GitHub 캐시와 같은 cache_root/<기수>/<소스 id>. 원격(origin)이 없어 브랜치는 refs/heads/main.
- 커밋 날짜는 그날 18:00(KST) — 작성 · 커밋 날짜를 같게 둔다. 지난 날짜로 늦게 올려도 읽는 쪽이 날짜를 직접 거른다.
- 내용이 지난번과 같은 파일은 넣지 않는다. 폴더에서 빠진 파일은 지우지 않는다(실수로 빠뜨린 걸 지운 것으로 보지 않게).
- 날짜를 모르는 「지난 자료」는 따로 표시한 커밋 하나로 넣는다(작성자 PAST_AUTHOR_EMAIL). 수업 날짜 목록 · 「그날 파일」은
  이 커밋을 건너뛰어서 날짜 노트 · 날짜별 출제에는 안 나오고, 폴더 노트 · 과목 요약처럼 최신 파일 전체를 보는 곳에만 나온다.
- 내용 지문(blob id)을 화면과 맞추려고 줄바꿈 변환을 끈다(core.autocrlf=false) — 올린 그대로 저장한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from study_notes.git_tools import (
    PAST_AUTHOR_EMAIL,
    GitToolError,
    RepoCache,
    _lock_for,
    _sync_cache,
    is_learning_file,
    run_git,
    sanitize_path,
)
from study_notes.upload_plan import blob_id, read_texts

BRANCH = "main"
LESSON_HOUR = "18:00:00"
AUTHOR = ("LMS 폴더 올리기", "upload@lms.local")
PAST_AUTHOR = ("LMS 지난 자료", PAST_AUTHOR_EMAIL)
# 한 번에 받는 파일 — 화면이 이보다 많으면 나눠 보낸다
MAX_FILES = 300
MAX_FILE_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class DayCommit:
    date: str
    sha: str | None
    changed: list[str]
    skipped: list[str]


def _git(repo: Path, args: list[str], *, when: str | None = None, author: tuple[str, str] = AUTHOR) -> str:
    """서버 안 저장소 전용 git — 작성자 · 날짜를 이번 호출에만 넣는다(전역 git 설정 · 프로세스 환경은 그대로)"""
    env = {
        "GIT_AUTHOR_NAME": author[0], "GIT_AUTHOR_EMAIL": author[1],
        "GIT_COMMITTER_NAME": author[0], "GIT_COMMITTER_EMAIL": author[1],
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
        # 올린 그대로 저장(지문이 화면과 같게), 한글 파일 이름을 따옴표 · 8진수로 바꾸지 않게
        for key, value in (("core.autocrlf", "false"), ("core.safecrlf", "false"), ("core.quotepath", "false")):
            run_git(["config", key, value], cwd=repo)
    return repo


def has_commits(repo: Path) -> bool:
    try:
        run_git(["rev-parse", "--verify", "-q", f"refs/heads/{BRANCH}"], cwd=repo)
        return True
    except GitToolError:
        return False



def tree_blobs(repo: Path) -> dict[str, str]:
    """지금(마지막 커밋) 파일마다 내용 지문 {경로: blob id} — 「지난번과 같은 파일」을 가르는 기준"""
    if not has_commits(repo):
        return {}
    out = run_git(["ls-tree", "-r", "-z", f"refs/heads/{BRANCH}"], cwd=repo)
    found: dict[str, str] = {}
    for entry in out.split("\0"):
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob" and path:
            found[path] = parts[2]
    return found


def _clean(files: dict[str, bytes]) -> dict[str, bytes]:
    """수업 파일(.ipynb · .py …)만, 안전한 경로만, 크기 한도 안에서"""
    if len(files) > MAX_FILES:
        raise GitToolError(f"한 번에 {MAX_FILES}개까지 올릴 수 있어요. 나눠서 올려 주세요.")
    clean: dict[str, bytes] = {}
    for raw_path, body in files.items():
        path = sanitize_path(raw_path)
        if path.startswith(".git/") or "/.git/" in path or path == ".git":
            raise GitToolError("파일 경로가 올바르지 않습니다.")
        if not is_learning_file(path):
            continue
        if len(body) > MAX_FILE_BYTES:
            raise GitToolError(f"{path} 가 너무 커요({MAX_FILE_BYTES // 1024 // 1024}MB 까지).")
        clean[path] = body
    return clean


def _commit(
    cache: RepoCache, label: str, files: dict[str, bytes], *, message: str, when: str | None, author: tuple[str, str]
) -> DayCommit:
    """바뀐 파일만 커밋 하나로. message 의 {n} 은 바뀐 파일 수"""
    clean = _clean(files)
    with _lock_for(str(cache.dir)):
        repo = ensure_repo(cache)
        before = tree_blobs(repo)
        changed: list[str] = []
        skipped: list[str] = []
        for path, body in sorted(clean.items()):
            if before.get(path) == blob_id(body):
                skipped.append(path)
                continue
            target = repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            changed.append(path)
        if not changed:
            return DayCommit(label, None, [], skipped)
        _git(repo, ["add", "--", *changed])
        _git(repo, ["commit", "-q", "-m", message.format(n=len(changed))], when=when, author=author)
        sha = run_git(["rev-parse", f"refs/heads/{BRANCH}"], cwd=repo).strip()
        _sync_cache.pop(str(cache.dir), None)
        return DayCommit(label, sha, changed, skipped)


def commit_day(cache: RepoCache, date: str, files: dict[str, bytes], message: str = "") -> DayCommit:
    """그날 수업 파일을 그 날짜 커밋 하나로. 바뀐 게 없으면 커밋하지 않는다(sha=None).

    files — {저장소 안 경로: 내용}. 수업 파일(.ipynb · .py …)만 받는다.
    """
    return _commit(
        cache, date, files,
        message=message.replace("{", "{{").replace("}", "}}") if message else f"{date} 수업 파일 {{n}}개",
        when=f"{date}T{LESSON_HOUR}+09:00", author=AUTHOR,
    )


def commit_past(cache: RepoCache, files: dict[str, bytes]) -> DayCommit:
    """날짜를 모르는 지난 자료 — 표시한 커밋 하나(커밋 시각은 지금). 수업 날짜로 세지 않는다"""
    return _commit(cache, "", files, message="지난 자료 {n}개(날짜 없음)", when=None, author=PAST_AUTHOR)


def import_all(cache: RepoCache, days: dict[str, dict[str, bytes]], past: dict[str, bytes] | None = None) -> list[DayCommit]:
    """처음 가져오기 — 지난 자료를 먼저, 그다음 날짜별 묶음을 오래된 날부터 차례로 커밋한다.
    두 날에 걸친 노트북은 화면이 첫날 몫(앞 셀들)과 둘째 날 몫(전체)을 따로 담아 보낸다."""
    out = [commit_past(cache, past)] if past else []
    return out + [commit_day(cache, date, days[date]) for date in sorted(days)]


def snapshot(cache: RepoCache, *, texts: bool = True) -> dict:
    """계획에 쓸 지금 모습 — {tree: {경로: blob}, dates: [수업 날짜], texts: {경로: 앞부분 글}}. 아직 없는 과목이면 빈 것.
    texts 는 오늘 수업 올리기의 폴더 추천에만 쓴다(처음 가져오기는 안 읽는다)."""
    if not (cache.dir / ".git").exists():
        return {"tree": {}, "dates": [], "texts": {}}
    with _lock_for(str(cache.dir)):
        tree = tree_blobs(cache.dir)
        found = read_texts(cache.dir, [p for p in tree if "/" in p and is_learning_file(p)]) if texts else {}
    dates = cache.recent_lesson_dates([]) if tree else []
    return {"tree": tree, "dates": dates, "texts": found}
