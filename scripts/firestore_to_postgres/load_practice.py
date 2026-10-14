"""복습 문제 세트를 practice 스키마에 넣는다.

    # 세트 JSON 파일(하나 또는 목록)
    python scripts/firestore_to_postgres/load_practice.py --cohort cohort_34 sets.json
    # 화면 데모 세트(lms_react/src/data/practiceSeed.ts) 그대로
    python scripts/firestore_to_postgres/load_practice.py --cohort cohort_34 --from-seed
    # 출제 범위 기록도 함께(study_notes/practice/daily.py --coverage 파일)
    python scripts/firestore_to_postgres/load_practice.py --cohort cohort_34 --coverage multimodal=cov.json

세트 JSON 모양은 화면의 PracticeSet 과 같다: {id, sourceTitle, lessonDate, dayLabel, title, files, model, problems:[...]}.
문제 모양은 PracticeProblem.to_json() 과 같다.

같은 세트 id 를 다시 넣으면 세트 정보와 문제를 고친다. 문제는 세트 안 순서(idx)로 맞춰 고치고,
그 순서의 풀이 기록 · 신고는 그대로 둔다. 새 세트에 없는 뒤쪽 문제는 지운다(기록도 함께 지워진다).

DATABASE_URL 은 환경 변수 또는 저장소 루트 .env 에서 읽는다. 스키마는 practice_schema.sql 로 먼저 만든다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[2]
SEED_TS = ROOT / "lms_react" / "src" / "data" / "practiceSeed.ts"


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    env = ROOT / ".env"
    if env.exists():
        for raw in env.read_text(encoding="utf-8").splitlines():
            if raw.startswith("DATABASE_URL="):
                return raw.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit("DATABASE_URL 이 없습니다(.env 또는 환경 변수)")


def sets_from_seed() -> list[dict]:
    """practiceSeed.ts 의 `const sets: SeedSet[] = [...];` 는 JSON 그대로다."""
    text = SEED_TS.read_text(encoding="utf-8")
    m = re.search(r"const sets: SeedSet\[\] = (\[.*?\n\]);", text, re.S)
    if not m:
        raise SystemExit(f"{SEED_TS} 에서 세트 목록을 찾지 못했습니다")
    return json.loads(m.group(1))


def load_sets(paths: list[str]) -> list[dict]:
    out: list[dict] = []
    for p in paths:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        out.extend(data if isinstance(data, list) else [data])
    return out


def upsert_set(cur, cohort: str, s: dict) -> int:
    cur.execute(
        """INSERT INTO practice.sets (legacy_id, cohort_code, source_title, lesson_date, day_label, title, files, model)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (legacy_id) DO UPDATE SET
             cohort_code = EXCLUDED.cohort_code, source_title = EXCLUDED.source_title,
             lesson_date = EXCLUDED.lesson_date, day_label = EXCLUDED.day_label, title = EXCLUDED.title,
             files = EXCLUDED.files, model = EXCLUDED.model
           RETURNING id""",
        [s["id"], cohort, s.get("sourceTitle", ""), s["lessonDate"], s.get("dayLabel", ""), s.get("title", ""),
         Jsonb(s.get("files") or []), s.get("model", "")],
    )
    set_id = cur.fetchone()[0]
    problems = s.get("problems") or []
    for idx, p in enumerate(problems):
        cur.execute(
            """INSERT INTO practice.problems (set_id, idx, kind, topic, prompt, source_files, explanation, choices,
                 answer_index, starter_code, expected_stdout, blank_answers, reference_solution, hidden_tests, packages)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (set_id, idx) DO UPDATE SET
                 kind = EXCLUDED.kind, topic = EXCLUDED.topic, prompt = EXCLUDED.prompt,
                 source_files = EXCLUDED.source_files, explanation = EXCLUDED.explanation, choices = EXCLUDED.choices,
                 answer_index = EXCLUDED.answer_index, starter_code = EXCLUDED.starter_code,
                 expected_stdout = EXCLUDED.expected_stdout, blank_answers = EXCLUDED.blank_answers,
                 reference_solution = EXCLUDED.reference_solution, hidden_tests = EXCLUDED.hidden_tests,
                 packages = EXCLUDED.packages""",
            [set_id, idx, p["kind"], p.get("topic", ""), p.get("prompt", ""), Jsonb(p.get("sourceFiles") or []),
             p.get("explanation", ""), Jsonb(p.get("choices") or []), p.get("answerIndex"),
             p.get("starterCode", ""), p.get("expectedStdout", ""), Jsonb(p.get("blankAnswers") or []),
             p.get("referenceSolution", ""), p.get("hiddenTests", ""), Jsonb(p.get("packages") or [])],
        )
    cur.execute("DELETE FROM practice.problems WHERE set_id = %s AND idx >= %s", [set_id, len(problems)])
    return len(problems)


def main() -> int:
    parser = argparse.ArgumentParser(description="복습 문제 세트를 practice 스키마에 넣는다")
    parser.add_argument("files", nargs="*", help="세트 JSON 파일")
    parser.add_argument("--cohort", required=True, help="cohorts.code (예: cohort_34)")
    parser.add_argument("--from-seed", action="store_true", help="lms_react 데모 세트(practiceSeed.ts)를 넣는다")
    parser.add_argument("--coverage", action="append", default=[], metavar="저장소=파일",
                        help="출제 범위 기록 JSON (예: multimodal=cov.json)")
    args = parser.parse_args()

    sets = (sets_from_seed() if args.from_seed else []) + load_sets(args.files)
    if not sets and not args.coverage:
        parser.error("넣을 세트가 없습니다(파일 또는 --from-seed)")

    with psycopg.connect(database_url()) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('practice.sets')")
        if cur.fetchone()[0] is None:
            raise SystemExit("practice 스키마가 없습니다 — practice_schema.sql 을 먼저 실행하세요")
        cur.execute("SELECT 1 FROM cohorts WHERE code = %s", [args.cohort])
        if cur.fetchone() is None:
            print(f"[주의] cohorts 에 {args.cohort} 가 없습니다. 그래도 넣습니다(ETL 뒤에 기수가 생기면 이어집니다).")
        for s in sets:
            n = upsert_set(cur, args.cohort, s)
            print(f"  {s['id']} · {s['lessonDate']} · {s.get('title', '')} — 문제 {n}개")
        for item in args.coverage:
            source, _, path = item.partition("=")
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            cur.execute(
                """INSERT INTO practice.coverage (cohort_code, source_title, data, updated_at) VALUES (%s, %s, %s, now())
                   ON CONFLICT (cohort_code, source_title) DO UPDATE SET data = EXCLUDED.data, updated_at = now()""",
                [args.cohort, source, Jsonb(data)],
            )
            print(f"  출제 범위 {source} ← {path}")
    print(f"완료 — 세트 {len(sets)}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
