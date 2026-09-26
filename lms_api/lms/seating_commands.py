"""좌석 배치 쓰기 — 강의실 틀 · 배치 · 프로젝트 팀.

React 관리자 좌석 화면(features/seating/AdminSeatingScreen.tsx)이 /command 로 부른다.
commands.OPS 에 SEATING_OPS 를 더해 등록한다.

강의실은 기수당 하나다(RDS 스키마 cohort_seating, PK cohort_id). 틀 · 배치 · 확정 여부를 그 한 줄의
layout jsonb 와 published 에 담는다 — 모양은 lms.seating_layout 참고.
- 좌석은 seatId 가 번호("1"…), 강사석 · 출입문은 "행_열". 빈 칸은 저장하지 않는다.
- 화면이 만든 강의실 id 는 layout.sourceRoomId 에 넣어 bootstrap 이 같은 id 로 돌려준다.
- 화면이 만든 팀 id 는 project_teams.legacy_id 에 넣는다.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from lms.commands import _require_staff, resolve_cohort, resolve_row
from lms.permissions import can_access_cohort
from lms.seating_layout import parse_layout, room_id, seat_ids


def _cohort_for(cur, user, cohort_key) -> int:
    cohort_id = resolve_cohort(cur, cohort_key, user)
    if cohort_id is None or not can_access_cohort(user, cohort_id):
        raise PermissionError("cohort")
    return cohort_id


def _find_room(cur, user, room_key) -> tuple[int, dict]:
    """화면의 강의실 id 로 cohort_seating 줄을 잠가 찾는다 → (cohort_id, layout)."""
    key = str(room_key or "")
    cur.execute(
        """SELECT s.cohort_id, s.layout FROM cohort_seating s JOIN cohorts c ON c.id = s.cohort_id
           WHERE s.layout->>'sourceRoomId' = %s OR 'seating-' || c.code = %s
           FOR UPDATE OF s""",
        [key, key],
    )
    row = cur.fetchone()
    if not row:
        raise KeyError("room")
    if not can_access_cohort(user, row[0]):
        raise PermissionError("cohort")
    return row[0], parse_layout(row[1])


def _user_ids(cur, uids) -> dict[str, int]:
    uids = [str(u) for u in uids if u]
    if not uids:
        return {}
    cur.execute("SELECT firebase_uid, id FROM users WHERE firebase_uid = ANY(%s)", [uids])
    return {uid: pk for uid, pk in cur.fetchall()}


def _clean_assignments(cur, assignments: dict, cells: list) -> dict[str, str]:
    """없는 좌석 · 없는 학생 · 한 학생 두 자리는 뺀다."""
    seats = seat_ids(cells)
    known = _user_ids(cur, (assignments or {}).values())
    out: dict[str, str] = {}
    for seat_id, uid in (assignments or {}).items():
        if str(seat_id) in seats and str(uid) in known and str(uid) not in out.values():
            out[str(seat_id)] = str(uid)
    return out


def _write(cur, user, cohort_id: int, layout: dict, published: bool | None = None) -> None:
    """cohort_seating 한 줄을 넣거나 고친다. published 가 None 이면 확정 여부는 그대로(새 줄은 작성 중)."""
    layout["updatedAt"] = datetime.now(timezone.utc).isoformat()
    layout["updatedBy"] = user.get("firebase_uid") or ""
    cur.execute(
        """INSERT INTO cohort_seating (cohort_id, room_number, layout, published, updated_by, updated_at)
           VALUES (%s, %s, %s::jsonb, COALESCE(%s, false), %s, now())
           ON CONFLICT (cohort_id) DO UPDATE SET
             room_number = EXCLUDED.room_number, layout = EXCLUDED.layout,
             published = COALESCE(%s, cohort_seating.published),
             updated_by = EXCLUDED.updated_by, updated_at = now()""",
        [cohort_id, layout.get("roomNumber") or None, json.dumps(layout, ensure_ascii=False),
         published, user["id"], published],
    )


def op_save_seating_room(cur, user, p):
    """강의실 틀 저장(없으면 만든다). 틀이 바뀌면 좌석이 새로 매겨지므로, 화면이 자리를 따라 옮긴 배치도 함께 받는다."""
    _require_staff(user)
    cohort_id = _cohort_for(cur, user, p.get("cohortId"))
    cur.execute("SELECT code FROM cohorts WHERE id = %s", [cohort_id])
    code = cur.fetchone()[0]
    cur.execute("SELECT layout FROM cohort_seating WHERE cohort_id = %s FOR UPDATE", [cohort_id])
    found = cur.fetchone()
    old = parse_layout(found[0]) if found else None
    room_key = str(p.get("roomId") or "")
    if old is not None and room_key and room_key != room_id(old, code):
        raise ValueError("이 기수에는 이미 강의실이 있습니다. 기수당 강의실은 하나입니다.")

    cells = []
    for c in p.get("cells") or []:
        kind = str(c.get("type") or "")
        if kind not in ("seat", "instructor", "door"):
            continue
        row, col = int(c.get("row") or 0), int(c.get("col") or 0)
        cell = {"row": row, "col": col, "type": kind, "label": c.get("label") or "",
                "seatId": str(c.get("seatId") or "") or f"{row}_{col}"}
        if c.get("groupId"):
            cell["groupId"] = c["groupId"]
        cells.append(cell)
    assignments = p["assignments"] if "assignments" in p else (old or {}).get("assignments") or {}
    layout = {
        **(old or {}),
        "rows": int(p.get("rows") or 0),
        "cols": int(p.get("cols") or 0),
        "cells": cells,
        "roomNumber": p.get("roomNumber") or "",
        "assignments": _clean_assignments(cur, assignments, cells),
        "sourceRoomId": room_id(old, code) if old is not None else (room_key or f"seating-{code}"),
    }
    _write(cur, user, cohort_id, layout)
    return {"ok": True, "id": layout["sourceRoomId"]}


def op_delete_seating_room(cur, user, p):
    _require_staff(user)
    cohort_id, _ = _find_room(cur, user, p.get("roomId"))
    cur.execute("DELETE FROM cohort_seating WHERE cohort_id = %s", [cohort_id])


def op_save_seating_assignments(cur, user, p):
    """배치 임시 저장(status draft) 또는 확정(status published). 작성 중이면 학생 화면에서 내려간다."""
    _require_staff(user)
    cohort_id, layout = _find_room(cur, user, p.get("roomId"))
    layout["assignments"] = _clean_assignments(cur, p.get("assignments") or {}, layout.get("cells") or [])
    _write(cur, user, cohort_id, layout, published=str(p.get("status") or "draft") == "published")


def op_replace_project_teams(cur, user, p):
    """프로젝트 팀을 한 번에 갈아 끼운다 — 바뀐 팀은 고치고, 새 팀은 만들고, deleteIds 는 지운다. 팀원도 통째로."""
    _require_staff(user)
    cohort_id = _cohort_for(cur, user, p.get("cohortId"))
    for team_key in p.get("deleteIds") or []:
        team = resolve_row(cur, "project_teams", team_key)
        if team and team["cohort_id"] == cohort_id:
            cur.execute("DELETE FROM project_teams WHERE id = %s", [team["id"]])
    ids = []
    for t in p.get("teams") or []:
        key = str(t.get("id") or "")
        team = resolve_row(cur, "project_teams", key) if key else None
        if team and team["cohort_id"] != cohort_id:
            raise PermissionError("cohort")
        values = [t.get("name") or "", int(t.get("sortOrder") or 0), int(t.get("colorIndex") or 0), user["id"]]
        if team:
            cur.execute(
                """UPDATE project_teams SET name = %s, sort_order = %s, color_index = %s, updated_by = %s, updated_at = now()
                   WHERE id = %s RETURNING id""",
                [*values, team["id"]],
            )
        else:
            cur.execute(
                """INSERT INTO project_teams (legacy_id, cohort_id, name, sort_order, color_index, updated_by, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, now()) RETURNING id""",
                [key or None, cohort_id, *values],
            )
        team_id = cur.fetchone()[0]
        cur.execute("DELETE FROM project_team_members WHERE team_id = %s", [team_id])
        users = _user_ids(cur, t.get("memberIds") or [])
        for uid in t.get("memberIds") or []:
            if uid in users:
                cur.execute(
                    "INSERT INTO project_team_members (team_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    [team_id, users[uid]],
                )
        ids.append(key or str(team_id))
    return {"ok": True, "ids": ids}


SEATING_OPS = {
    "saveSeatingRoom": op_save_seating_room,
    "deleteSeatingRoom": op_delete_seating_room,
    "saveSeatingAssignments": op_save_seating_assignments,
    "replaceProjectTeams": op_replace_project_teams,
}
