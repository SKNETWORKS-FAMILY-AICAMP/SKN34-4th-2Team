"""공부방 · 연습장 — 옛 로컬 Postgres(practice.* · study.*) → 새 표(practice_* · study_*, lms.0006).

Firestore 에 없는 데이터라 etl.py 가 옮기지 못한다. LMS 가 만든 것들이다:
수업 저장소 자동 등록, LMS 에서 만든 노트, 18:30 자동 출제 문제 · 출제 범위, GitHub 조직 연결, 튜터 대화.

etl.py 를 돌린 뒤에 돌린다. 기수는 code, 사람은 firebase_uid, 저장소는 주소(대소문자 · 끝 / · .git 무시)로
새 번호를 찾는다. 이미 있는 것(같은 legacy_id · 같은 저장소 주소 · 같은 세트)은 건너뛴다 — 다시 돌려도 된다.

usage: python migrate_local_study.py --source postgresql://…/lms --target postgresql://…/lms_etl_0925
"""

from __future__ import annotations

import argparse
import re

import psycopg
from psycopg.types.json import Jsonb


def repo_key(url: str | None) -> str:
    return re.sub(r"\.git$", "", (url or "").strip().rstrip("/")).lower()


def rows(conn, sql, args=()):
    cur = conn.execute(sql, args)
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def js(value):
    return None if value is None else Jsonb(value)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="옛 로컬 DB (practice · study 스키마가 있는 곳)")
    ap.add_argument("--target", required=True, help="새 스키마 DB (etl.py 를 돌린 곳)")
    args = ap.parse_args()
    src = psycopg.connect(args.source)
    dst = psycopg.connect(args.target)
    count: dict[str, int] = {}

    def add(name, n=1):
        count[name] = count.get(name, 0) + n

    cohort = {r["code"]: r["id"] for r in rows(dst, "SELECT id, code FROM cohorts")}
    user = {r["firebase_uid"]: r["id"] for r in rows(dst, "SELECT id, firebase_uid FROM users")}
    src_cohort_code = {r["id"]: r["code"] for r in rows(src, "SELECT id, code FROM cohorts")}
    src_user_uid = {r["id"]: r["firebase_uid"] for r in rows(src, "SELECT id, firebase_uid FROM users")}

    # ── 수업 저장소 ───────────────────────────────────────────
    dst_sources = rows(dst, "SELECT id, legacy_id, cohort_id, repo_url FROM study_sources")
    by_key = {(s["cohort_id"], repo_key(s["repo_url"])): s["id"] for s in dst_sources}
    source_map: dict[int, int] = {}  # 옛 study_sources.id → 새 id
    for s in rows(src, "SELECT * FROM study_sources ORDER BY id"):
        cid = cohort.get(src_cohort_code.get(s["cohort_id"]))
        if cid is None:
            add("skip source (기수 없음)")
            continue
        key = (cid, repo_key(s["repo_url"]))
        if key not in by_key:
            new_id = dst.execute(
                """INSERT INTO study_sources (legacy_id, cohort_id, title, repo_url, branch, allowed_prefixes, is_active,
                                             sort_order, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                [s["legacy_id"], cid, s["title"], s["repo_url"], s["branch"] or "main",
                 Jsonb(list(s["allowed_prefixes"] or [])), bool(s["is_active"]), s["sort_order"],
                 s["created_at"], s["updated_at"]],
            ).fetchone()[0]
            by_key[key] = new_id
            add("study_sources")
        source_map[s["id"]] = by_key[key]
    source_by_repo = {(cid, k): sid for (cid, k), sid in by_key.items()}

    # ── 노트 ─────────────────────────────────────────────────
    have_notes = {r["legacy_id"] for r in rows(dst, "SELECT legacy_id FROM study_notes WHERE legacy_id IS NOT NULL")}
    have_scope = {(r["user_id"], r["source_id"], r["scope_key"]) for r in rows(dst, "SELECT user_id, source_id, scope_key FROM study_notes")}
    for n in rows(src, "SELECT * FROM study_notes ORDER BY id"):
        uid = user.get(src_user_uid.get(n["user_id"]))
        sid = source_map.get(n["source_id"])
        if uid is None or (n["legacy_id"] and n["legacy_id"] in have_notes) or (uid, sid, n["scope_key"]) in have_scope:
            continue
        dst.execute(
            """INSERT INTO study_notes (legacy_id, user_id, source_id, status, scope_type, scope_value, scope_key,
                                        report_markdown, review_markdown, error_message, message, files, created_at, updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [n["legacy_id"], uid, sid, n["status"], n["scope_type"], js(n["scope_value"]), n["scope_key"],
             n["report_markdown"], n["review_markdown"], n["error_message"], n["message"], Jsonb(n["files"] or []),
             n["created_at"], n["created_at"]],
        )
        add("study_notes")

    # ── 복습 문제 세트 · 문제 ─────────────────────────────────
    have_sets = {r["legacy_id"]: r["id"] for r in rows(dst, "SELECT id, legacy_id FROM practice_sets")}
    set_map: dict[int, int] = {}
    problem_map: dict[int, int] = {}
    for s in rows(src, "SELECT * FROM practice.sets ORDER BY id"):
        cid = cohort.get(s["cohort_code"])
        if cid is None:
            add("skip set (기수 없음)")
            continue
        if s["legacy_id"] in have_sets:
            set_map[s["id"]] = have_sets[s["legacy_id"]]
            continue
        owner = user.get(s["owner_uid"]) if s.get("owner_uid") else None
        new_id = dst.execute(
            """INSERT INTO practice_sets (legacy_id, cohort_id, owner_id, origin, source_title, lesson_date, day_label,
                                          title, source_files, generation_model, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            [s["legacy_id"], cid, owner, s.get("origin") or "lesson", s["source_title"] or "", s["lesson_date"],
             s["day_label"] or "", s["title"] or "", Jsonb(s["files"] or []), s["model"] or "", s["created_at"]],
        ).fetchone()[0]
        set_map[s["id"]] = new_id
        add("practice_sets")
        for p in rows(src, "SELECT * FROM practice.problems WHERE set_id = %s ORDER BY idx", [s["id"]]):
            pid = dst.execute(
                """INSERT INTO practice_problems (problem_set_id, position, kind, topic, prompt, source_files, explanation,
                       choices, answer_index, starter_code, expected_stdout, blank_answers, reference_solution,
                       hidden_tests, packages)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                [new_id, p["idx"], p["kind"], p["topic"] or "", p["prompt"] or "", Jsonb(p["source_files"] or []),
                 p["explanation"] or "", Jsonb(p["choices"] or []), p["answer_index"], p["starter_code"] or "",
                 p["expected_stdout"] or "", Jsonb(p["blank_answers"] or []), p["reference_solution"] or "",
                 p["hidden_tests"] or "", Jsonb(p["packages"] or [])],
            ).fetchone()[0]
            problem_map[p["id"]] = pid
            add("practice_problems")

    for a in rows(src, "SELECT * FROM practice.attempts"):
        uid, pid = user.get(a["user_uid"]), problem_map.get(a["problem_id"])
        if uid and pid:
            dst.execute(
                """INSERT INTO practice_attempts (user_id, problem_id, passed, tries, answered_at) VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT DO NOTHING""",
                [uid, pid, a["passed"], a["tries"], a["answered_at"]],
            )
            add("practice_attempts")
    for r in rows(src, "SELECT * FROM practice.reports"):
        uid, pid = user.get(r["user_uid"]), problem_map.get(r["problem_id"])
        if uid and pid:
            dst.execute(
                """INSERT INTO practice_reports (user_id, problem_id, reason, note, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                [uid, pid, r["reason"], r["note"] or "", r["created_at"], r["created_at"]],
            )
            add("practice_reports")
    for v in rows(src, "SELECT * FROM practice.reviews"):
        uid, pid = user.get(v["decided_by_uid"]), problem_map.get(v["problem_id"])
        if uid and pid:
            dst.execute(
                """INSERT INTO practice_reviews (problem_id, decision, decided_by_id, decided_at) VALUES (%s,%s,%s,%s)
                   ON CONFLICT DO NOTHING""",
                [pid, v["decision"], uid, v["decided_at"]],
            )
            add("practice_reviews")
    for c in rows(src, "SELECT * FROM practice.coverage"):
        cid = cohort.get(c["cohort_code"])
        if cid:
            dst.execute(
                """INSERT INTO practice_coverage (cohort_id, source_title, data, updated_at) VALUES (%s,%s,%s,%s)
                   ON CONFLICT (cohort_id, source_title) DO NOTHING""",
                [cid, c["source_title"], Jsonb(c["data"] or {}), c["updated_at"]],
            )
            add("practice_coverage")

    # ── 조직 연결 · 자동 출제 설정 · 실행 기록 · 학생 문제 만들기 · 튜터 ──
    for o in rows(src, "SELECT * FROM study.github_owners"):
        cid = cohort.get(o["cohort_code"])
        if cid:
            dst.execute(
                """INSERT INTO study_github_owners (cohort_id, owner, added_by_id, last_synced_at, last_error, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                [cid, o["owner"], user.get(o["added_by_uid"]), o["last_synced_at"], o["last_error"] or "", o["created_at"]],
            )
            add("study_github_owners")
    for s in rows(src, "SELECT * FROM study.practice_settings"):
        sid = source_by_repo.get((cohort.get(s["cohort_code"]), repo_key(s["repo_key"])))
        if sid:
            dst.execute(
                """INSERT INTO study_practice_settings (source_id, enabled, updated_by_id, updated_at) VALUES (%s,%s,%s,%s)
                   ON CONFLICT (source_id) DO NOTHING""",
                [sid, s["enabled"], user.get(s["updated_by_uid"]), s["updated_at"]],
            )
            add("study_practice_settings")
    for r in rows(src, "SELECT * FROM study.practice_runs ORDER BY id"):
        sid = source_by_repo.get((cohort.get(r["cohort_code"]), repo_key(r["repo_key"])))
        if sid:
            dst.execute(
                """INSERT INTO study_practice_runs (source_id, trigger, status, problems, dates, message, started_at, finished_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                [sid, r["trigger"], r["status"], r["problems"] or 0, Jsonb(r["dates"] or []), r["message"] or "",
                 r["started_at"], r["finished_at"]],
            )
            add("study_practice_runs")
    set_by_legacy = {r["legacy_id"]: r["id"] for r in rows(dst, "SELECT id, legacy_id FROM practice_sets")}
    for j in rows(src, "SELECT * FROM study.practice_jobs ORDER BY id"):
        uid, cid = user.get(j["user_uid"]), cohort.get(j["cohort_code"])
        if uid and cid:
            dst.execute(
                """INSERT INTO study_practice_jobs (user_id, cohort_id, origin, label, status, practice_set_id, message,
                                                    created_at, finished_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [uid, cid, j["origin"], j["label"] or "", j["status"], set_by_legacy.get(j["set_legacy_id"]),
                 j["message"] or "", j["created_at"], j["finished_at"]],
            )
            add("study_practice_jobs")
    problem_by_key = {
        (r["legacy_id"], r["position"]): r["id"]
        for r in rows(dst, "SELECT p.id, p.position, s.legacy_id FROM practice_problems p JOIN practice_sets s ON s.id = p.problem_set_id")
    }
    for t in rows(src, "SELECT * FROM study.tutor_turns ORDER BY id"):
        uid = user.get(t["user_uid"])
        if not uid:
            continue
        m = re.fullmatch(r"set:(.+):(\d+)", t["thread_key"] or "")
        pid = problem_by_key.get((m.group(1), int(m.group(2)))) if m else None
        dst.execute(
            """INSERT INTO study_tutor_turns (user_id, problem_id, thread_key, role, text, kind, hint_level, lines, llm, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [uid, pid, t["thread_key"], t["role"], t["text"], t["kind"] or "", t["hint_level"],
             Jsonb(t["lines"] or []), bool(t["llm"]), t["created_at"]],
        )
        add("study_tutor_turns")

    dst.commit()
    for name, n in count.items():
        print(f"{name}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
