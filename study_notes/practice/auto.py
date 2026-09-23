"""복습 문제 자동 출제 — 강사가 수업 저장소에 올린 새 내용으로 그날 문제를 만든다.

LMS(Django)가 매일 18:30(수업 끝)에 저장소마다 부른다(api.py 의 /proxy/practice).
daily.py 를 손으로 돌리던 것과 같은 일을 한다.

- 마지막으로 출제한 수업 날짜부터 오늘까지, 커밋이 있는 날마다 「새로 생긴 셀」로만 출제한다(increments).
  마지막 날도 다시 본다 — 그날 저녁 늦게 올린 커밋은 다음 날 실행이 그날 몫에서 남은 만큼만 채운다.
- 처음 보는 저장소는 최근 FIRST_RUN_DAYS 일 안의 가장 최근 수업 하루만 — 연결하자마자 지난 과목 전체를 출제하지 않고,
  며칠 커밋이 없던 과목도 마지막 수업은 바로 문제가 생긴다(학생 「오늘 복습」도 14일 안의 수업을 올린다).
- 저장은 하지 않는다. 만든 문제와 새 출제 범위 기록을 돌려주면 Django 가 practice 스키마에 넣는다.
- 한 날짜가 실패하면 거기서 멈추고, 그 앞까지의 결과와 기록을 돌려준다(다음 실행이 실패한 날부터 다시).
"""

from __future__ import annotations

import time
from datetime import date as Date
from datetime import timedelta
from typing import Any, Protocol

from study_notes.git_tools import ChangedFile
from study_notes.practice.build import build_practice_set
from study_notes.practice.generate import practice_model_name
from study_notes.practice.increments import DAY_QUOTA, FileCoverage, plan_day
from study_notes.practice.runner import Runner

FIRST_RUN_DAYS = 14
MAX_TITLE_TOPICS = 3


class LessonRepo(Protocol):
    """RepoCache 중 여기서 쓰는 것 — 테스트가 가짜로 바꿔 끼운다"""

    def sync(self) -> str: ...
    def recent_lesson_dates(self, prefixes: list[str]) -> list[str]: ...
    def changed_files_on(self, date: str, prefixes: list[str]) -> tuple[list[str], list[ChangedFile]]: ...
    def read_file(self, commit: str, path: str) -> str: ...


def coverage_from_json(data: dict[str, Any] | None) -> tuple[dict[str, FileCoverage], dict[str, int]]:
    """practice.coverage.data — daily.py --coverage 파일과 같은 모양 {files: [...], days: {날짜: 문제 수}}"""
    data = data or {}
    files = {item["path"]: FileCoverage.from_json(item) for item in data.get("files", [])}
    return files, {k: int(v) for k, v in (data.get("days") or {}).items()}


def coverage_to_json(files: dict[str, FileCoverage], days: dict[str, int]) -> dict[str, Any]:
    return {"files": [c.to_json() for c in files.values()], "days": days}


def dates_to_run(lesson_dates: list[str], days: dict[str, int], today: str) -> list[str]:
    """자동 출제할 수업 날짜(오래된 날부터). lesson_dates 는 커밋이 있던 날 전부.

    언제나 최근 FIRST_RUN_DAYS 일 안에서만 — 강사가 지난 날짜를 골라 만든 뒤에도(run_source 의 dates)
    자동 출제가 그 날부터 오늘까지 과목 전체를 메우지 않게."""
    since = (Date.fromisoformat(today) - timedelta(days=FIRST_RUN_DAYS - 1)).isoformat()
    recent = [d for d in sorted(set(lesson_dates)) if since <= d <= today]
    done = [d for d in sorted(days) if d <= today]
    if done:
        return [d for d in recent if d >= done[-1]]  # 마지막 날도 다시 — 늦은 커밋
    return recent[-1:]


def nothing_to_do(lesson_dates: list[str], today: str) -> str:
    """자동 출제할 날이 없을 때 강사에게 보일 이유"""
    past = [d for d in lesson_dates if d <= today]
    if not past:
        return "아직 수업 파일(.ipynb · .py · .md)이 올라온 날이 없어요."
    return (
        f"최근 {FIRST_RUN_DAYS}일 안에 수업이 없어 자동 출제 대상이 아니에요(마지막 수업 {past[-1]}). "
        "「지금 만들기」에서 날짜를 골라 만들 수 있어요."
    )


def set_title(problems: list[dict[str, Any]]) -> str:
    topics: list[str] = []
    for p in problems:
        topic = str(p.get("topic") or "").strip()
        if topic and topic not in topics:
            topics.append(topic)
    return " · ".join(topics[:MAX_TITLE_TOPICS])


def run_source(
    repo: LessonRepo,
    *,
    source_title: str,
    prefixes: list[str],
    coverage: dict[str, Any] | None,
    today: str,
    runner: Runner,
    dates: list[str] | None = None,
) -> dict[str, Any]:
    """저장소 하나 — {sets: [{lessonDate, dayLabel, title, files, model, problems}], coverage, error, note}

    dates — 강사가 「지금 만들기」에서 고른 날짜. 없으면 자동(dates_to_run). 고른 날짜도 이미 출제한 셀은 다시 내지 않는다."""
    repo.sync()
    files_cov, days = coverage_from_json(coverage)
    lesson_dates = sorted(repo.recent_lesson_dates(prefixes))
    sets: list[dict[str, Any]] = []
    error = ""
    if dates:
        todo = [d for d in sorted(set(dates)) if d in lesson_dates and d <= today]
        note = "" if todo else "고른 날짜에 수업 파일이 없어요."
    else:
        todo = dates_to_run(lesson_dates, days, today)
        note = "" if todo else nothing_to_do(lesson_dates, today)
    for day in todo:
        already = days.get(day, 0)
        _shas, changed = repo.changed_files_on(day, prefixes)
        files = [(f.path, f.commit, repo.read_file(f.commit, f.path)) for f in changed]
        plan = plan_day(day, files, files_cov, quota=max(0, DAY_QUOTA - already))
        if plan.targets:
            started = time.monotonic()
            try:
                result = build_practice_set(
                    scope_label=f"{day} 수업 — 새로 진행한 부분",
                    materials=plan.materials(),
                    runner=runner,
                    focus_note=plan.focus_note(),
                    kind_counts=plan.kind_counts(),
                )
            except Exception as exc:  # noqa: BLE001 — 이 날부터 다음 실행에 다시
                error = f"{day} 출제 실패: {str(exc)[:300]}"
                break
            problems = [p.to_json() for p in result.problems]
            if problems:
                sets.append({
                    "lessonDate": day,
                    "dayLabel": f"{source_title} {lesson_dates.index(day) + 1}일차",
                    "title": set_title(problems),
                    "files": [f.path for f in plan.targets],
                    "model": practice_model_name(),
                    "problems": problems,
                    "usage": vars(result.usage),
                    "seconds": round(time.monotonic() - started, 1),
                })
            days[day] = already + len(problems)
        elif day not in days:
            days[day] = already
        files_cov = plan.coverage_after(files_cov)
    if todo and not sets and not error:
        note = "고른 날짜의 수업 내용은 이미 출제했어요." if dates else "새로 올라온 수업 내용이 없었어요."
    return {"sets": sets, "coverage": coverage_to_json(files_cov, days), "error": error, "note": note}
