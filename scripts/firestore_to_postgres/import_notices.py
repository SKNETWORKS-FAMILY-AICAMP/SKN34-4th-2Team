"""Import published Firestore notices without migrating demo users.

Usage: python scripts/firestore_to_postgres/import_notices.py --target-db DB_NAME
       python scripts/firestore_to_postgres/import_notices.py --target-db DB_NAME --apply

The first command previews the source. --apply upserts one cohort and its notices
into an already migrated PostgreSQL database. Scheduled jobs are not activated.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import firebase_admin
import psycopg
from firebase_admin import credentials, firestore

from etl import COHORT_STATUS, as_date, blank, storage_key, ts

ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def source():
    credential_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(ROOT / "secrets" / "firebase-adminsdk.json"),
    )
    credential = credentials.Certificate(credential_path)
    configured_project = os.environ.get("FIREBASE_PROJECT_ID")
    if configured_project and credential.project_id != configured_project:
        raise RuntimeError("Firebase 서비스 계정의 프로젝트 ID가 .env와 다릅니다.")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            credential, {"projectId": configured_project or credential.project_id}
        )
    return firestore.client()


def connect(target_db: str):
    if not os.environ.get("DB_HOST"):
        raise RuntimeError("DB_HOST, DB_USER, DB_PASSWORD가 필요합니다.")
    return psycopg.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        dbname=target_db,
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        sslmode=os.environ.get("DB_SSLMODE", "require"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-db", required=True, help="명시적으로 선택한 PostgreSQL DB")
    parser.add_argument("--cohort", default="cohort_34")
    parser.add_argument("--apply", action="store_true", help="기본값은 읽기 전용 미리보기")
    args = parser.parse_args()
    load_env()

    db = source()
    cohort_ref = db.collection("cohorts").document(args.cohort)
    cohort = cohort_ref.get()
    if not cohort.exists:
        raise RuntimeError(f"Firestore 기수가 없습니다: {args.cohort}")
    cohort_data = cohort.to_dict() or {}
    notices = list(cohort_ref.collection("notices").stream())
    if not notices:
        raise RuntimeError(f"Firestore 공지가 없습니다: {args.cohort}")
    if len({notice.id for notice in notices}) != len(notices):
        raise RuntimeError("공지 legacy ID가 중복됩니다.")
    image_count = sum(bool((n.to_dict() or {}).get("imageUrl")) for n in notices)
    scheduled_count = sum(bool((n.to_dict() or {}).get("scheduledNoticeId")) for n in notices)
    print(f"source_cohort={args.cohort} notices={len(notices)} images={image_count} scheduled_history={scheduled_count}")
    if not args.apply:
        print("preview_only=true")
        return 0

    with connect(args.target_db) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.notices'), to_regclass('public.cohorts')")
            if None in cur.fetchone():
                raise RuntimeError("대상 DB에 Django migration을 먼저 적용해야 합니다.")
            cur.execute(
                """INSERT INTO cohorts
                   (code,name,description,term_number,classroom_name,status,is_active,start_date,end_date,created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name
                   RETURNING id""",
                (
                    args.cohort, cohort_data.get("name") or args.cohort,
                    cohort_data.get("description"), cohort_data.get("termNumber"),
                    cohort_data.get("classroomName"),
                    COHORT_STATUS.get(str(cohort_data.get("status") or "active"), "active"),
                    bool(cohort_data.get("isActive", True)),
                    as_date(cohort_data.get("startDate")), as_date(cohort_data.get("endDate")),
                    ts(cohort_data.get("createdAt")),
                ),
            )
            cohort_id = cur.fetchone()[0]
            for notice in notices:
                data = notice.to_dict() or {}
                image = data.get("imageUrl")
                image_key = storage_key(image)
                if image and not image_key:
                    raise RuntimeError(f"이미지 저장 경로를 해석할 수 없습니다: {notice.id}")
                # Historical author names survive without importing demo user accounts.
                # Old vector counts and scheduled job IDs are projections/automation state.
                cur.execute(
                    """INSERT INTO notices
                       (legacy_id,cohort_id,title,content,author_id,author_name,is_favorite,
                        priority,source,channel_label,discord_message_id,discord_channel_id,
                        discord_channel_type,scheduled_notice_id,image_storage_key,
                        vector_chunk_count,created_at,updated_at)
                       VALUES (%s,%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s,0,%s,%s)
                       ON CONFLICT (legacy_id) DO UPDATE SET
                         cohort_id=EXCLUDED.cohort_id,title=EXCLUDED.title,
                         content=EXCLUDED.content,author_id=NULL,
                         author_name=EXCLUDED.author_name,is_favorite=EXCLUDED.is_favorite,
                         priority=EXCLUDED.priority,source=EXCLUDED.source,
                         channel_label=EXCLUDED.channel_label,
                         discord_message_id=EXCLUDED.discord_message_id,
                         discord_channel_id=EXCLUDED.discord_channel_id,
                         discord_channel_type=EXCLUDED.discord_channel_type,
                         scheduled_notice_id=NULL,image_storage_key=EXCLUDED.image_storage_key,
                         vector_chunk_count=0,created_at=EXCLUDED.created_at,
                         updated_at=EXCLUDED.updated_at""",
                    (
                        notice.id, cohort_id, data.get("title"), data.get("content"),
                        blank(data.get("authorName")),
                        bool(data.get("isFavorite") or data.get("isPinned")),
                        int(data.get("priority") or 0), data.get("source") or "app",
                        data.get("channelLabel"), blank(data.get("discordMessageId")),
                        data.get("discordChannelId"), data.get("discordChannelType"),
                        image_key, ts(data.get("createdAt")), ts(data.get("updatedAt")),
                    ),
                )
            cur.execute(
                "SELECT count(*) FROM notices WHERE cohort_id=%s AND legacy_id IS NOT NULL",
                (cohort_id,),
            )
            target_count = cur.fetchone()[0]
            if target_count != len(notices):
                raise RuntimeError(f"공지 건수 불일치: source={len(notices)}, target={target_count}")
        conn.commit()
    print(f"target_db={args.target_db} notices={target_count} applied=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
