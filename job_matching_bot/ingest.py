"""수집 실행 — 원본 보존 → 정규화 → upsert → 리포트.

분석 파이프라인(`python -m job_matching_bot`)과 분리돼 있다. 수집은 반복해서
돌리며 저장소를 쌓아가는 일이고, 분석은 그 저장소를 읽어 한 번 계산하는
일이라 주기가 다르기 때문이다.

    python -m job_matching_bot.ingest --source SARAMIN_POC
    python -m job_matching_bot.ingest --source SARAMIN_POC --observed job_matching_bot/artifacts/raw/saramin_raw.json

`--input`을 생략하면 소스별 기본 경로(`SOURCES`)를 쓴다. `--observed`는 목록
페이지에서 본 공고 목록이다. 증분 수집(새 공고 상세만 받음)에서는 이걸 줘야
기존 공고가 "안 보임"으로 세이지 않는다.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from job_matching_bot.config import ARTIFACTS_DIR, DEFAULT_SARAMIN_INPUT, now
from job_matching_bot.ingestion.record_files import latest_by_id, read_records, record_ids
from job_matching_bot.ingestion import raw_store
from job_matching_bot.ingestion import jobkorea
from job_matching_bot.ingestion import saramin
from job_matching_bot.ingestion.job_store import open_store
from job_matching_bot.schemas.job_posting import Job
from job_matching_bot.schemas.job_record import CollectionReport

# SQLite. JSON은 전 카테고리 규모(활성 17만 건, 1GB)를 통째로 읽고 쓸 수 없다.
DEFAULT_STORE = ARTIFACTS_DIR / "job_store.sqlite"
DEFAULT_RAW_ROOT = ARTIFACTS_DIR / "job_raw"
DEFAULT_REPORT = ARTIFACTS_DIR / "collection_report.json"

# 소스 이름 → (파서, 파서 버전, 원본에서 source_job_id 뽑는 함수, 기본 입력 경로)
# 파서는 `parser(record, as_of=...)`로 호출된다.
SOURCES: dict[
    str, tuple[Callable[..., Job], str, Callable[[dict[str, Any]], str], Path]
] = {
    "SARAMIN_POC": (
        saramin.normalize_saramin,
        saramin.PARSER_VERSION,
        # 상세 레코드 최상위에 있고, 없으면 합쳐 둔 목록 항목에서 찾는다.
        lambda record: str(
            record.get("source_job_id") or (record.get("list_item") or {}).get("source_job_id") or ""
        ),
        DEFAULT_SARAMIN_INPUT,
    ),
    "JOBKOREA_POC": (
        jobkorea.normalize_jobkorea,
        jobkorea.PARSER_VERSION,
        lambda record: str(
            record.get("source_job_id") or (record.get("list_item") or {}).get("source_job_id") or ""
        ),
        # 크롤러가 받는 족족 붙여 쓰는 파일. 사람인과 달리 한 번에 끝나지 않아 jsonl이다.
        ARTIFACTS_DIR / "job_raw" / "JOBKOREA_POC" / "details.jsonl",
    ),
}


def ingest(
    records: list[dict[str, Any]],
    *,
    source: str,
    store_path: Path = DEFAULT_STORE,
    raw_root: Path = DEFAULT_RAW_ROOT,
    as_of: datetime | None = None,
    observed_ids: set[str] | None = None,
    extract: bool = False,
    allow_llm: bool = True,
) -> CollectionReport:
    """원본을 보존하고 정규화한 뒤 저장소에 반영한다.

    `observed_ids`를 주면 목록에서 본 공고는 상세가 없어도 살아 있는 것으로
    본다(증분 수집). 이번에 받은 상세의 ID는 자동으로 포함된다.

    `extract=True`면 사람인 본문에서 필수·우대 기술을 뽑는다. CLI는 기본으로 켜고,
    테스트처럼 함수를 직접 부르는 곳은 명시해야 외부 API를 부르지 않는다.

    `allow_llm=False`면 LLM을 부르지 않고 본문 제목(자격요건/우대사항) 구간의
    사전 매칭만 쓴다. 비용이 없고 결과가 결정적이다.
    """
    as_of = as_of or now()
    if observed_ids is not None:
        observed_ids = set(observed_ids) | record_ids(records)
    if source not in SOURCES:
        raise ValueError(f"등록되지 않은 소스: {source} (가능: {', '.join(SOURCES)})")
    parser, parser_version, extract_id, _ = SOURCES[source]

    jobs: list[Job] = []
    for index, record in enumerate(records):
        source_job_id = extract_id(record) or f"unknown-{index}"
        try:
            if extract and parser is saramin.normalize_saramin:
                # 본문 제목(자격요건/우대사항) 구간의 사전 매칭, LLM 키가 있으면 LLM 추출.
                # 이미지뿐인 공고는 본문이 짧아 대부분 UNKNOWN으로 남는다.
                from job_matching_bot.coach.skill_source import extract_requirements

                listing = record.get("list_item") or {}
                requirements = extract_requirements(
                    str(listing.get("title") or ""),
                    str(record.get("description") or ""),
                    cache_path=ARTIFACTS_DIR / "llm_cache.json",
                    allow_llm=allow_llm,
                )
                job = parser(record, as_of=as_of, requirements=requirements)
            else:
                job = parser(record, as_of=as_of)
            jobs.append(job)
            status, error = raw_store.PARSE_OK, None
        except Exception as exc:
            # 한 건이 깨져도 나머지 수집은 계속한다. 원본은 남겨 재처리한다.
            status = raw_store.PARSE_FAILED
            error = f"{type(exc).__name__}: {exc}"
        raw_store.save_raw(
            raw_root,
            source,
            source_job_id,
            record,
            parse_status=status,
            parse_error=error,
            parser_version=parser_version,
            fetched_at=as_of,
        )

    with open_store(store_path) as store:
        return store.upsert(jobs, source=source, as_of=as_of, observed_ids=observed_ids)


def _print_report(report: CollectionReport, store_path: Path) -> None:
    with open_store(store_path) as store:
        stats = store.stats()
    print(f"수집 소스: {report.source}  기준시각: {report.collected_at}")
    print(
        f"  신규 {len(report.new)} / 갱신 {len(report.updated)} / "
        f"변경없음 {len(report.unchanged)}"
    )
    print(
        f"  만료 {len(report.expired)} / 삭제 {len(report.removed)} / "
        f"미관측(상태유지) {len(report.still_missing)} / 목록에서만 확인 {len(report.observed)}"
    )
    if report.missing_fields:
        print(f"  필수 필드 누락 {len(report.missing_fields)}건 — 선택자 확인 필요")
        for job_id, fields in list(report.missing_fields.items())[:5]:
            print(f"    {job_id}: {', '.join(fields)}")
    for version, count in report.parser_versions.items():
        print(f"  파서 {version}: {count}건")
    print(f"저장소 총 {stats['total']}건 — {stats['by_status']}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="채용공고 수집 실행")
    parser.add_argument(
        "--input", type=Path, default=None, help="생략하면 소스별 기본 경로를 쓴다"
    )
    parser.add_argument("--source", default="SARAMIN_POC", choices=sorted(SOURCES))
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument(
        "--no-extract",
        action="store_true",
        help="본문에서 필수·우대 기술을 뽑지 않는다(구간 규칙·LLM 모두 끔)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="LLM을 부르지 않고 본문 구간 규칙으로만 필수·우대 기술을 뽑는다(비용 없음)",
    )
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--observed",
        type=Path,
        default=None,
        help="목록 페이지 수집 결과(JSON). 주면 증분 수집으로 보고 목록에 있는 공고를 유지한다",
    )
    args = parser.parse_args()

    input_path = args.input or SOURCES[args.source][3]
    if not input_path.exists():
        print(f"입력 파일이 없습니다: {input_path}")
        return 1
    # 다시 받은 공고는 파일에 두 번 있다. 마지막(최신) 것만 쓴다.
    records = list(latest_by_id(read_records(input_path)).values())
    observed_ids = None
    if args.observed is not None:
        if not args.observed.exists():
            print(f"목록 파일이 없습니다: {args.observed}")
            return 1
        observed_ids = record_ids(read_records(args.observed))
        print(f"목록에서 확인한 공고 {len(observed_ids)}건 (증분 모드)")
    report = ingest(
        records,
        source=args.source,
        store_path=args.store,
        raw_root=args.raw_root,
        observed_ids=observed_ids,
        extract=not args.no_extract,
        allow_llm=not args.no_llm,
    )

    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _print_report(report, args.store)
    print(f"STORE:  {args.store.resolve()}")
    print(f"RAW:    {args.raw_root.resolve()}")
    print(f"REPORT: {args.report_output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
