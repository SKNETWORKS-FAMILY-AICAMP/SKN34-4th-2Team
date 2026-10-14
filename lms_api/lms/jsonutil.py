"""Postgres rows → Flutter/React 가 쓰던 camelCase 문서 모양."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID


def camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


def jsonable(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M") if value.second == 0 and value.microsecond == 0 else value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    return value


def public_row(row: dict, uid_by_pk: dict, code_by_pk: dict) -> dict:
    out = {}
    for key, value in row.items():
        value = jsonable(value)
        if key == "firebase_uid":
            out["uid"] = value
            out["firebaseUid"] = value
            continue
        if key == "legacy_id":
            continue
        if key == "id":
            out["id"] = str(row.get("legacy_id") or value)
            out["pk"] = value
            continue
        if key in ("user_id", "author_id", "created_by", "updated_by", "reviewed_by", "adjusted_by", "published_by", "uploaded_by") and value in uid_by_pk:
            out[camel(key)] = uid_by_pk[value]
            continue
        if key in ("cohort_id",) and value in code_by_pk:
            out["cohortId"] = code_by_pk[value]
            continue
        if key == "code":
            out["code"] = value
            out["cohortId"] = out.get("cohortId") or value
            continue
        out[camel(key)] = value
    if row.get("legacy_id") and "id" not in out:
        out["id"] = row["legacy_id"]
    return out
