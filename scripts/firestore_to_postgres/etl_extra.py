"""Incremental ETL for the 3 unmapped collections. Does not DROP schema."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import firebase_admin
import psycopg
from firebase_admin import credentials, firestore
from psycopg import ClientCursor
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parent
EXTRA = ROOT / "schema_extra.sql"
REPORT = ROOT.parents[1] / "docs" / "migration-report.md"


def _init():
    cred = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(ROOT.parents[1] / "secrets" / "firebase-adminsdk.json"),
    )
    project = os.environ.get("FIREBASE_PROJECT_ID", "skn34-3rd-2team")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred), {"projectId": project})
    return firestore.client()


def ts(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    to_dt = getattr(value, "to_datetime", None)
    if callable(to_dt):
        dt = to_dt()
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def dump(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    to_dt = getattr(value, "to_datetime", None)
    if callable(to_dt):
        return to_dt().isoformat()
    if isinstance(value, dict):
        return {str(k): dump(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [dump(v) for v in value]
    return str(value)


def main() -> int:
    url = os.environ["DATABASE_URL"]
    db = _init()
    stats = {
        "job_requirement_profiles_fs": 0,
        "job_requirement_profiles_pg": 0,
        "resume_ai_reviews_fs": 0,
        "resume_ai_reviews_pg": 0,
        "resume_ai_applications_fs": 0,
        "resume_ai_applications_pg": 0,
        "skipped_no_resume": 0,
    }
    with psycopg.connect(url, autocommit=True, cursor_factory=ClientCursor) as conn:
        conn.execute(EXTRA.read_text(encoding="utf-8"))

    with psycopg.connect(url) as conn:
        cur = conn.cursor()
        cur.execute("SELECT legacy_id, id FROM resumes WHERE legacy_id IS NOT NULL")
        resume_map = {row[0]: row[1] for row in cur.fetchall()}
        cur.execute("SELECT firebase_uid, id FROM users WHERE firebase_uid IS NOT NULL")
        user_map = {row[0]: row[1] for row in cur.fetchall()}

        for doc in db.collection("jobRequirementProfiles").stream():
            stats["job_requirement_profiles_fs"] += 1
            data = doc.to_dict() or {}
            cur.execute(
                """INSERT INTO job_requirement_profiles (key, requirements, created_at)
                   VALUES (%s,%s,%s) ON CONFLICT (key) DO UPDATE
                   SET requirements = EXCLUDED.requirements, created_at = COALESCE(EXCLUDED.created_at, job_requirement_profiles.created_at)""",
                (doc.id, Jsonb(dump(data.get("requirements") or [])), ts(data.get("createdAt"))),
            )
            stats["job_requirement_profiles_pg"] += 1

        for cohort in db.collection("cohorts").stream():
            for resume in cohort.reference.collection("resumes").stream():
                targets = [(resume.id, resume.reference)]
                for tailored in resume.reference.collection("tailoredResumes").stream():
                    targets.append((f"{resume.id}/tailored/{tailored.id}", tailored.reference))
                for legacy, ref in targets:
                    pg_resume = resume_map.get(legacy)
                    if pg_resume is None:
                        # parent resume may exist without tailored prefix
                        pg_resume = resume_map.get(legacy.split("/tailored/")[0] if "/tailored/" in legacy else legacy)
                    for review in ref.collection("aiReviews").stream():
                        stats["resume_ai_reviews_fs"] += 1
                        if pg_resume is None:
                            stats["skipped_no_resume"] += 1
                            continue
                        d = review.to_dict() or {}
                        known = {"userId", "fingerprint", "status", "response", "telemetry", "createdAt"}
                        payload = {k: dump(v) for k, v in d.items() if k not in known}
                        cur.execute(
                            """INSERT INTO resume_ai_reviews (legacy_id, resume_id, user_id, fingerprint, status, response, telemetry, payload, created_at)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (legacy_id) DO NOTHING""",
                            (
                                f"{legacy}/{review.id}",
                                pg_resume,
                                user_map.get(d.get("userId") or ""),
                                d.get("fingerprint"),
                                d.get("status"),
                                Jsonb(dump(d.get("response"))) if d.get("response") is not None else None,
                                Jsonb(dump(d.get("telemetry"))) if d.get("telemetry") is not None else None,
                                Jsonb(payload),
                                ts(d.get("createdAt")),
                            ),
                        )
                        stats["resume_ai_reviews_pg"] += cur.rowcount
                    for app in ref.collection("aiApplications").stream():
                        stats["resume_ai_applications_fs"] += 1
                        if pg_resume is None:
                            stats["skipped_no_resume"] += 1
                            continue
                        d = app.to_dict() or {}
                        known = {
                            "userId", "fingerprint", "kind", "before", "after_hash",
                            "response", "source_id", "undoneBy", "createdAt",
                        }
                        payload = {k: dump(v) for k, v in d.items() if k not in known}
                        cur.execute(
                            """INSERT INTO resume_ai_applications (legacy_id, resume_id, user_id, fingerprint, kind, before, after_hash, response, source_id, undone_by, payload, created_at)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (legacy_id) DO NOTHING""",
                            (
                                f"{legacy}/{app.id}",
                                pg_resume,
                                user_map.get(d.get("userId") or ""),
                                d.get("fingerprint"),
                                d.get("kind"),
                                Jsonb(dump(d.get("before"))) if d.get("before") is not None else None,
                                d.get("after_hash") or d.get("afterHash"),
                                Jsonb(dump(d.get("response"))) if d.get("response") is not None else None,
                                d.get("source_id") or d.get("sourceId"),
                                d.get("undoneBy"),
                                Jsonb(payload),
                                ts(d.get("createdAt")),
                            ),
                        )
                        stats["resume_ai_applications_pg"] += cur.rowcount
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM job_requirement_profiles")
        stats["job_requirement_profiles_pg"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM resume_ai_reviews")
        stats["resume_ai_reviews_pg"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM resume_ai_applications")
        stats["resume_ai_applications_pg"] = cur.fetchone()[0]

    extra = [
        "",
        "## 미매핑 3테이블 ETL (증분, DROP 없음)",
        "",
        f"- jobRequirementProfiles FS {stats['job_requirement_profiles_fs']} → job_requirement_profiles PG {stats['job_requirement_profiles_pg']}",
        f"- aiReviews FS {stats['resume_ai_reviews_fs']} → resume_ai_reviews PG {stats['resume_ai_reviews_pg']}",
        f"- aiApplications FS {stats['resume_ai_applications_fs']} → resume_ai_applications PG {stats['resume_ai_applications_pg']}",
        f"- resume 매핑 없어 생략 {stats['skipped_no_resume']}건 (고아 uid 이력서 하위 문서 포함)",
        "",
    ]
    text = REPORT.read_text(encoding="utf-8") if REPORT.exists() else ""
    if "## 미매핑 3테이블 ETL" not in text:
        REPORT.write_text(text.rstrip() + "\n" + "\n".join(extra), encoding="utf-8")
    print(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
