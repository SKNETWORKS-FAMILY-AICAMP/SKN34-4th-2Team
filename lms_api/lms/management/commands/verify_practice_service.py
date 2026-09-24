"""Transactional practice smoke test against the explicitly selected RDS database."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from lms.practice_service import (
    create_personal_set,
    get_coverage,
    insert_problems,
    practice_snapshot,
    record_attempt,
    report_problem,
    review_problem,
    save_coverage,
)


class Command(BaseCommand):
    help = "Rollback-only practice service smoke test on lms_migration_replay_20260923"

    def handle(self, *args, **options):
        with connection.cursor() as cur:
            cur.execute("SELECT current_database(), current_user")
            target = cur.fetchone()
        if target != ("lms_migration_replay_20260923", "project_admin"):
            raise CommandError(f"Unexpected database identity: {target!r}")

        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("SELECT id, code FROM cohorts ORDER BY id LIMIT 1")
                cohort = cur.fetchone()
                if not cohort:
                    raise CommandError("No cohort available for rollback-only smoke test")
                cohort_id, cohort_code = cohort
                token = uuid4().hex
                users = []
                for role in ("student", "student", "instructor"):
                    cur.execute(
                        """INSERT INTO users
                           (firebase_uid, email, password, display_name, role, cohort_id,
                            is_active, must_change_password, mileage_balance, social_links)
                           VALUES (%s, %s, %s, %s, %s, %s, true, false, 0, '{}'::jsonb) RETURNING id""",
                        [f"practice-check-{token}-{len(users)}", f"practice-{token}-{len(users)}@example.invalid",
                         "!", "Practice check", role, cohort_id],
                    )
                    users.append({"id": cur.fetchone()[0], "role": role, "cohort_id": cohort_id})
                learner, other, instructor = users
                problem = {"kind": "code_scratch", "topic": "python", "prompt": "print(1)"}
                set_id = create_personal_set(
                    cur, learner, origin="file", legacy_id=f"practice-check-{token}",
                    source_title="smoke", lesson_date=date.today(),
                    day_label="Smoke", title="Smoke", files=["smoke.py"],
                    generation_model="smoke", problems=[problem],
                )
                key = f"practice-check-{token}"
                own = practice_snapshot(cur, learner, [cohort_code])
                assert len(own["practiceSets"]) == 1
                assert own["practiceSets"][0]["problems"][0]["kind"] == "code_scratch"
                assert practice_snapshot(cur, other, [cohort_code])["practiceSets"] == []
                record_attempt(cur, learner, {"setId": key, "index": 0, "passed": False})
                record_attempt(cur, learner, {"setId": key, "index": 0, "passed": True})
                report_problem(cur, learner, {"setId": key, "index": 0, "reason": "unclear", "note": "test"})
                public_key = f"practice-public-{token}"
                cur.execute(
                    """INSERT INTO practice_sets
                       (legacy_id, cohort_id, origin, source_title, lesson_date, day_label,
                        title, source_files, generation_model, created_at)
                       VALUES (%s, %s, 'lesson', 'smoke', %s, 'Smoke', 'Smoke', '[]'::jsonb,
                               'smoke', now()) RETURNING id""",
                    [public_key, cohort_id, date.today()],
                )
                insert_problems(cur, cur.fetchone()[0], [problem])
                review_problem(cur, instructor, {"setId": public_key, "index": 0, "decision": "kept"})
                save_coverage(cur, cohort_id, "smoke", {"smoke.py": 1})
                assert get_coverage(cur, cohort_id, "smoke") == {"smoke.py": 1}
                own = practice_snapshot(cur, learner, [cohort_code])
                assert own["practiceAttempts"][0]["tries"] == 2
                assert own["practiceAttempts"][0]["passed"] is True
                assert len(own["practiceReports"]) == 1
                assert practice_snapshot(cur, instructor, [cohort_code])["practiceReviews"][0]["decision"] == "kept"
                cur.execute("SELECT count(*) FROM practice_problems WHERE problem_set_id = %s", [set_id])
                assert cur.fetchone()[0] == 1
            transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS("Practice service smoke passed; all test rows rolled back."))
