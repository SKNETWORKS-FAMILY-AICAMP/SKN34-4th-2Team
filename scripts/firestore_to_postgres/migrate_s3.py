"""One-time Firebase Storage -> S3 copy for the TO-BE schema.

PostgreSQL stores S3 object keys, not provider URLs. The Firebase source is never
deleted by this script.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import unquote

import boto3
import firebase_admin
import psycopg
from firebase_admin import credentials, firestore, storage

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs" / "cutover-report.md"
URL_RE = re.compile(
    r"https://firebasestorage\.googleapis\.com/v0/b/[^/]+/o/([^?]+)", re.I
)
GS_RE = re.compile(r"^gs://[^/]+/(.+)$")


def _init_firebase():
    cred = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(ROOT / "secrets" / "firebase-adminsdk.json"),
    )
    project = os.environ.get("FIREBASE_PROJECT_ID", "skn34-3rd-2team")
    bucket_name = os.environ.get(
        "FIREBASE_STORAGE_BUCKET", "skn34-3rd-2team.firebasestorage.app"
    )
    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            credentials.Certificate(cred),
            {"projectId": project, "storageBucket": bucket_name},
        )
    return storage.bucket(bucket_name), firestore.client()


def _connect_database():
    if os.environ.get("DB_HOST"):
        return psycopg.connect(
            host=os.environ["DB_HOST"],
            port=os.environ.get("DB_PORT", "5432"),
            dbname=os.environ.get("DB_NAME", "postgres"),
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            sslmode=os.environ.get("DB_SSLMODE", "require"),
        )
    return psycopg.connect(os.environ["DATABASE_URL"])


def _rewrite_key(name: str, id_to_code: dict[str, str]) -> str:
    parts = name.split("/")
    if len(parts) >= 2 and parts[0] == "cohorts" and parts[1] in id_to_code:
        parts[1] = id_to_code[parts[1]]
    return "/".join(parts)


def _path_from_value(value: str | None) -> str | None:
    if not value:
        return None
    match = URL_RE.search(value)
    if match:
        return unquote(match.group(1))
    match = GS_RE.match(value)
    if match:
        return match.group(1)
    if "://" not in value:
        return value.lstrip("/")
    return None


def main() -> int:
    src_bucket, fs = _init_firebase()
    dest_name = os.environ.get("AWS_S3_BUCKET") or os.environ.get("S3_BUCKET")
    if not dest_name:
        raise RuntimeError("AWS_S3_BUCKET 환경변수가 필요합니다.")
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if not region:
        raise RuntimeError("AWS_REGION 환경변수가 필요합니다.")

    # Credentials use boto3's normal chain: environment, profile, or IAM role.
    s3 = boto3.client("s3", region_name=region)
    failed: list[str] = []
    copied = 0
    mapping: dict[str, str] = {}
    copied_keys: set[str] = set()
    id_to_code: dict[str, str] = {}

    with _connect_database() as conn:
        for row in conn.execute("SELECT code FROM cohorts"):
            id_to_code[str(row[0])] = str(row[0])
    for cohort in fs.collection("cohorts").stream():
        data = cohort.to_dict() or {}
        code = str(data.get("code") or cohort.id)
        id_to_code[cohort.id] = code
        id_to_code[code] = code

    for blob in src_bucket.list_blobs():
        name = blob.name
        if not name or name.endswith("/"):
            continue
        key = _rewrite_key(name, id_to_code)
        try:
            extra_args = {"ContentType": blob.content_type} if blob.content_type else None
            with blob.open("rb") as source:
                if extra_args:
                    s3.upload_fileobj(source, dest_name, key, ExtraArgs=extra_args)
                else:
                    s3.upload_fileobj(source, dest_name, key)
            mapping[name] = key
            copied_keys.add(key)
            copied += 1
        except Exception as exc:
            code = type(exc).__name__
            response = getattr(exc, "response", None)
            if isinstance(response, dict):
                code = response.get("Error", {}).get("Code", code)
            failed.append(f"{name} ({code})")

    missing_references: list[str] = []

    def canonical_key(value: str | None, reference: str) -> str | None:
        path = _path_from_value(value)
        if not path:
            return None
        key = mapping.get(path) or _rewrite_key(path, id_to_code)
        if key not in copied_keys:
            missing_references.append(f"{reference}: {path}")
        return key

    targets = (
        ("users", "id", "photo_storage_key"),
        ("curriculum_pdfs", "cohort_id", "storage_key"),
        ("curriculum_sheets", "id", "storage_key"),
        ("materials", "id", "storage_key"),
        ("record_submission_files", "id", "storage_key"),
        ("assessments", "id", "thumbnail_storage_key"),
        ("notices", "id", "image_storage_key"),
    )
    updates = 0
    with _connect_database() as conn:
        cur = conn.cursor()
        for table, pk_column, key_column in targets:
            cur.execute(
                f"SELECT {pk_column}, {key_column} FROM {table} "
                f"WHERE {key_column} IS NOT NULL AND {key_column} <> ''"
            )
            for pk, old_value in cur.fetchall():
                new_value = canonical_key(old_value, f"{table}.{pk}")
                if new_value and new_value != old_value:
                    cur.execute(
                        f"UPDATE {table} SET {key_column}=%s WHERE {pk_column}=%s",
                        (new_value, pk),
                    )
                    updates += 1
        conn.commit()

    extra = [
        "",
        "## S3 copy",
        "",
        f"- copied={copied}",
        f"- postgres_key_updates={updates}",
        f"- failed={len(failed)}",
        f"- missing_referenced_objects={len(missing_references)}",
        *(f"  - copy-failure: {item}" for item in failed[:200]),
        *(f"  - missing-reference: {item}" for item in missing_references[:200]),
        "",
        "Firebase Storage 원본은 삭제하지 않았다. DB에는 S3 object key만 저장한다.",
        "",
    ]
    if REPORT.exists():
        text = REPORT.read_text(encoding="utf-8")
        REPORT.write_text(text.rstrip() + "\n" + "\n".join(extra), encoding="utf-8")
    else:
        REPORT.write_text("# Cutover report\n" + "\n".join(extra), encoding="utf-8")

    print(f"s3_copied={copied}")
    print(f"pg_key_updates={updates}")
    print(f"s3_failed={len(failed)}")
    print(f"missing_referenced_objects={len(missing_references)}")
    for item in failed:
        print(f"fail={item}")
    for item in missing_references:
        print(f"missing={item}")
    return 0 if not failed and not missing_references else 1


if __name__ == "__main__":
    raise SystemExit(main())
