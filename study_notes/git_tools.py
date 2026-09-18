"""로컬 git 명령으로 강사 저장소를 읽는다.

- 저장소는 기수/소스별 캐시 폴더에 `--filter=blob:none --no-checkout`으로 받는다.
  파일 내용은 `git show`가 필요할 때만 서버에서 가져오므로 크기가 작다.
- 모든 git 호출은 인자 리스트로 실행한다. 셸 문자열은 쓰지 않는다.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

# KST는 DST가 없어 고정 오프셋으로 충분하다. (Windows는 tzdata가 없어 ZoneInfo가 실패한다)
SEOUL = timezone(timedelta(hours=9), name="Asia/Seoul")
ALLOWED_SUFFIXES = (".ipynb", ".py", ".md")
RECENT_DAYS = 30
MAX_TREE_ENTRIES = 400
GIT_TIMEOUT_SEC = 180

_REPO_RE = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")
_BRANCH_RE = re.compile(r"^[\w./-]+$")

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_sync_cache: dict[str, tuple[float, str]] = {}
SYNC_TTL_SEC = 120


class GitToolError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 git 오류."""


@dataclass(frozen=True)
class RepoRef:
    owner: str
    repo: str

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}.git"


@dataclass(frozen=True)
class ChangedFile:
    path: str
    commit: str


def parse_repo_url(repo_url: str) -> RepoRef:
    match = _REPO_RE.match(repo_url.strip())
    if not match:
        raise GitToolError("https://github.com/owner/repo 형식의 저장소 주소만 허용됩니다.")
    return RepoRef(owner=match.group(1), repo=match.group(2))


def sanitize_branch(branch: str) -> str:
    value = (branch or "").strip() or "main"
    if ".." in value or "\\" in value or value.startswith("-") or not _BRANCH_RE.match(value):
        raise GitToolError("브랜치 이름이 올바르지 않습니다.")
    return value


def sanitize_path(path: str) -> str:
    value = path.strip().replace("\\", "/").lstrip("/")
    if not value or ".." in value or "\0" in value:
        raise GitToolError("파일 경로가 올바르지 않습니다.")
    return value


def is_learning_file(path: str) -> bool:
    return path.lower().endswith(ALLOWED_SUFFIXES)


def path_allowed(path: str, prefixes: list[str]) -> bool:
    if not prefixes:
        return True
    for prefix in prefixes:
        base = prefix.rstrip("/")
        if path == base or path.startswith(f"{base}/"):
            return True
    return False


def cache_root() -> Path:
    override = os.getenv("STUDY_NOTES_CACHE_DIR", "").strip()
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "skn34-study-notes"


def _safe_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)[:80] or "_"


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = _locks[key] = threading.Lock()
        return lock


def run_git(args: list[str], cwd: Path | None = None) -> str:
    command = ["git", *args]
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=GIT_TIMEOUT_SEC,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"},
        )
    except FileNotFoundError as exc:
        raise GitToolError("서버에 git이 설치되어 있지 않습니다.") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitToolError("저장소를 읽는 데 시간이 너무 오래 걸립니다.") from exc
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise GitToolError(_friendly_git_error(stderr))
    return result.stdout


def _friendly_git_error(stderr: str) -> str:
    lower = stderr.lower()
    if "could not read username" in lower or "authentication failed" in lower:
        return "비공개 저장소입니다. 서버 PC에서 GitHub 로그인이 필요합니다."
    if "repository not found" in lower or "not found" in lower:
        return "GitHub 저장소를 찾지 못했습니다. 주소를 확인하세요."
    if "couldn't find remote ref" in lower or "remote branch" in lower:
        return "브랜치를 찾지 못했습니다. 브랜치 이름을 확인하세요."
    if "could not resolve host" in lower or "unable to access" in lower:
        return "GitHub에 연결하지 못했습니다. 네트워크를 확인하세요."
    return f"git 오류: {stderr[:200] or '알 수 없는 오류'}"


class RepoCache:
    """기수/소스 하나에 대응하는 로컬 저장소 캐시."""

    def __init__(self, cohort_id: str, source_id: str, repo: RepoRef, branch: str) -> None:
        self.repo = repo
        self.branch = sanitize_branch(branch)
        self.dir = cache_root() / _safe_segment(cohort_id) / _safe_segment(source_id)
        self._lock = _lock_for(str(self.dir))

    @property
    def ref(self) -> str:
        return f"refs/remotes/origin/{self.branch}"

    def _clone(self) -> None:
        self.dir.parent.mkdir(parents=True, exist_ok=True)
        if self.dir.exists():
            shutil.rmtree(self.dir, ignore_errors=True)
        run_git(
            [
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                "--single-branch",
                "--branch",
                self.branch,
                self.repo.clone_url,
                str(self.dir),
            ],
        )

    def _origin_url(self) -> str:
        try:
            return run_git(["remote", "get-url", "origin"], cwd=self.dir).strip().rstrip("/")
        except GitToolError:
            return ""

    def sync(self, *, force: bool = False) -> str:
        """clone 또는 fetch 후 브랜치 HEAD sha를 반환한다.

        같은 저장소는 2분 안이면 fetch를 건너뛴다. 트리 조회가 매번 GitHub에
        나가지 않게 해서 화면 진입을 빠르게 한다.
        """
        cache_key = str(self.dir)
        with self._lock:
            cached = (self.dir / ".git").exists() or (self.dir / "HEAD").exists()
            previous = _sync_cache.get(cache_key)
            if (
                not force
                and cached
                and previous
                and time.monotonic() - previous[0] < SYNC_TTL_SEC
                and self._origin_url() == self.repo.clone_url.rstrip("/")
            ):
                return previous[1]
            if cached and self._origin_url() == self.repo.clone_url.rstrip("/"):
                run_git(
                    [
                        "fetch",
                        "--filter=blob:none",
                        "--prune",
                        "origin",
                        f"+refs/heads/{self.branch}:{self.ref}",
                    ],
                    cwd=self.dir,
                )
            else:
                self._clone()
            sha = run_git(["rev-parse", self.ref], cwd=self.dir).strip()
            _sync_cache[cache_key] = (time.monotonic(), sha)
            return sha

    # ── 조회 ────────────────────────────────────────────────────────

    def list_tree(self, prefixes: list[str]) -> list[str]:
        out = run_git(["ls-tree", "-r", "--name-only", self.ref], cwd=self.dir)
        paths = sorted(
            {
                line.strip()
                for line in out.splitlines()
                if line.strip() and is_learning_file(line.strip()) and path_allowed(line.strip(), prefixes)
            }
        )
        return paths

    def _log_with_files(self, extra_args: list[str]) -> list[tuple[str, str, list[str]]]:
        """[(sha, author_iso, [paths])] 최신순."""
        out = run_git(
            [
                "log",
                *extra_args,
                "--name-only",
                "--pretty=format:%x1e%H%x1f%aI",
                self.ref,
            ],
            cwd=self.dir,
        )
        commits: list[tuple[str, str, list[str]]] = []
        for block in out.split("\x1e"):
            block = block.strip("\n")
            if not block.strip():
                continue
            header, _, body = block.partition("\n")
            sha, _, iso = header.partition("\x1f")
            files = [line.strip() for line in body.splitlines() if line.strip()]
            commits.append((sha.strip(), iso.strip(), files))
        return commits

    def recent_lesson_dates(self, prefixes: list[str]) -> list[str]:
        since = (datetime.now(SEOUL) - timedelta(days=RECENT_DAYS)).isoformat()
        dates: set[str] = set()
        for _sha, iso, files in self._log_with_files([f"--since={since}"]):
            if not any(is_learning_file(p) and path_allowed(p, prefixes) for p in files):
                continue
            try:
                when = datetime.fromisoformat(iso).astimezone(SEOUL)
            except ValueError:
                continue
            dates.add(when.strftime("%Y-%m-%d"))
        return sorted(dates, reverse=True)

    def changed_files_on(self, date: str, prefixes: list[str]) -> tuple[list[str], list[ChangedFile]]:
        """해당 날짜(KST)의 커밋 목록과, 파일별 가장 최신 커밋."""
        start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=SEOUL)
        end = start + timedelta(days=1)
        latest: dict[str, str] = {}
        shas: list[str] = []
        for sha, _iso, files in self._log_with_files(
            [f"--since={start.isoformat()}", f"--until={end.isoformat()}"],
        ):
            shas.append(sha)
            for path in files:
                if not is_learning_file(path) or not path_allowed(path, prefixes):
                    continue
                if path not in latest and self._exists_at(sha, path):
                    latest[path] = sha
        files_sorted = [ChangedFile(path=p, commit=c) for p, c in sorted(latest.items())]
        return shas, files_sorted

    def _exists_at(self, sha: str, path: str) -> bool:
        """삭제된 파일(removed)은 제외한다."""
        try:
            run_git(["cat-file", "-e", f"{sha}:{path}"], cwd=self.dir)
            return True
        except GitToolError:
            return False

    def read_file(self, commit: str, path: str) -> str:
        return run_git(["show", f"{commit}:{path}"], cwd=self.dir)


def notebook_to_text(raw: str) -> str:
    """ipynb에서 Markdown·코드 셀만 추출하고 실행 출력은 제외한다."""
    try:
        notebook = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    sections: list[str] = []
    for index, cell in enumerate(notebook.get("cells", [])):
        cell_type = cell.get("cell_type", "unknown")
        if cell_type not in {"markdown", "code"}:
            continue
        source = cell.get("source", [])
        text = "".join(source) if isinstance(source, list) else str(source)
        text = text.strip()
        if text:
            sections.append(f"[{cell_type.upper()} CELL {index}]\n{text}")
    return "\n\n".join(sections)
