"""Markdown 테스트 질문을 개선 Luna 챗봇에 실제 실행하고 결과를 저장한다."""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def parse_cases(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    section = ""
    cases: list[dict[str, Any]] = []
    pending_followup: dict[str, Any] | None = None
    for raw in lines:
        line = raw.strip()
        if line.startswith("### "):
            section = line[4:].strip()
            pending_followup = None
            continue
        if line.startswith("## "):
            section = line[3:].strip()
            pending_followup = None
            continue
        if section.startswith("3. Supervisor"):
            first = re.match(r"^(\d+)\.\s*첫 질문:\s*(.+)$", line)
            follow = re.match(r"^후속 질문:\s*(.+)$", line)
            if first:
                pending_followup = {
                    "id": f"followup-{first.group(1)}",
                    "section": section,
                    "questions": [first.group(2).strip()],
                }
            elif follow and pending_followup:
                pending_followup["questions"].append(follow.group(1).strip())
                cases.append(pending_followup)
                pending_followup = None
            continue
        match = re.match(r"^(\d+)\.\s+(.+)$", line)
        if match and (section.startswith("2-") or section.startswith("4-")):
            cases.append({
                "id": f"{section.split('.')[0]}-{match.group(1)}",
                "section": section,
                "questions": [match.group(2).strip()],
            })
    return cases


def slim_result(result: dict[str, Any]) -> dict[str, Any]:
    sources = []
    for source in result.get("sources") or []:
        sources.append({
            key: source.get(key)
            for key in ("title", "doc_id", "namespace", "cohort", "project_round", "url")
            if source.get(key) is not None
        })
    return {
        "answer": result.get("answer"),
        "route": result.get("route"),
        "namespaces": result.get("namespaces") or [],
        "student_scopes": result.get("student_scopes") or [],
        "query": result.get("query"),
        "sources": sources,
    }


def write_outputs(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = [
        "# LMS 학생 챗봇 실제 실행 결과",
        "",
        f"- 실행 시각: {payload['started_at']}",
        f"- 모델: {payload['model']}",
        f"- 학생: {payload['student']['display_name']} ({payload['student']['cohort']})",
        f"- 완료 호출: {payload['completed_calls']} / {payload['total_calls']}",
        "",
    ]
    for case in payload["results"]:
        markdown.extend([f"## {case['id']} · {case['section']}", ""])
        for turn in case["turns"]:
            markdown.extend([
                f"### 질문 {turn['turn']}", "", turn["question"], "",
                "### 실제 답변", "", turn["result"].get("answer") or "(응답 없음)", "",
                f"- 경로: `{turn['result'].get('route')}`",
                f"- namespaces: `{turn['result'].get('namespaces')}`",
                f"- student_scopes: `{turn['result'].get('student_scopes')}`",
                f"- 실행 시간: {turn['elapsed_ms']:,}ms", "",
            ])
    path.with_suffix(".md").write_text("\n".join(markdown), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("markdown", type=Path)
    parser.add_argument("--student", required=True, help="Firebase UID 또는 이메일")
    parser.add_argument("--output", type=Path, default=RESULTS_DIR / "markdown_eval.json")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    from chatbot_lab.bot import LAB_MODEL, create_lab_chatbot
    from chatbot_lab.firebase_loader import create_firebase_student_loader

    cases = parse_cases(args.markdown)
    total_calls = sum(len(case["questions"]) for case in cases)
    if len(cases) != 45 or total_calls != 50:
        raise RuntimeError(f"질문 파싱 결과가 예상과 다릅니다: {len(cases)}개 항목, {total_calls}회")

    loader, uid, cohort = create_firebase_student_loader(args.student)
    bot = create_lab_chatbot(student_context_loader=loader)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "started_at": datetime.now().astimezone().isoformat(),
        "model": LAB_MODEL,
        "student": {"uid": uid, "display_name": "문성호", "cohort": cohort},
        "source_markdown": str(args.markdown),
        "total_calls": total_calls,
        "completed_calls": 0,
        "results": [],
    }
    write_outputs(args.output, payload)

    for case_index, case in enumerate(cases, 1):
        completed_case = {"id": case["id"], "section": case["section"], "turns": []}
        thread_id = f"md-eval-{case_index:02d}"
        for turn_index, question in enumerate(case["questions"], 1):
            started = time.perf_counter()
            try:
                result = slim_result(bot.invoke_debug({
                    "question": question,
                    "thread_id": thread_id,
                    "cohort": cohort,
                    "student_uid": uid,
                }))
                error = None
            except Exception as exc:
                result = {}
                error = f"{type(exc).__name__}: {exc}"
            elapsed = round((time.perf_counter() - started) * 1000)
            completed_case["turns"].append({
                "turn": turn_index,
                "question": question,
                "result": result,
                "error": error,
                "elapsed_ms": elapsed,
            })
            payload["completed_calls"] += 1
            print(
                f"[{payload['completed_calls']:02d}/{total_calls}] {case['id']} turn {turn_index} "
                f"{elapsed}ms {'ERROR ' + error if error else 'OK'}",
                flush=True,
            )
        payload["results"].append(completed_case)
        write_outputs(args.output, payload)

    payload["finished_at"] = datetime.now().astimezone().isoformat()
    write_outputs(args.output, payload)
    print(f"DONE {args.output} {args.output.with_suffix('.md')}", flush=True)


if __name__ == "__main__":
    main()
