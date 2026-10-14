"""Rollback-only smoke test for the FastAPI resume gateway's TO-BE mapping."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


class _NoCommitConnection:
    """Keep gateway commits inside the outer Django rollback-only transaction."""

    def __init__(self, raw):
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, *args, **kwargs):
        return self.raw.execute(*args, **kwargs)

    def commit(self):
        pass


class Command(BaseCommand):
    help = "Rollback-only tailored resume smoke test on lms_migration_replay_20260923"

    def handle(self, *args, **options):
        with connection.cursor() as cur:
            cur.execute("SELECT current_database(), current_user")
            target = cur.fetchone()
        if target != ("lms_migration_replay_20260923", "project_admin"):
            raise CommandError(f"Unexpected database identity: {target!r}")

        repo = Path(__file__).resolve().parents[4]
        sys.path.insert(0, str(repo / "cover_letter_rag"))
        from app.firebase_gateway import FirebaseGateway

        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("SELECT id, code FROM cohorts ORDER BY id LIMIT 1")
                cohort = cur.fetchone()
                if not cohort:
                    raise CommandError("No cohort available for rollback-only smoke test")
                cohort_id, cohort_code = cohort
                token = uuid4().hex
                uid = f"tailoring-check-{token}"
                base_id = f"tailoring-base-{token}"
                cur.execute(
                    """INSERT INTO users (firebase_uid, email, password, display_name, role,
                       cohort_id, is_active, must_change_password, mileage_balance, social_links)
                       VALUES (%s, %s, '!', 'Tailoring check', 'student', %s,
                               true, false, 0, '{}'::jsonb) RETURNING id""",
                    [uid, f"tailoring-{token}@example.invalid", cohort_id],
                )
                user_id = cur.fetchone()[0]
                cur.execute(
                    """INSERT INTO resumes (legacy_id, cohort_id, user_id, title, status,
                       content, is_base_resume, revision_count, created_at, updated_at)
                       VALUES (%s, %s, %s, 'Base', 'writing', '{}'::jsonb,
                               true, 0, now(), now())""",
                    [base_id, cohort_id, user_id],
                )

            gateway = object.__new__(FirebaseGateway)
            gateway._pg = lambda: _NoCommitConnection(connection.connection)
            source = {"job_id": f"job-{token}", "snapshot_hash": f"hash-{token}",
                      "company": "Example", "title": "Engineer"}
            created = gateway.create_tailored_resume(cohort_code, base_id, uid, source)
            tailored_id = created["tailored_resume_id"]
            assert gateway.create_tailored_resume(cohort_code, base_id, uid, source)["tailored_resume_id"] == tailored_id
            assert len(gateway.list_tailored_resumes(cohort_code, base_id, uid)) == 1
            gateway.save_tailored_resume_session(cohort_code, base_id, tailored_id, uid, {"result": {"score": 1}})
            detail = gateway.get_owned_tailored_resume(cohort_code, base_id, tailored_id, uid)
            assert detail["reviewSession"] == {"result": {"score": 1}}, detail
            assert detail["reviewProgress"] == "in_progress"
            assert gateway.list_tailored_resumes(cohort_code, base_id, uid)[0]["reviewProgress"] == "in_progress"
            gateway.save_tailored_resume_session(cohort_code, base_id, tailored_id, uid, {"completed": True})
            assert gateway.get_owned_tailored_resume(cohort_code, base_id, tailored_id, uid)["reviewProgress"] == "completed"
            workspace_id = gateway.promote_tailored_resume(cohort_code, base_id, tailored_id, uid)
            assert gateway.get_owned_tailored_resume(cohort_code, base_id, tailored_id, uid)["workspaceResumeId"] == workspace_id
            other = gateway.create_tailored_resume(
                cohort_code, base_id, uid,
                {**source, "job_id": f"other-job-{token}", "snapshot_hash": f"other-hash-{token}"},
            )
            with connection.cursor() as cur:
                cur.execute("SELECT id FROM resumes WHERE legacy_id = %s",
                            [f"{base_id}/tailored/{tailored_id}"])
                tailored_pk = cur.fetchone()[0]
                cur.execute("SELECT id FROM resumes WHERE legacy_id = %s", [workspace_id])
                workspace_pk = cur.fetchone()[0]
                for index, resume_pk in enumerate((tailored_pk, workspace_pk)):
                    cur.execute(
                        """INSERT INTO resume_ai_reviews
                           (legacy_id, resume_id, user_id, status, payload, created_at)
                           VALUES (%s, %s, %s, 'complete', '{}'::jsonb, now())""",
                        [f"tailoring-check-review-{token}-{index}", resume_pk, user_id],
                    )
                    cur.execute(
                        """INSERT INTO resume_ai_applications
                           (legacy_id, resume_id, user_id, kind, payload, created_at)
                           VALUES (%s, %s, %s, 'apply', '{}'::jsonb, now())""",
                        [f"tailoring-check-application-{token}-{index}", resume_pk, user_id],
                    )
                    cur.execute(
                        """INSERT INTO resume_feedback
                           (legacy_id, resume_id, content, created_at)
                           VALUES (%s, %s, 'Smoke', now()) RETURNING id""",
                        [f"tailoring-check-feedback-{token}-{index}", resume_pk],
                    )
                    feedback_pk = cur.fetchone()[0]
                    cur.execute(
                        """INSERT INTO resume_feedback_reads (resume_id, user_id, feedback_id, read_at)
                           VALUES (%s, %s, %s, now())""",
                        [resume_pk, user_id, feedback_pk],
                    )
                    cur.execute(
                        """INSERT INTO resume_revisions
                           (legacy_id, resume_id, revision_no, content, created_at)
                           VALUES (%s, %s, 1, '{}'::jsonb, now())""",
                        [f"tailoring-check-revision-{token}-{index}", resume_pk],
                    )
            gateway.delete_tailored_resume(cohort_code, base_id, tailored_id, uid)
            with connection.cursor() as cur:
                cur.execute("SELECT count(*) FROM resumes WHERE legacy_id IN (%s, %s)",
                            [f"{base_id}/tailored/{tailored_id}", workspace_id])
                assert cur.fetchone()[0] == 0
                cur.execute("SELECT count(*) FROM resumes WHERE legacy_id IN (%s, %s)",
                            [base_id, f"{base_id}/tailored/{other['tailored_resume_id']}"])
                assert cur.fetchone()[0] == 2
                for table in ("resume_ai_reviews", "resume_ai_applications", "resume_feedback",
                              "resume_feedback_reads", "resume_revisions", "resume_tailorings"):
                    cur.execute(f"SELECT count(*) FROM {table} WHERE resume_id IN (%s, %s)",
                                [tailored_pk, workspace_pk])
                    assert cur.fetchone()[0] == 0, table
            transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS("Tailored resume gateway smoke passed; all test rows rolled back."))
