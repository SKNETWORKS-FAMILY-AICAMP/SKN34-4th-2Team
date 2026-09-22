"""Copy Firebase Storage objects to S3 and rewrite Postgres URL columns. Does not delete origin."""

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
    r"https://firebasestorage\.googleapis\.com/v0/b/[^/]+/o/([^?]+)",
    re.I,
)
GS_RE = re.compile(r"^gs://[^/]+/(.+)$")


def _init():
    cred = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(ROOT / "secrets" / "firebase-adminsdk.json"),
    )
    project = os.environ.get("FIREBASE_PROJECT_ID", "skn34-3rd-2team")
    bucket_name = os.environ.get("FIREBASE_STORAGE_BUCKET", "skn34-3rd-2team.firebasestorage.app")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            credentials.Certificate(cred),
            {"projectId": project, "storageBucket": bucket_name},
        )
    return storage.bucket(bucket_name), firestore.client()


def _rewrite_key(name: str, id_to_code: dict[str, str]) -> str:
    parts = name.split("/")
    if len(parts) >= 2 and parts[0] == "cohorts" and parts[1] in id_to_code:
        parts[1] = id_to_code[parts[1]]
    return "/".join(parts)


def _s3_url(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}"


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
    src_bucket, fs = _init()
    dest_name = os.environ.get("S3_BUCKET", "skn34-4th-2team-lms")
    region = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION") or "ap-northeast-2"
    s3 = boto3.client("s3", region_name=region)
    url = os.environ["DATABASE_URL"]
    failed: list[str] = []
    copied = 0
    mapping: dict[str, str] = {}
    id_to_code: dict[str, str] = {}
    with psycopg.connect(url) as conn:
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
            body = blob.download_as_bytes()
            extra: dict = {}
            if blob.content_type:
                extra["ContentType"] = blob.content_type
            s3.put_object(Bucket=dest_name, Key=key, Body=body, **extra)
            mapping[name] = key
            copied += 1
        except Exception as exc:
            code = type(exc).__name__
            err = getattr(exc, "response", None)
            if err is not None:
                try:
                    code = err.get("Error", {}).get("Code", code)
                except Exception:
                    code = type(exc).__name__
            failed.append(f"{name} ({code})")

    def rewrite_value(old: str | None) -> str | None:
        path = _path_from_value(old)
        if not path:
            return old
        key = mapping.get(path) or _rewrite_key(path, id_to_code)
        if key in mapping.values() or path in mapping:
            return _s3_url(dest_name, mapping.get(path, key))
        if path in mapping:
            return _s3_url(dest_name, mapping[path])
        return _s3_url(dest_name, key) if key != path or path in mapping else old

    updates = 0
    with psycopg.connect(url) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, photo_url, photo_storage_path FROM users")
        for uid, photo_url, photo_path in cur.fetchall():
            new_url = rewrite_value(photo_url)
            new_path = mapping.get(photo_path or "", photo_path)
            if photo_path and photo_path in mapping:
                new_path = mapping[photo_path]
            elif photo_path:
                new_path = _rewrite_key(photo_path, id_to_code)
            if new_url != photo_url or new_path != photo_path:
                cur.execute(
                    "UPDATE users SET photo_url=%s, photo_storage_path=%s WHERE id=%s",
                    (new_url, new_path, uid),
                )
                updates += 1
        cur.execute("SELECT cohort_id, full_pdf_url FROM curriculum_pdfs")
        for cid, pdf in cur.fetchall():
            new_url = rewrite_value(pdf)
            if new_url != pdf:
                cur.execute("UPDATE curriculum_pdfs SET full_pdf_url=%s WHERE cohort_id=%s", (new_url, cid))
                updates += 1
        cur.execute("SELECT id, storage_path FROM curriculum_sheets")
        for sid, path in cur.fetchall():
            new_path = mapping.get(path or "") or (_rewrite_key(path, id_to_code) if path else path)
            if new_path != path:
                cur.execute("UPDATE curriculum_sheets SET storage_path=%s WHERE id=%s", (new_path, sid))
                updates += 1
        cur.execute("SELECT id, file_url FROM materials")
        for mid, file_url in cur.fetchall():
            new_url = rewrite_value(file_url)
            if new_url != file_url:
                cur.execute("UPDATE materials SET file_url=%s WHERE id=%s", (new_url, mid))
                updates += 1
        cur.execute("SELECT id, file_urls FROM record_submissions")
        for rid, urls in cur.fetchall():
            urls = list(urls or [])
            rewritten = [rewrite_value(u) or u for u in urls]
            if rewritten != urls:
                cur.execute("UPDATE record_submissions SET file_urls=%s WHERE id=%s", (rewritten, rid))
                updates += 1
        cur.execute("SELECT assignment_id, user_id, file_url FROM assignment_submissions")
        for aid, uid, file_url in cur.fetchall():
            new_url = rewrite_value(file_url)
            if new_url != file_url:
                cur.execute(
                    "UPDATE assignment_submissions SET file_url=%s WHERE assignment_id=%s AND user_id=%s",
                    (new_url, aid, uid),
                )
                updates += 1
        cur.execute("SELECT id, thumbnail_url, thumbnail_path FROM assessments")
        for aid, thumb_url, thumb_path in cur.fetchall():
            new_url = rewrite_value(thumb_url)
            new_path = mapping.get(thumb_path or "", thumb_path)
            if thumb_path and thumb_path in mapping:
                new_path = mapping[thumb_path]
            elif thumb_path:
                new_path = _rewrite_key(thumb_path, id_to_code)
            if new_url != thumb_url or new_path != thumb_path:
                cur.execute(
                    "UPDATE assessments SET thumbnail_url=%s, thumbnail_path=%s WHERE id=%s",
                    (new_url, new_path, aid),
                )
                updates += 1
        cur.execute("SELECT id, image_url FROM notices")
        for nid, image_url in cur.fetchall():
            new_url = rewrite_value(image_url)
            if new_url != image_url:
                cur.execute("UPDATE notices SET image_url=%s WHERE id=%s", (new_url, nid))
                updates += 1
        conn.commit()

    extra = [
        "",
        "## S3 copy",
        "",
        f"- copied={copied}",
        f"- postgres_url_updates={updates}",
        f"- failed={len(failed)}",
        *(f"  - {item}" for item in failed[:200]),
        "",
        "원본 Firebase Storage는 지우지 않았다.",
        "",
    ]
    if REPORT.exists():
        text = REPORT.read_text(encoding="utf-8")
        if "## S3 copy" not in text:
            REPORT.write_text(text.rstrip() + "\n" + "\n".join(extra), encoding="utf-8")
    else:
        REPORT.write_text("# Cutover report\n" + "\n".join(extra), encoding="utf-8")
    print(f"s3_copied={copied}")
    print(f"pg_updates={updates}")
    print(f"s3_failed={len(failed)}")
    for item in failed:
        print(f"fail={item}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
