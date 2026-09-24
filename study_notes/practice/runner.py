"""practice_verifier(Node + Pyodide)를 subprocess로 부른다.

작업을 한 번에 묶어 넘긴다 — Pyodide 부팅이 1초쯤 걸려서 문제마다 띄우면 느리다.
나중에 Docker로 가면 이 클래스만 HTTP 호출로 바꾸면 된다(verify.py는 그대로).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIER_DIR = REPO_ROOT / "practice_verifier"


@dataclass(frozen=True)
class Job:
    id: str
    steps: list[str]
    timeout_ms: int = 3000


@dataclass(frozen=True)
class RunResult:
    id: str
    ok: bool
    stdout: str
    timed_out: bool
    error_type: str = ""
    error_message: str = ""
    error_step: int = -1
    stdout_truncated: bool = False

    def describe(self) -> str:
        if self.timed_out:
            return "시간 제한 초과"
        if self.ok:
            return "정상 종료"
        return f"{self.error_type}: {self.error_message}".strip(": ")


class Runner(Protocol):
    def run(self, jobs: list[Job]) -> dict[str, RunResult]: ...


class VerifierError(RuntimeError):
    pass


class PyodideRunner:
    def __init__(self, *, node: str | None = None, verifier_dir: Path = VERIFIER_DIR) -> None:
        self.node = node or os.getenv("PRACTICE_NODE") or shutil.which("node") or "node"
        self.verifier_dir = verifier_dir
        self.version = ""

    def run(self, jobs: list[Job]) -> dict[str, RunResult]:
        if not jobs:
            return {}
        if not (self.verifier_dir / "node_modules" / "pyodide").exists():
            raise VerifierError(
                f"{self.verifier_dir}에서 npm install 을 먼저 실행하세요."
            )
        payload = {
            "jobs": [{"id": j.id, "steps": j.steps, "timeoutMs": j.timeout_ms} for j in jobs],
        }
        # 무한 루프 문제는 작업마다 워커를 새로 띄우므로(약 1초) 그만큼 여유를 둔다.
        budget = 30 + sum(j.timeout_ms / 1000 + 2 for j in jobs)
        try:
            proc = subprocess.run(
                [self.node, "cli.mjs"],
                cwd=self.verifier_dir,
                input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                capture_output=True,
                timeout=budget,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise VerifierError(f"검증기가 {budget:.0f}초 안에 끝나지 않았습니다.") from exc
        if proc.returncode != 0:
            raise VerifierError(proc.stderr.decode("utf-8", "replace")[-800:] or "검증기 실패")
        data = json.loads(proc.stdout.decode("utf-8"))
        self.version = data.get("version") or ""
        results: dict[str, RunResult] = {}
        for raw in data.get("results", []):
            error = raw.get("error") or {}
            results[raw["id"]] = RunResult(
                id=raw["id"],
                ok=bool(raw.get("ok")),
                stdout=raw.get("stdout") or "",
                timed_out=bool(raw.get("timedOut")),
                error_type=error.get("type", ""),
                error_message=error.get("message", ""),
                error_step=int(error.get("step", -1)),
                stdout_truncated=bool(raw.get("stdoutTruncated")),
            )
        return results
