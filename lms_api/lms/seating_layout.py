"""cohort_seating 한 줄(기수당 강의실 하나, layout jsonb)을 다루는 도움 함수.

layout 모양(ETL 이 Firestore 강의실 문서를 옮긴 그대로):
    {"rows", "cols", "cells": [{row, col, type, seatId, label, groupId}], "roomNumber",
     "assignments": {좌석번호: 학생 firebase_uid}, "sourceRoomId", "maxStudents", "updatedAt", "updatedBy"}

화면(lms_react data/bootstrap.ts mapSeating)은 강의실 · 칸 · 배치 · 좌석을 따로 받는 모양을 기대하므로
seating_payload 가 한 줄을 그 네 목록으로 편다. 강의실 id 는 sourceRoomId(없으면 seating-<기수 코드>)다.
"""

from __future__ import annotations

import json

from lms.jsonutil import jsonable


def parse_layout(value) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


def room_id(layout: dict, cohort_code: str) -> str:
    return str(layout.get("sourceRoomId") or f"seating-{cohort_code}")


def seat_ids(cells: list) -> set[str]:
    return {str(c.get("seatId") or "") for c in cells if c.get("type") == "seat" and c.get("seatId")}


def seating_payload(rows: list[dict], code_by_pk: dict) -> dict:
    """cohort_seating 줄들을 bootstrap 의 seatingRooms · seatingCells · seatingAssignments · seatAssignments 로 편다."""
    rooms, cells, assignments, seats = [], [], [], []
    published: dict[str, str] = {}
    for row in rows:
        layout = parse_layout(row.get("layout"))
        code = code_by_pk.get(row["cohort_id"], str(row["cohort_id"]))
        rid = room_id(layout, code)
        updated = jsonable(row.get("updated_at"))
        rooms.append({
            "id": rid,
            "pk": rid,
            "cohortId": code,
            "rows": int(layout.get("rows") or 0),
            "cols": int(layout.get("cols") or 0),
            "roomNumber": row.get("room_number") or layout.get("roomNumber"),
            "createdAt": updated,
            "updatedAt": updated,
        })
        cell_by_seat = {}
        for c in layout.get("cells") or []:
            kind = str(c.get("type") or "")
            if kind in ("", "empty"):
                continue  # 빈 칸은 화면이 rows×cols 로 채운다
            pk = f"{rid}:{c.get('row')}_{c.get('col')}"
            cells.append({
                "pk": pk,
                "roomId": rid,
                "seatId": str(c.get("seatId") or ""),
                "row": int(c.get("row") or 0),
                "col": int(c.get("col") or 0),
                "label": str(c.get("label") or ""),
                "type": kind,
                "groupId": c.get("groupId"),
            })
            if kind == "seat" and c.get("seatId"):
                cell_by_seat[str(c["seatId"])] = pk
        is_published = bool(row.get("published"))
        assignments.append({
            "roomId": rid,
            "status": "published" if is_published else "draft",
            "publishedAt": updated if is_published else None,
            "updatedAt": updated,
        })
        for seat_id, uid in (layout.get("assignments") or {}).items():
            if str(seat_id) in cell_by_seat and uid:
                seats.append({"roomId": rid, "cellId": cell_by_seat[str(seat_id)], "userId": str(uid)})
        if is_published:
            published[code] = rid
    return {
        "seatingRooms": rooms,
        "seatingCells": cells,
        "seatingAssignments": assignments,
        "seatAssignments": seats,
        "publishedSeatingRooms": published,
    }
