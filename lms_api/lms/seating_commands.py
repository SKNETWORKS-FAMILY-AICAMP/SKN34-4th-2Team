"""좌석 배치 쓰기 — 강의실 틀 · 강의실별 배치 · 프로젝트 팀.

React 관리자 좌석 화면(features/seating/AdminSeatingScreen.tsx)이 /command 로 부른다.
commands.OPS 에 SEATING_OPS 를 더해 등록한다.

규칙(ETL 로 옮긴 Firestore 데이터와 같게):
- seating_cells 에는 빈 칸을 두지 않는다. 좌석은 seat_id 가 번호("1"…), 강사석 · 출입문은 "행_열".
- 화면이 만든 강의실 · 팀 id 는 legacy_id 에 넣는다. bootstrap 이 공개 id 로 legacy_id 를 쓰므로 화면의 id 가 그대로 이어진다.
"""

from __future__ import annotations

from lms.commands import _one, _require_staff, resolve_cohort, resolve_row
from lms.permissions import can_access_cohort


def _cohort_for(cur, user, cohort_key) -> int:
    cohort_id = resolve_cohort(cur, cohort_key, user)
    if cohort_id is None or not can_access_cohort(user, cohort_id):
        raise PermissionError("cohort")
    return cohort_id


def _room(cur, user, room_key):
    room = resolve_row(cur, "seating_rooms", room_key)
    if not room:
        raise KeyError("room")
    if not can_access_cohort(user, room["cohort_id"]):
        raise PermissionError("cohort")
    return room


def _user_ids(cur, uids) -> dict[str, int]:
    uids = [str(u) for u in uids if u]
    if not uids:
        return {}
    cur.execute("SELECT firebase_uid, id FROM users WHERE firebase_uid = ANY(%s)", [uids])
    return {uid: pk for uid, pk in cur.fetchall()}


def _write_assignments(cur, user, room: dict, assignments: dict, status: str) -> None:
    """강의실 한 곳의 배치를 통째로 갈아 끼운다. 확정이면 같은 기수의 다른 확정은 작성 중으로 내린다."""
    room_id = room["id"]
    status = "published" if status == "published" else "draft"
    if status == "published":
        cur.execute(
            """UPDATE seating_assignments SET status = 'draft'
               FROM seating_rooms r
               WHERE seating_assignments.room_id = r.id AND r.cohort_id = %s
                 AND seating_assignments.room_id <> %s AND seating_assignments.status = 'published'""",
            [room["cohort_id"], room_id],
        )
    cur.execute(
        f"""INSERT INTO seating_assignments (room_id, status, published_at, published_by, updated_at, updated_by)
            VALUES (%s, %s, {'now()' if status == 'published' else 'NULL'}, %s, now(), %s)
            ON CONFLICT (room_id) DO UPDATE SET
              status = EXCLUDED.status,
              published_at = COALESCE(EXCLUDED.published_at, seating_assignments.published_at),
              published_by = COALESCE(EXCLUDED.published_by, seating_assignments.published_by),
              updated_at = now(), updated_by = EXCLUDED.updated_by""",
        [room_id, status, user["id"] if status == "published" else None, user["id"]],
    )
    if status == "published":
        cur.execute("UPDATE cohorts SET published_seating_room_id = %s WHERE id = %s", [room_id, room["cohort_id"]])

    cur.execute("DELETE FROM seat_assignments WHERE room_id = %s", [room_id])
    cur.execute("SELECT seat_id, id FROM seating_cells WHERE room_id = %s AND type = 'seat'", [room_id])
    cell_by_seat = {seat_id: pk for seat_id, pk in cur.fetchall()}
    users = _user_ids(cur, (assignments or {}).values())
    seen_users: set[int] = set()
    for seat_id, uid in (assignments or {}).items():
        cell_id = cell_by_seat.get(str(seat_id))
        user_id = users.get(str(uid))
        # 없는 좌석 · 없는 학생 · 한 학생 두 자리는 건너뛴다(seat_assignments 의 UNIQUE(room_id, user_id))
        if cell_id is None or user_id is None or user_id in seen_users:
            continue
        seen_users.add(user_id)
        cur.execute(
            "INSERT INTO seat_assignments (room_id, cell_id, user_id) VALUES (%s, %s, %s)",
            [room_id, cell_id, user_id],
        )


def op_save_seating_room(cur, user, p):
    """강의실 틀 저장(없으면 만든다). 틀이 바뀌면 좌석이 새로 매겨지므로, 화면이 자리를 따라 옮긴 배치도 함께 받는다."""
    _require_staff(user)
    cohort_id = _cohort_for(cur, user, p.get("cohortId"))
    room_key = str(p.get("roomId") or "")
    room = resolve_row(cur, "seating_rooms", room_key) if room_key else None
    if room and room["cohort_id"] != cohort_id:
        raise PermissionError("cohort")
    rows, cols = int(p.get("rows") or 0), int(p.get("cols") or 0)
    if room:
        cur.execute(
            """UPDATE seating_rooms SET room_number = %s, rows = %s, cols = %s, updated_by = %s, updated_at = now()
               WHERE id = %s RETURNING *""",
            [p.get("roomNumber"), rows, cols, user["id"], room["id"]],
        )
    else:
        cur.execute(
            """INSERT INTO seating_rooms (legacy_id, cohort_id, room_number, rows, cols, updated_by, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, now(), now()) RETURNING *""",
            [room_key or None, cohort_id, p.get("roomNumber"), rows, cols, user["id"]],
        )
    room = _one(cur)

    cur.execute("DELETE FROM seating_cells WHERE room_id = %s", [room["id"]])
    for c in p.get("cells") or []:
        kind = str(c.get("type") or "")
        if kind not in ("seat", "instructor", "door"):
            continue
        row, col = int(c.get("row") or 0), int(c.get("col") or 0)
        seat_id = str(c.get("seatId") or "") or f"{row}_{col}"
        cur.execute(
            """INSERT INTO seating_cells (room_id, seat_id, row, col, label, type, group_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            [room["id"], seat_id, row, col, c.get("label") or "", kind, c.get("groupId")],
        )

    # 셀을 새로 넣었으니 배치도 새 셀에 다시 잇는다. 배치가 있던 강의실만.
    cur.execute("SELECT status FROM seating_assignments WHERE room_id = %s", [room["id"]])
    existing = cur.fetchone()
    if existing or p.get("assignments"):
        _write_assignments(cur, user, room, p.get("assignments") or {}, existing[0] if existing else "draft")
    return {"ok": True, "id": room.get("legacy_id") or str(room["id"])}


def op_delete_seating_room(cur, user, p):
    _require_staff(user)
    room = _room(cur, user, p.get("roomId"))
    cur.execute(
        "UPDATE cohorts SET published_seating_room_id = NULL WHERE published_seating_room_id = %s", [room["id"]]
    )
    cur.execute("DELETE FROM seating_rooms WHERE id = %s", [room["id"]])


def op_save_seating_assignments(cur, user, p):
    """배치 임시 저장(status draft) 또는 확정(status published)."""
    _require_staff(user)
    room = _room(cur, user, p.get("roomId"))
    _write_assignments(cur, user, room, p.get("assignments") or {}, str(p.get("status") or "draft"))


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
