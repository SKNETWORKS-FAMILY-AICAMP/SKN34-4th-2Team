"""추천 결과에서 **규칙으로 잡을 수 있는 결함**을 찾는다. 사람 정답이 필요 없다.

    python -m job_matching_bot.evaluation.recommend_check            # 추천을 받아 검사
    python -m job_matching_bot.evaluation.recommend_check --run-file <결과.json>

## 왜 따로 있나

옆의 `recommend_eval`은 사람이 매긴 정답과 대조한다. "이 공고가 이 사람에게 맞나"는
사람만 판단할 수 있기 때문이다. 그건 그것대로 필요하지만, 사람을 기다려야 한다.

그런데 **사람 없이도 확실히 틀렸다고 말할 수 있는 것**들이 있다. 신입에게 경력 3년
공고를 보내는 것, 서울만 원한다는 사람에게 부산 공고를 주는 것, 근거 한 줄 없이
"높음"이라고 하는 것. 이런 건 규칙으로 잡힌다.

2026-09-08에 신입 이력서 5종에서 경력 공고가 25건 중 6건 나가는 것을 찾았는데,
그때는 일회용 스크립트로 쟀다. 고치고 나서 다시 재지 않으면 같은 것이 되돌아와도
모른다. 그래서 재볼 수 있게 남긴다.

## 검사 항목

각 검사는 **왜 결함인지**가 분명해야 한다. 애매한 것은 넣지 않는다. 취향 문제를
결함으로 세면 숫자가 의미를 잃는다.

## 쓰는 법

서버를 띄우고 그냥 돌리면 된다. 고치기 전에 한 번, 고친 뒤에 한 번 돌려 비교한다.
결함이 하나라도 있으면 종료 코드가 1이라 CI에 걸 수도 있다.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter
from functools import lru_cache
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from job_matching_bot.config import ARTIFACTS_DIR, PACKAGE_ROOT
from job_matching_bot.evaluation.app_resume import EVAL_MOCKS, load_personas

KST = timezone(timedelta(hours=9))
# 이력서 원본은 앱과 같은 `scripts/resume_mocks.json` 하나다. `app_resume`가 읽는다.
RUNS_DIR = ARTIFACTS_DIR / "eval_runs"
# 회차별 검사 건수. 원본(`RUNS_DIR`)은 커밋하지 않지만 건수는 남긴다 — 고치기 전
# 숫자가 없으면 좋아졌는지 말할 수 없다.
CHECKS_DIR = PACKAGE_ROOT / "fixtures" / "checks"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"

# 회사 한 곳이 목록을 채우지 못하게 하는 상한. api/service.py 의 MAX_PER_COMPANY 와 같다.
MAX_PER_COMPANY = 2

# 인용이 원문에 있는지 볼 때 허용하는 최소 길이. 너무 짧은 인용은 우연히 맞을 수 있다.
MIN_QUOTE = 6


@dataclass
class Defect:
    """무엇이, 어디서, 왜 잘못됐는지. 셋이 다 있어야 고칠 수 있다."""

    check: str
    persona: str
    job_id: str
    title: str
    detail: str


@dataclass
class Report:
    defects: list[Defect] = field(default_factory=list)
    checked: int = 0
    personas: int = 0
    elapsed: float = 0.0
    missing_personas: list[str] = field(default_factory=list)
    skipped_same_day: bool = False

    def add(self, check: str, persona: str, job: dict, detail: str) -> None:
        self.defects.append(
            Defect(check, persona, job.get("job_id", "?"), job.get("title", "?")[:40], detail)
        )


# ── 검사 ──────────────────────────────────────────────────────
#
# 각 검사는 (이름, 함수)다. 함수는 결함이면 사유 문자열을, 아니면 None을 돌려준다.
# 페르소나·공고·저장소 행을 받는다. 저장소 행이 없을 수도 있다(인덱스에만 있는 경우).


def _career_years(persona: dict) -> float:
    return float(persona.get("career_years") or 0)


def check_experienced_for_entry(persona, job, row) -> str | None:
    """신입에게 경력자 채용 공고.

    2026-09-08에 실제로 25건 중 6건이 이랬고 셋은 적합도 "높음"이었다. 연차가 미기재라
    하드 필터가 "확인 필요"로 통과시킨 것이 원인이었다. 미기재인 것은 연차이지
    "경력자를 뽑는다"는 사실이 아니다.
    """
    if _career_years(persona) >= 1 or row is None:
        return None
    if (row["career_type"] or "") != "EXPERIENCED":
        return None
    years = row["min_career_years"]
    return f"경력자 채용 (최소 {years}년)" if years is not None else "경력자 채용 (연차 미기재)"


def check_region_outside_preference(persona, job, row) -> str | None:
    """희망 지역 밖의 공고. 전국 근무는 통과다."""
    wanted = [r for r in (persona.get("preferred_regions") or []) if r]
    if not wanted:
        return None
    region = (job.get("conditions") or {}).get("region") or ""
    if not region or region == "미기재":
        return None
    if "전국" in region:
        return None
    if any(want in region for want in wanted):
        return None
    return f"희망 {'·'.join(wanted)} 인데 {region}"


def check_employment_outside_preference(persona, job, row) -> str | None:
    wanted = [t for t in (persona.get("preferred_employment_types") or []) if t]
    if not wanted:
        return None
    kind = (job.get("conditions") or {}).get("employment_type") or ""
    if not kind or kind == "미기재":
        return None
    if any(want in kind for want in wanted):
        return None
    return f"희망 {'·'.join(wanted)} 인데 {kind}"


def check_high_without_reason(persona, job, row) -> str | None:
    """근거 없이 "높음". 이 프로젝트의 약속은 "근거는 인용이다"이다."""
    if job.get("fit") != "높음":
        return None
    if job.get("reasons"):
        return None
    return "적합도 높음인데 근거가 0건"


def check_quote_not_in_job(persona, job, row) -> str | None:
    """공고 인용이 공고 원문에 없다. 서버가 검증하지만 여기서 한 번 더 본다.

    검증이 망가져도 결과는 그럴듯해 보이므로, 밖에서 재보지 않으면 알 수 없다.

    **서버와 같은 함수로 대조한다.** 처음에 문자열을 그대로 비교했더니 14건이 전부
    걸렸는데, 전부 오탐이었다. 공고 원문에는 줄바꿈 없는 공백( )이 섞여 있고 LLM은
    인용할 때 보통 공백으로 바꿔 쓴다. 검사가 서버와 다른 규칙을 쓰면 오탐만 만든다.
    """
    if row is None:
        return None
    from job_matching_bot.api.service import _quote_in

    # 서버는 원문 전체가 아니라 excerpt(= index_body)를 공고 본문으로 삼는다
    # (`service.hit_to_job`). 요건 구간만 골라 라벨을 붙여 다시 이은 글이라 원문의
    # 부분 문자열이 아니다. 원문과만 대조하면 정상인 인용이 결함으로 잡힌다. 둘 다 본다.
    sources = [t for t in (row["description"] or "", _excerpt_of(job.get("job_id", ""))) if t]
    if not sources:
        return None

    for reason in job.get("reasons") or []:
        quote = (reason.get("job_quote") or "").strip()
        if len(quote) < MIN_QUOTE:
            continue
        if not any(_quote_in(quote, source) for source in sources):
            # 자르지 않는다. 잘라 두면 어디가 어긋났는지 볼 수 없어 한참 헤맸다.
            return f"공고에 없는 인용: {quote!r}"
    return None


def _excerpt_of(job_id: str) -> str:
    """서버가 재정렬에 넘긴 글. 저장소의 공고로 다시 만든다(인덱스를 부르지 않는다)."""
    record = _record(job_id) if job_id else None
    if record is None:
        return ""
    from job_matching_bot.retrieval.documents import index_body

    try:
        return index_body(record.job)
    except Exception:
        return ""


@lru_cache(maxsize=512)
def _record(job_id: str):
    from job_matching_bot.ingest import DEFAULT_STORE
    from job_matching_bot.ingestion.sqlite_store import SqliteJobStore

    if not DEFAULT_STORE.exists():
        return None
    with SqliteJobStore(DEFAULT_STORE) as store:
        return store.get(job_id)


def check_closed(persona, job, row) -> str | None:
    """마감했거나 내려간 공고."""
    if row is None:
        return None
    if (row["status"] or "") != "OPEN":
        return f"상태가 {row['status']}"
    deadline = (row["deadline"] or "")[:10]
    today = datetime.now(KST).date().isoformat()
    if deadline and deadline < today:
        return f"마감일 {deadline} 지남"
    return None


def check_missing_from_store(persona, job, row) -> str | None:
    """인덱스에는 있는데 저장소에 없다. 둘이 어긋났다는 뜻이다."""
    return None if row is not None else "저장소에 없음"


CHECKS = [
    ("신입에게 경력 공고", check_experienced_for_entry),
    ("희망 지역 밖", check_region_outside_preference),
    ("희망 고용형태 밖", check_employment_outside_preference),
    ("근거 없는 높음", check_high_without_reason),
    ("원문에 없는 인용", check_quote_not_in_job),
    ("마감·삭제된 공고", check_closed),
    ("저장소에 없음", check_missing_from_store),
]


def check_company_cap(persona_name: str, jobs: list[dict], report: Report) -> None:
    """한 회사가 목록을 차지했나. 공고 하나가 아니라 목록 전체를 봐야 한다."""
    counts = Counter((job.get("company") or "?") for job in jobs)
    for company, count in counts.items():
        if count > MAX_PER_COMPANY:
            report.add(
                "회사당 상한 초과",
                persona_name,
                {"job_id": "-", "title": company},
                f"{company} {count}건 (상한 {MAX_PER_COMPANY})",
            )


# ── 실행 ──────────────────────────────────────────────────────


def store_rows(job_ids: set[str]) -> dict[str, sqlite3.Row]:
    from job_matching_bot.ingest import DEFAULT_STORE

    if not job_ids or not DEFAULT_STORE.exists():
        return {}
    connection = sqlite3.connect(f"{DEFAULT_STORE.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        marks = ", ".join("?" for _ in job_ids)
        rows = connection.execute(
            f"SELECT job_id, career_type, min_career_years, status, deadline, description "
            f"FROM jobs WHERE job_id IN ({marks})",
            list(job_ids),
        ).fetchall()
    finally:
        connection.close()
    return {row["job_id"]: row for row in rows}


def fetch(base_url: str, top_k: int, personas: dict[str, dict]) -> dict:
    import urllib.request

    raw: dict[str, dict] = {}
    for name, persona in personas.items():
        body = json.dumps({**persona, "top_k": top_k}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/api/v1/jobs/recommend", data=body,
            headers={"Content-Type": "application/json"},
        )
        began = time.time()
        with urllib.request.urlopen(request, timeout=300) as response:
            raw[name] = json.loads(response.read().decode("utf-8"))
        print(f"  {name:26s} {time.time() - began:5.1f}초 · {len(raw[name]['recommendations'])}건")
    return raw


# 이력서가 있어야 판정할 수 있는 검사. 이력서를 못 찾으면 건너뛴다.
PERSONA_CHECKS = {"신입에게 경력 공고", "희망 지역 밖", "희망 고용형태 밖"}
# 받은 그날이 아니면 뜻이 없는 검사. 그 사이 마감된 공고까지 결함으로 센다.
SAME_DAY_CHECKS = {"마감·삭제된 공고"}


def wrap_run(raw: dict, personas: dict[str, dict], resume_set: str) -> dict:
    """저장할 모양. 받은 시각과 **그때의 이력서 조건**을 같이 남긴다.

    결과만 남겼더니 나중에 다시 검사할 때 지금의 목업과 이름이 달라 이력서를 못 찾았고,
    못 찾은 이력서를 연차 0으로 보아 경력 3년 이력서를 "신입에게 경력 공고"로 셌다.
    """
    keep = ("career_years", "preferred_regions", "preferred_employment_types")
    return {
        "fetched_at": datetime.now(KST).isoformat(timespec="seconds"),
        "resume_set": resume_set,
        "personas": {name: {k: personas[name].get(k) for k in keep} for name in raw if name in personas},
        "results": raw,
    }


def unwrap_run(data: dict) -> tuple[dict, dict[str, dict] | None, str | None]:
    """(결과, 저장해 둔 이력서 조건, 받은 날). 예전 파일은 결과만 있다."""
    if "results" in data and isinstance(data.get("results"), dict):
        return data["results"], data.get("personas"), (data.get("fetched_at") or "")[:10] or None
    return data, None, None


def inspect(raw: dict, personas: dict[str, dict], *, same_day: bool = True) -> Report:
    report = Report(personas=len(raw), skipped_same_day=not same_day)

    job_ids = {
        job["job_id"]
        for result in raw.values()
        for job in result.get("recommendations", [])
    }
    rows = store_rows(job_ids)

    for name, result in raw.items():
        persona = personas.get(name)
        if persona is None:
            report.missing_personas.append(name)
        jobs = result.get("recommendations", [])
        check_company_cap(name, jobs, report)
        for job in jobs:
            report.checked += 1
            row = rows.get(job["job_id"])
            for label, rule in CHECKS:
                if persona is None and label in PERSONA_CHECKS:
                    continue
                if not same_day and label in SAME_DAY_CHECKS:
                    continue
                reason = rule(persona or {}, job, row)
                if reason:
                    report.add(label, name, job, reason)
    return report


def summary(report: Report, resume_set: str, fetched_at: str | None) -> dict:
    """회차 기록. 건수만 남기고 공고 원문은 넣지 않는다."""
    counts = Counter(defect.check for defect in report.defects)
    return {
        "checked_at": datetime.now(KST).isoformat(timespec="seconds"),
        "fetched_at": fetched_at,
        "resume_set": resume_set,
        "personas": report.personas,
        "jobs": report.checked,
        "counts": {label: counts.get(label, 0) for label, _ in [*CHECKS, ("회사당 상한 초과", None)]},
        "skipped_personas": report.missing_personas,
        "defects": [
            {"check": d.check, "persona": d.persona, "job_id": d.job_id, "detail": d.detail}
            for d in report.defects
        ],
    }


def show(report: Report) -> int:
    print()
    print(f"이력서 {report.personas}종 · 공고 {report.checked}건 검사")
    if report.missing_personas:
        print(f"  이력서를 찾지 못해 조건 검사를 건너뜀: {', '.join(report.missing_personas)}")
    if report.skipped_same_day:
        print("  받은 날이 오늘이 아니라 마감 검사를 건너뜀")
    print()
    counts = Counter(defect.check for defect in report.defects)
    width = max((len(label) for label, _ in CHECKS), default=12) + 2
    for label, _ in [*CHECKS, ("회사당 상한 초과", None)]:
        n = counts.get(label, 0)
        mark = "  " if n == 0 else "!!"
        print(f"  {mark} {label:{width}s} {n:>3}건")

    if report.defects:
        print("\n─ 자세히 ─")
        for defect in report.defects:
            print(f"  [{defect.check}] {defect.persona}")
            print(f"      {defect.title}  ({defect.job_id})")
            print(f"      {defect.detail}")
    print()
    if report.defects:
        print(f"결함 {len(report.defects)}건. 위 항목을 고치고 다시 돌리세요.")
        return 1
    print("규칙으로 잡히는 결함 없음.")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="추천 결과 자동 검사 (사람 정답 불필요)")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--run-file", type=Path, default=None,
        help="이미 받아 둔 결과를 검사한다. 없으면 서버를 호출한다",
    )
    parser.add_argument(
        "--save", action="store_true",
        help="받은 결과 원본과 검사 건수를 남긴다(건수는 fixtures/checks/, 커밋 대상)",
    )
    parser.add_argument("--eval-resumes", action="store_true", help="앱 목업 대신 평가 전용 이력서")
    args = parser.parse_args()

    resume_set = "eval-resumes" if args.eval_resumes else "app-mocks"
    started = time.time()
    today = datetime.now(KST).date().isoformat()
    if args.run_file:
        raw, saved_personas, fetched_on = unwrap_run(json.loads(args.run_file.read_text(encoding="utf-8")))
        # 받을 때 남긴 조건이 있으면 그것으로 본다. 목업이 그 뒤에 바뀌었을 수 있다.
        personas = saved_personas if saved_personas is not None else load_personas(
            EVAL_MOCKS if args.eval_resumes else None
        )
        same_day = fetched_on == today
        print(f"결과 파일로 검사: {args.run_file}")
    else:
        personas = load_personas(EVAL_MOCKS if args.eval_resumes else None)
        print("추천을 받는 중…")
        raw = fetch(args.base_url, args.top_k, personas)
        fetched_on, same_day = today, True
        if args.save:
            RUNS_DIR.mkdir(parents=True, exist_ok=True)
            path = RUNS_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-check.json"
            path.write_text(
                json.dumps(wrap_run(raw, personas, resume_set), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"결과 원본: {path}")

    report = inspect(raw, personas, same_day=same_day)
    report.elapsed = time.time() - started
    code = show(report)
    if args.save:
        CHECKS_DIR.mkdir(parents=True, exist_ok=True)
        path = CHECKS_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{resume_set}.json"
        path.write_text(
            json.dumps(summary(report, resume_set, fetched_on), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"검사 기록: {path}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
