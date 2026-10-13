"""예약 출결 안내만 최신 한 건으로 정리한다. 기본은 조회, 적용 전 백업 필수."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from lms.publish import _dicts
from lms.services import SCHEDULED_ATTENDANCE_TITLE, schedule_notice_vector


class Command(BaseCommand):
    help = "기수별 중복 예약 출결 공지를 조회하거나 백업 후 정리합니다."

    def add_arguments(self, parser):
        parser.add_argument("--cohort-id", type=int)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--backup")

    def handle(self, *args, **options):
        if options["apply"] and (not options["backup"] or options["cohort_id"] is None):
            raise CommandError("적용에는 --cohort-id 및 새 --backup 경로가 필요합니다.")
        with transaction.atomic(), connection.cursor() as cur:
            if options["apply"]:
                cur.execute("SELECT pg_advisory_xact_lock(71423, %s)", [options["cohort_id"]])
            cur.execute(
                """SELECT n.*, c.code AS cohort_code FROM notices n JOIN cohorts c ON c.id = n.cohort_id
                   WHERE n.source = 'scheduled' AND btrim(n.title) = %s
                     AND (%s IS NULL OR n.cohort_id = %s)
                   ORDER BY n.cohort_id, n.created_at DESC NULLS LAST, n.id DESC""",
                [SCHEDULED_ATTENDANCE_TITLE, options["cohort_id"], options["cohort_id"]],
            )
            rows = _dicts(cur)
            seen, duplicates = set(), []
            for row in rows:
                if row["cohort_id"] in seen:
                    duplicates.append(row)
                else:
                    seen.add(row["cohort_id"])
                    self.stdout.write(f"cohort={row['cohort_id']} code={row['cohort_code']} keep={row['id']}")
            self.stdout.write(f"matched={len(rows)} duplicates={len(duplicates)}")
            if not options["apply"] or not duplicates:
                return
            # 기존 백업을 덮어쓰지 않는다. 백업 실패 시 트랜잭션도 중단한다.
            with Path(options["backup"]).open("x", encoding="utf-8") as backup:
                json.dump(rows, backup, ensure_ascii=False, default=str, indent=2)
            for row in duplicates:
                cur.execute("DELETE FROM notices WHERE id = %s", [row["id"]])
                schedule_notice_vector(cohort_code=row["cohort_code"], notice_id=row["id"], data=None,
                                       previous_chunk_count=row.get("vector_chunk_count") or 0)
            self.stdout.write(f"deleted={len(duplicates)} backup={options['backup']}")
