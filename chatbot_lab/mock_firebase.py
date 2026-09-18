"""Firestore 모양의 원시 fixture를 운영 loader 반환 구조로 변환한다."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Callable

from chatbot.unit_period import calculate_unit_period_context

FIXTURE_PATH = Path(__file__).with_name("fixtures") / "mock_firebase.json"


def _items(
    documents: dict[str, Any], predicate: Callable[[dict[str, Any]], bool] = lambda _item: True,
) -> dict[str, Any]:
    return {
        "items": [
            {"id": document_id, **document}
            for document_id, document in documents.items()
            if predicate(document)
        ],
        "truncated": False,
    }


def load_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _unit_period(fixture: dict[str, Any], cohort: dict[str, Any], uid: str) -> dict[str, Any]:
    course = cohort["document"]
    sheets = list(cohort.get("curriculumSheets", {}).values())
    latest_sheet = max(sheets, key=lambda item: item.get("uploadedAt", ""), default={})
    scheduled_dates = {
        date.fromisoformat(row["dateLabel"])
        for row in latest_sheet.get("rows", [])
        if row.get("dateLabel")
    }
    attendance_records = {
        date.fromisoformat(item["dateKey"]): item["status"]
        for item in cohort.get("attendances", {}).values()
        if item.get("userId") == uid and item.get("dateKey") and item.get("status")
    }
    return calculate_unit_period_context(
        date.fromisoformat(course["startDate"]),
        date.fromisoformat(course["endDate"]),
        today=date.fromisoformat(fixture["today"]),
        scheduled_dates=scheduled_dates,
        attendance_records=attendance_records,
    )


def load_mock_student_context(
    uid: str, cohort_id: str, scopes: list[str], _query: str,
) -> dict[str, Any]:
    """Firebase 접속 없이 선택된 scope만 실제 loader와 같은 외형으로 반환한다."""
    fixture = load_fixture()
    uid = uid or fixture["active_student_uid"]
    cohort_id = cohort_id or fixture["active_cohort_id"]
    if cohort_id.isdigit():
        cohort_id = f"cohort_{cohort_id}"
    collections = fixture["collections"]
    user = collections["users"].get(uid, {})
    cohort = collections["cohorts"].get(cohort_id, {})
    data: dict[str, Any] = {}

    if "student_private" in scopes:
        mine = lambda item: item.get("userId") == uid
        data["student_private"] = {
            "profile": {"id": uid, **user},
            "todos": _items(cohort.get("todos", {}), mine),
            "attendances": _items(cohort.get("attendances", {}), mine),
            "assignment_submissions": _items(cohort.get("assignmentSubmissions", {}), mine),
            "user_progress": {"id": uid, **cohort.get("userProgress", {}).get(uid, {})},
            "unit_period_context": _unit_period(fixture, cohort, uid),
        }
    if "cohort_shared" in scopes:
        data["cohort_shared"] = {
            "cohort": {"id": cohort_id, **cohort.get("document", {})},
            "assignments": _items(cohort.get("assignments", {})),
            "schedules": _items(cohort.get("schedules", {})),
        }
    for file_scope in ("curriculum_files", "material_files", "record_files", "assignment_files"):
        if file_scope in scopes:
            data[file_scope] = {"items": [], "truncated": False}

    return {
        "cohort": cohort_id,
        "as_of": f"{fixture['today']}T12:00:00+09:00",
        "requested_scopes": list(dict.fromkeys(scopes)),
        "data": data,
        "errors": {},
        "fixture": True,
    }
