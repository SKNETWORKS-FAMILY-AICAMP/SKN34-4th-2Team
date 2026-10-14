"""Rollback-only smoke test for the five new study storage tables."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from lms.practice_service import create_personal_set
from lms.study_feature_store import (
    add_github_owner, add_tutor_turn, claim_practice_run, finish_practice_job,
    finish_practice_run, list_github_owners, practice_job, practice_setting,
    remove_github_owner, set_practice_setting, start_practice_job, tutor_turns,
)


class Command(BaseCommand):
    help = "Rollback-only study storage smoke test on lms_migration_replay_20260923"

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
                for role in ("student", "instructor"):
                    cur.execute(
                        """INSERT INTO users
                           (firebase_uid, email, password, display_name, role, cohort_id,
                            is_active, must_change_password, mileage_balance, social_links)
                           VALUES (%s, %s, '!', 'Study check', %s, %s, true, false, 0, '{}'::jsonb)
                           RETURNING id""",
                        [f"study-check-{token}-{role}", f"study-{token}-{role}@example.invalid",
                         role, cohort_id],
                    )
                    users.append({"id": cur.fetchone()[0], "role": role, "is_active": True,
                                  "cohort_id": cohort_id, "cohort_code": cohort_code})
                learner, instructor = users
                source_key = f"study-check-{token}"
                cur.execute(
                    """INSERT INTO study_sources
                       (legacy_id, cohort_id, title, repo_url, branch, allowed_prefixes, is_active)
                       VALUES (%s, %s, 'Smoke', 'https://github.com/example/study-check',
                               'main', '[]'::jsonb, true) RETURNING id""",
                    [source_key, cohort_id],
                )
                source_id = cur.fetchone()[0]

                owners = add_github_owner(instructor, cohort_code, "SmokeOwner")
                assert len(owners["owners"]) == 1
                assert len(add_github_owner(instructor, cohort_code, "smokeowner")["owners"]) == 1
                owner_id = int(owners["owners"][0]["id"])
                assert list_github_owners(instructor, cohort_code)["owners"][0]["owner"] == "SmokeOwner"
                assert remove_github_owner(instructor, owner_id)["owners"] == []

                assert practice_setting(instructor, source_key)["enabled"] is True
                assert set_practice_setting(instructor, source_key, False)["enabled"] is False
                run_id = claim_practice_run(instructor, source_key, "manual")
                assert run_id is not None
                assert claim_practice_run(instructor, source_key, "manual") is None
                finish_practice_run(run_id, status="done", problems=1, dates=[date.today().isoformat()])
                cur.execute("SELECT source_id, status, problems FROM study_practice_runs WHERE id = %s", [run_id])
                assert cur.fetchone() == (source_id, "done", 1)

                job_id = start_practice_job(learner, origin="file", label="Smoke")
                set_id = create_personal_set(
                    cur, learner, origin="file", legacy_id=f"study-check-set-{token}",
                    source_title="Smoke", lesson_date=date.today(), day_label="Smoke",
                    title="Smoke", files=[], generation_model="smoke", problems=[],
                )
                finish_practice_job(job_id, status="done", set_id=set_id, message="ready")
                assert practice_job(learner, job_id)["setId"] == f"study-check-set-{token}"

                add_tutor_turn(learner, thread_key="cell", role="user", text="help")
                add_tutor_turn(learner, thread_key="cell", role="assistant", text="answer",
                               kind="hint", hint_level=1, lines=[1], llm=False)
                turns = tutor_turns(learner, "cell")
                assert [turn["role"] for turn in turns] == ["user", "assistant"]
                assert turns[1]["lines"] == [1]
            transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS("Study storage smoke passed; all test rows rolled back."))
