"""DB 표 문서(docs/db-tables.md)를 실제 DB 에서 만든다.

    python scripts/firestore_to_postgres/describe_schema.py            # docs/db-tables.md 를 다시 쓴다
    python scripts/firestore_to_postgres/describe_schema.py --check    # 문서가 DB 와 다르면 1 로 끝난다

칸 · 형식 · 비어도 되는지 · 기본값 · 키 · 참조는 DB(information_schema · pg_catalog)에서 읽는다.
표 설명과 칸 메모는 아래 TABLES · NOTES 에 손으로 적는다 — 표를 새로 만들면 여기에 한 줄 더한다
(설명이 없는 표는 문서의 「설명 없음」 절에 모인다).

DATABASE_URL 은 환경 변수 또는 저장소 루트 .env 에서 읽는다.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "db-tables.md"

# (스키마, 묶음 이름, [(표, 설명)]) — 문서에 이 순서로 나온다
TABLES: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("public", "계정 · 기수", [
        ("cohorts", "기수(반). `code`(예: cohort_34)가 화면 · API 에서 쓰는 기수 id 다."),
        ("users", "계정 — 학생 · 강사 · 관리자. 화면의 사용자 id 는 `firebase_uid` 다."),
        ("student_intakes", "학생 사전 설문(전공 · 수준 · 희망 직무 등). 학생 한 명에 한 줄."),
        ("todos", "대시보드 할 일."),
        ("alert_popup_dismissals", "알림 팝업 「오늘 하루 보지 않기」 기록."),
        ("system_cache", "외부에서 받아 둔 값(자격 시험 일정 등). `key` 로 찾는다."),
    ]),
    ("public", "수업 · 출결", [
        ("schedules", "기수의 하루 교시표(`sessions`)."),
        ("curriculum_sheets", "업로드한 커리큘럼 표 한 벌."),
        ("curriculum_rows", "커리큘럼 한 줄 = 수업 하루. `day_index` 가 N일차, `date_label` 은 날짜 글자."),
        ("curriculum_pdfs", "기수의 커리큘럼 PDF 한 장."),
        ("materials", "수업 자료 파일."),
        ("attendances", "학생의 하루 출결. 학생 · 날짜마다 한 줄."),
        ("roll_calls", "강사 「자리 확인」 — 날짜 · 교시마다 한 번."),
        ("roll_call_entries", "자리 확인의 학생별 상태(확인 · 보류)."),
    ]),
    ("public", "좌석 · 프로젝트 팀", [
        ("seating_rooms", "강의실 틀. 기수마다 여럿, 그중 하나를 확정해 학생에게 보인다(`cohorts.published_seating_room_id`)."),
        ("seating_cells", "강의실 격자의 칸 — 좌석 · 강사석 · 출입문만 둔다(빈 칸은 없다)."),
        ("seating_assignments", "강의실별 배치 상태 — 작성 중(draft) · 확정(published)."),
        ("seat_assignments", "좌석에 앉은 학생. 한 강의실에서 한 학생은 한 자리."),
        ("project_teams", "프로젝트 팀."),
        ("project_team_members", "팀원."),
    ]),
    ("public", "공지", [
        ("notices", "게시판 공지. 디스코드에서 들어온 공지 · 벡터 색인 상태도 담는다."),
        ("scheduled_notices", "예약 공지 — 정해진 시각에 notices 로 발행된다."),
        ("alert_popups", "로그인하면 뜨는 알림 팝업."),
    ]),
    ("public", "과제 · 기록 · 설문", [
        ("assignments", "과제."),
        ("assignment_submissions", "과제 제출 파일."),
        ("record_submissions", "기록실 제출(자격증 · 스터디 · 블로그 · 학습 인증 · 프리코스 퀴즈) — 승인되면 마일리지."),
        ("weekly_tasks", "주간 과제 목록."),
        ("weekly_progress", "학생별 주간 과제 진행."),
        ("form_tasks", "구글폼 설문 · 제출 과제."),
        ("form_responses", "설문 응답 여부(구글폼에서 가져온 것)."),
    ]),
    ("public", "성취도평가", [
        ("assessments", "평가. 커리큘럼 N일차 범위(`day_from` ~ `day_to`)로 문항을 만든다."),
        ("assessment_questions", "평가 문항. `source_day` · `source_topic` 은 문항이 나온 수업 — 틀린 문항을 그날 복습으로 잇는 데 쓴다."),
        ("assessment_submissions", "학생의 응시. 평가 · 학생마다 한 줄."),
        ("assessment_answers", "응시의 문항별 답과 점수."),
        ("assessment_score_adjustments", "강사가 점수를 고친 기록."),
    ]),
    ("public", "마일리지", [
        ("mileage_settings", "기수의 마일리지 규칙(카테고리 한도 · 적립 규칙)."),
        ("mileage_transactions", "마일리지 적립 · 차감 내역."),
        ("mission_progress", "미션 진행(학습 인증 · 퀴즈 · 코딩 테스트 · 블로그)과 지급 여부."),
        ("mileage_products", "마일리지 상품."),
        ("mileage_cart_items", "학생 장바구니."),
        ("purchase_requests", "구매 요청."),
        ("purchase_request_items", "구매 요청에 담긴 상품."),
    ]),
    ("public", "이력서", [
        ("resumes", "이력서. 기본 이력서 하나(`is_base_resume`)와, 공고에 맞춰 만든 맞춤 이력서(`base_resume_id` = 원본)."),
        ("resume_feedback", "강사 · 관리자의 섹션별 피드백과 답글(`parent_id`)."),
        ("resume_feedback_reads", "피드백을 읽었는지."),
        ("resume_revisions", "저장할 때마다 남기는 이전 판."),
        ("resume_ai_reviews", "AI 첨삭 결과."),
        ("resume_ai_applications", "AI 첨삭 제안을 이력서에 적용한 기록(되돌리기용)."),
        ("job_requirement_profiles", "직무별 요구 역량 목록(AI 첨삭 · 공고 매칭 재료)."),
    ]),
    ("public", "학습실 · 공부방", [
        ("inflearn_packages", "배정된 인프런 강의 묶음."),
        ("youtube_recommendations", "이번 주 커리큘럼 추천 영상."),
        ("recommendation_events", "추천 영상 클릭 · 반응 기록."),
        ("study_sources", "공부방 수업 저장소(GitHub). 노트와 복습 문제의 재료."),
        ("study_notes", "학생별 복습 노트. 범위는 `scope_type`(date · prefix · files) + `scope_key`."),
    ]),
    ("public", "AI 기록", [
        ("ai_generation_logs", "LLM 생성 기록(문항 초안 등) — 모델 · 토큰 · 지연."),
        ("ai_question_feedback", "AI 문항 초안을 강사가 채택 · 수정 · 버렸는지."),
        ("ai_eval_runs", "프롬프트 평가 실행 결과."),
    ]),
    ("practice", "복습 문제 (practice 스키마)", [
        ("sets", "수업 날짜별 복습 문제 묶음. 기수 공용. `legacy_id` 가 화면의 세트 id."),
        ("problems", "세트 안의 문제. `idx` 는 세트 안 순서(0부터). `hidden_tests` 는 채점용 — 학생 화면에 안 보인다."),
        ("attempts", "학생별 풀이 기록. 한 문제에 한 줄 — 다시 풀면 `tries` 가 는다."),
        ("reports", "「이 문제 이상해요」 신고. 한 문제에 한 사람 한 번."),
        ("reviews", "강사 결정(숨김 · 다시 보이기). 없으면 서로 다른 학생 2명의 신고로 숨긴다."),
        ("coverage", "출제 범위 기록 — 수업 파일마다 어디까지 문제로 냈는지(다음 날은 새 셀로만)."),
    ]),
    ("jobs", "공고 (jobs 스키마)", [
        ("jobs", "공고 한 건(상세). `job_id` 가 id."),
        ("job_tags", "공고의 기술 · 키워드 태그."),
        ("list_jobs", "목록 페이지에서 본 공고(상세를 받기 전 단계)."),
        ("list_jobs_search", "목록 공고 검색용 뷰."),
        ("list_seen", "목록에서 본 기록(직무 분류별)."),
        ("list_sweeps", "직무 분류별 목록 수집 한 번."),
        ("link_checks", "공고 링크가 살아 있는지 확인한 기록."),
        ("runs", "수집 배치 한 번의 결과(새 공고 · 갱신 · 만료 수)."),
    ]),
]

# (스키마.표.칸) → 메모
NOTES: dict[str, str] = {
    "public.users.firebase_uid": "화면 · API 의 사용자 id. ETL 로 `id` 가 새로 매겨져도 이 값은 그대로다",
    "public.users.password": "⚠ 지금은 평문으로 저장 · 비교한다. 배포 전 해시로 바꿔야 한다",
    "public.users.role": "student · instructor · admin",
    "public.cohorts.code": "화면 · API 의 기수 id",
    "public.cohorts.published_seating_room_id": "학생에게 보이는 강의실(seating_rooms.id)",
    "public.resumes.status": "writing · ready(작성 중), submitted(피드백 요청), approved · completed(승인)",
    "public.resumes.base_resume_id": "맞춤 이력서면 원본 이력서(resumes.id)",
    "public.resumes.source_tailored_resume_id": "AI 첨삭 작업본을 편집기로 옮긴 사본이면 그 작업본",
    "public.resumes.sections": "섹션별 채움 여부 { basicInfo: true, … }",
    "public.study_notes.scope_type": "date · prefix(폴더) · files",
    "public.study_notes.scope_key": "date 면 '2026-09-15', prefix 면 'prefix_…', files 면 'files_<해시>'",
    "public.seating_cells.seat_id": "좌석은 번호('1'…), 강사석 · 출입문은 '행_열'",
    "public.seating_cells.group_id": "같은 책상(테이블) 묶음. 강사석은 __instructor__, 출입문은 __door__",
    "public.curriculum_rows.date_label": "날짜 글자(예: 2026년 6월 16일 화요일) — date 형식이 아니다",
    "public.assessment_questions.source_day": "curriculum_rows.day_index",
    "practice.sets.cohort_code": "cohorts.code — 외래키가 아니다(ETL 이 public 을 다시 만들어도 이어지게)",
    "practice.attempts.user_uid": "users.firebase_uid — 외래키가 아니다(같은 이유)",
    "practice.reports.user_uid": "users.firebase_uid",
    "practice.reports.reason": "unclear · answer · tests · offtopic · other",
    "practice.reviews.decision": "hidden · kept",
}

HEADER = """# DB 표 문서

> 이 문서는 `scripts/firestore_to_postgres/describe_schema.py` 가 실제 DB 에서 만든다. 손으로 고치지 말고,
> 표를 바꾼 뒤 스크립트를 다시 돌린다. 표 설명 · 칸 메모는 스크립트 안의 `TABLES` · `NOTES` 에 적는다.

## 한눈에

| 스키마 | 무엇 | 만드는 파일 |
|---|---|---|
| `public` | LMS 본 데이터(Firestore 에서 옮겨 온 것) | `schema.sql`, `schema_extra.sql` — `etl.py` 가 **지우고 다시 만든다** |
| `practice` | 복습 문제 · 풀이 기록 · 신고 | `practice_schema.sql`, 세트 적재는 `load_practice.py` |
| `jobs` | 공고 수집 결과 | `jobs_schema.sql` (`CREATE SCHEMA jobs` 후 그 안에서 실행) |

(파일은 모두 `scripts/firestore_to_postgres/` 에 있다.)

## 공통 규칙

- **id** — 대부분 `id bigint`(자동 증가) + `legacy_id`(Firestore 문서 id). API 는 `legacy_id` 가 있으면 그것을, 없으면 `id` 를 화면 id 로 보낸다.
- **사용자 · 기수를 가리킬 때** — `public` 안에서는 `user_id` · `cohort_id`(숫자) 외래키. `public` 밖(`practice`)에서는
  `users.firebase_uid` · `cohorts.code` 로 가리킨다. ETL 이 `public` 을 다시 만들면 숫자 id 가 바뀌기 때문이다.
- **시각** — `timestamptz`. 날짜만이면 `date`(`date_key` 등).
- **jsonb** — 이력서 내용, 노트 파일 목록 같은 구조 값. 지금 `lms_api` 는 jsonb 를 **JSON 글자로** 돌려준다
  (화면이 받는 입구 `lms_react/src/data/bootstrap.ts` 의 `parseJsonb` 에서 푼다).
- **표 읽는 법** — 아래 칸 표의 「키」: PK 기본키, UQ 고유, FK → 참조 대상.
"""


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


def fetch(cur, schemas: list[str]):
    cur.execute(
        """SELECT c.table_schema, c.table_name, c.column_name, c.ordinal_position,
                  CASE WHEN c.data_type = 'ARRAY' THEN substr(c.udt_name, 2) || '[]'
                       WHEN c.data_type = 'USER-DEFINED' THEN c.udt_name
                       WHEN c.data_type IN ('character varying') THEN 'varchar'
                       WHEN c.data_type = 'timestamp with time zone' THEN 'timestamptz'
                       WHEN c.data_type = 'time without time zone' THEN 'time'
                       ELSE c.data_type END,
                  c.is_nullable = 'YES',
                  CASE WHEN c.is_identity = 'YES' THEN 'GENERATED' ELSE c.column_default END
           FROM information_schema.columns c
           WHERE c.table_schema = ANY(%s)
           ORDER BY c.table_schema, c.table_name, c.ordinal_position""",
        [schemas],
    )
    columns: dict[tuple[str, str], list[tuple]] = {}
    for s, t, col, _, typ, nullable, default in cur.fetchall():
        columns.setdefault((s, t), []).append((col, typ, nullable, default))

    cur.execute(
        """SELECT n.nspname, cl.relname, con.contype,
                  array(SELECT a.attname FROM unnest(con.conkey) k JOIN pg_attribute a
                        ON a.attrelid = con.conrelid AND a.attnum = k ORDER BY a.attnum),
                  fn.nspname, fcl.relname,
                  array(SELECT a.attname FROM unnest(con.confkey) k JOIN pg_attribute a
                        ON a.attrelid = con.confrelid AND a.attnum = k ORDER BY a.attnum),
                  con.confdeltype
           FROM pg_constraint con
           JOIN pg_class cl ON cl.oid = con.conrelid JOIN pg_namespace n ON n.oid = cl.relnamespace
           LEFT JOIN pg_class fcl ON fcl.oid = con.confrelid LEFT JOIN pg_namespace fn ON fn.oid = fcl.relnamespace
           WHERE n.nspname = ANY(%s) AND con.contype IN ('p', 'u', 'f')""",
        [schemas],
    )
    keys: dict[tuple[str, str, str], list[str]] = {}
    multi: dict[tuple[str, str], list[str]] = {}
    on_delete = {"c": "CASCADE", "n": "SET NULL", "r": "RESTRICT", "a": "", "d": "SET DEFAULT"}
    for s, t, kind, cols, fs, ft, fcols, deltype in cur.fetchall():
        if kind == "f":
            target = f"{ft}.{fcols[0]}" if fs == s else f"{fs}.{ft}.{fcols[0]}"
            rule = on_delete.get(deltype or "a", "")
            label = f"FK → `{target}`" + (f" ({rule})" if rule else "")
        else:
            label = "PK" if kind == "p" else "UQ"
        if len(cols) == 1:
            keys.setdefault((s, t, cols[0]), []).append(label)
        else:
            multi.setdefault((s, t), []).append(f"{label} ({', '.join(cols)})")

    cur.execute(
        """SELECT schemaname, tablename, indexname FROM pg_indexes
           WHERE schemaname = ANY(%s) AND indexname NOT IN (
             SELECT conname FROM pg_constraint WHERE contype IN ('p', 'u'))""",
        [schemas],
    )
    indexes: dict[tuple[str, str], int] = {}
    for s, t, _ in cur.fetchall():
        indexes[(s, t)] = indexes.get((s, t), 0) + 1

    cur.execute(
        "SELECT table_schema, table_name FROM information_schema.views WHERE table_schema = ANY(%s)", [schemas]
    )
    views = {(s, t) for s, t in cur.fetchall()}
    return columns, keys, multi, indexes, views


def short_default(default: str | None) -> str:
    if default is None:
        return ""
    if default.startswith("nextval(") or "GENERATED" in default:
        return "자동 증가"
    return "`" + default.replace("::character varying", "").replace("::text", "").replace("::jsonb", "").replace("'", "") + "`"


def render(columns, keys, multi, indexes, views) -> str:
    out = [HEADER]
    documented: set[tuple[str, str]] = set()
    toc = ["## 차례", ""]
    body: list[str] = []
    for schema, group, tables in TABLES:
        toc.append(f"- {group}: " + ", ".join(f"`{t}`" for t, _ in tables if (schema, t) in columns))
        body += [f"## {group}", ""]
        for table, desc in tables:
            key = (schema, table)
            if key not in columns:
                body += [f"### `{schema}.{table}` — (DB 에 없음)", "", desc, ""]
                continue
            documented.add(key)
            kind = " (뷰)" if key in views else ""
            body += [f"### `{schema}.{table}`{kind}", "", desc, ""]
            extra = multi.get(key, [])
            if extra:
                body += ["여러 칸 키: " + " · ".join(extra), ""]
            body += ["| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |", "|---|---|---|---|---|---|"]
            for col, typ, nullable, default in columns[key]:
                k = " · ".join(keys.get((schema, table, col), []))
                note = NOTES.get(f"{schema}.{table}.{col}", "")
                body.append(f"| `{col}` | {typ} | {'예' if nullable else ''} | {short_default(default)} | {k} | {note} |")
            if indexes.get(key):
                body.append("")
                body.append(f"추가 인덱스 {indexes[key]}개.")
            body.append("")
    rest = sorted(k for k in columns if k not in documented)
    if rest:
        toc.append("- 설명 없음: " + ", ".join(f"`{s}.{t}`" for s, t in rest))
        body += ["## 설명 없음", "", "`describe_schema.py` 의 `TABLES` 에 설명을 더해 주세요.", ""]
        for s, t in rest:
            body += [f"### `{s}.{t}`", "", "| 칸 | 형식 | 비어도 됨 |", "|---|---|---|"]
            body += [f"| `{c}` | {typ} | {'예' if n else ''} |" for c, typ, n, _ in columns[(s, t)]]
            body.append("")
    out += toc + [""] + body
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="DB 표 문서를 실제 DB 에서 만든다")
    parser.add_argument("--check", action="store_true", help="문서가 DB 와 다르면 1 로 끝난다")
    args = parser.parse_args()
    schemas = sorted({s for s, _, _ in TABLES})
    with psycopg.connect(database_url()) as conn, conn.cursor() as cur:
        text = render(*fetch(cur, schemas))
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("문서가 DB 와 같습니다" if same else f"{OUT} 가 DB 와 다릅니다 — 스크립트를 다시 돌리세요")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8")
    print(f"{OUT} — 표 {text.count(chr(10) + '### ')}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
