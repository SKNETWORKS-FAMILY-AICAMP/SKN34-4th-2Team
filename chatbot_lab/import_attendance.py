"""사진에서 옮긴 출석 fixture를 실제 학생 Firestore 문서에 안전하게 반영한다.

기본 실행은 dry-run이며, 실제 반영은 ``--write``를 명시해야 한다.
동일 날짜의 기존 문서는 반영 직전에 chatbot_lab/results 아래에 백업한다.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from chatbot.api import _firebase_app


LAB_DIR = Path(__file__).resolve().parent
FIXTURE_PATH = LAB_DIR / "fixtures" / "mock_firebase.json"
RESULTS_DIR = LAB_DIR / "results"


def _json_default(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _source_rows() -> list[dict[str, Any]]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cohort_id = fixture["active_cohort_id"]
    uid = fixture["active_student_uid"]
    rows = fixture["collections"]["cohorts"][cohort_id]["attendances"].values()
    selected = sorted(
        (dict(row) for row in rows if row.get("userId") == uid),
        key=lambda row: row["dateKey"],
    )
    if len(selected) != 19:
        raise RuntimeError(f"출석 fixture는 19건이어야 합니다: {len(selected)}건")
    return selected


def _find_student(db: Any, display_name: str, cohort_id: str) -> tuple[str, dict[str, Any]]:
    query = (
        db.collection("users")
        .where(filter=FieldFilter("displayName", "==", display_name))
        .limit(10)
    )
    matches = []
    for doc in query.stream():
        data = doc.to_dict() or {}
        if (
            data.get("role") == "student"
            and data.get("isActive") is True
            and str(data.get("cohortId") or "") == cohort_id
        ):
            matches.append((doc.id, data))
    if len(matches) != 1:
        summary = [
            {"uid": uid, "role": data.get("role"), "cohortId": data.get("cohortId")}
            for uid, data in matches
        ]
        raise RuntimeError(
            f"{display_name!r} 활성 학생을 {cohort_id}에서 정확히 1명 찾지 못했습니다: "
            f"{json.dumps(summary, ensure_ascii=False)}"
        )
    return matches[0]


def _payload(row: dict[str, Any], uid: str, display_name: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "userId": uid,
        "userDisplayName": display_name,
        "dateKey": row["dateKey"],
        "status": row["status"],
        "type": "status",
        "statusSource": "manual",
        "sourceLabel": row.get("sourceLabel"),
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    if row.get("checkIn"):
        payload["checkInTime"] = row["checkIn"]
    else:
        payload["checkInTime"] = firestore.DELETE_FIELD
    if row.get("checkOut"):
        payload["checkOutTime"] = row["checkOut"]
    else:
        payload["checkOutTime"] = firestore.DELETE_FIELD
    if row.get("officialLeaveType"):
        payload["officialLeaveUsed"] = True
        payload["officialLeaveType"] = row["officialLeaveType"]
    else:
        payload["officialLeaveUsed"] = firestore.DELETE_FIELD
        payload["officialLeaveType"] = firestore.DELETE_FIELD
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="문성호")
    parser.add_argument("--cohort", default="cohort_34")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    app = _firebase_app()
    db = firestore.client(app=app)
    uid, profile = _find_student(db, args.name, args.cohort)
    rows = _source_rows()
    collection = db.collection("cohorts").document(args.cohort).collection("attendances")

    existing: dict[str, Any] = {}
    for row in rows:
        doc_id = f"{uid}_{row['dateKey']}"
        snapshot = collection.document(doc_id).get()
        if snapshot.exists:
            existing[doc_id] = snapshot.to_dict()

    preview = {
        "mode": "write" if args.write else "dry-run",
        "uid": uid,
        "displayName": profile.get("displayName"),
        "cohortId": profile.get("cohortId"),
        "targetCount": len(rows),
        "existingTargetCount": len(existing),
        "dates": [row["dateKey"] for row in rows],
    }
    print(json.dumps(preview, ensure_ascii=False))
    if not args.write:
        return

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = RESULTS_DIR / f"attendance_backup_{uid}_{stamp}.json"
    backup_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )

    batch = db.batch()
    for row in rows:
        doc_id = f"{uid}_{row['dateKey']}"
        batch.set(collection.document(doc_id), _payload(row, uid, args.name), merge=True)
    batch.commit()

    verified = 0
    for row in rows:
        doc_id = f"{uid}_{row['dateKey']}"
        data = collection.document(doc_id).get().to_dict() or {}
        if data.get("status") == row["status"]:
            verified += 1
    print(
        json.dumps(
            {"written": len(rows), "verified": verified, "backup": str(backup_path)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
