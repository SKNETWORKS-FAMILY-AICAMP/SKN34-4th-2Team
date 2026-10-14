"""GitHub 계정·조직의 저장소 목록 — 공부방이 수업 저장소를 알아서 찾게 한다.

기수 조직(예: skn-ai34-260616)과 강사 개인 계정 둘 다 받는다. 수업 저장소는 대개 비공개라
토큰으로 「내가 볼 수 있는 저장소 전부」를 받아 주인 이름으로 거르고, 공개 저장소를 더한다.
강사 개인 계정의 비공개 저장소는 토큰 주인(학원 계정)을 그 저장소의 협업자(읽기)로 넣어야 보인다.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from typing import Any

from study_notes.git_tools import GitToolError, env_github_token

API = "https://api.github.com"
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
MAX_PAGES = 10
TIMEOUT_SEC = 20

_borrowed: str | None = None


def _credential_token() -> str:
    """로컬 개발 편의 — GITHUB_TOKEN 이 없으면 이 PC 의 git 로그인(자격 증명 관리자)에서 github.com 토큰을 빌린다.
    clone 이 이미 쓰는 그 로그인이다. 창을 띄우지 않고, 없으면 빈 글자. 배포 서버엔 없으니 거기선 GITHUB_TOKEN 을 쓴다."""
    global _borrowed
    if _borrowed is not None:
        return _borrowed
    try:
        out = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True,
            text=True,
            timeout=15,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"},
        ).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    _borrowed = next((line[9:] for line in out.splitlines() if line.startswith("password=")), "")
    return _borrowed


def _token() -> str:
    return env_github_token() or _credential_token()


def _get(url: str, token: str) -> tuple[Any, str]:
    """(본문, 다음 쪽 주소)"""
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "skn34-lms"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT_SEC) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            link = resp.headers.get("Link") or ""
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise GitToolError("GitHub 토큰이 올바르지 않습니다(GITHUB_TOKEN).") from exc
        if exc.code == 403:
            raise GitToolError("GitHub 요청 한도에 걸렸습니다. 잠시 후 다시 시도하세요.") from exc
        if exc.code == 404:
            raise FileNotFoundError(url) from exc
        raise GitToolError(f"GitHub 응답 오류 {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise GitToolError("GitHub에 연결하지 못했습니다. 네트워크를 확인하세요.") from exc
    match = re.search(r'<([^>]+)>;\s*rel="next"', link)
    return body, match.group(1) if match else ""


def _pages(url: str, token: str) -> list[dict]:
    out: list[dict] = []
    for _ in range(MAX_PAGES):
        body, url = _get(url, token)
        out += [r for r in body if isinstance(r, dict)]
        if not url:
            break
    return out


def list_owner_repos(owner: str) -> list[dict[str, Any]]:
    """owner(조직 또는 계정)의 저장소 중 이 서버가 읽을 수 있는 것. 보관(archived)·「.」로 시작하는 저장소는 뺀다."""
    owner = owner.strip()
    if not LOGIN_RE.match(owner):
        raise GitToolError("GitHub 계정·조직 이름이 올바르지 않습니다.")
    token = _token()
    found: dict[str, dict] = {}
    if token:
        mine = _pages(f"{API}/user/repos?per_page=100&affiliation=owner,collaborator,organization_member", token)
        for repo in mine:
            if str(repo.get("owner", {}).get("login", "")).lower() == owner.lower():
                found[repo["full_name"].lower()] = repo
    try:
        for repo in _pages(f"{API}/users/{owner}/repos?per_page=100", token):
            found.setdefault(repo["full_name"].lower(), repo)
    except FileNotFoundError as exc:
        if not found:
            raise GitToolError(f"GitHub 계정·조직 {owner} 을(를) 찾지 못했습니다.") from exc
    return sorted(
        (
            {
                "name": repo["name"],
                "repoUrl": repo["html_url"],
                "branch": repo.get("default_branch") or "main",
                "private": bool(repo.get("private")),
                "pushedAt": repo.get("pushed_at"),
            }
            for repo in found.values()
            if not repo.get("archived") and not str(repo["name"]).startswith(".")
        ),
        key=lambda r: r["name"].lower(),
    )
