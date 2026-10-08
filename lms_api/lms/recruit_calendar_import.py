"""공채 달력 수집 결과(job_matching_bot/crawling/recruit_calendar.py)를 company_profiles · jobs.jobs.apply_method 로.

- 회사: company_key(canonical_company_key)로 없으면 만들고, 있으면 **빈 칸만** 채운다 — 관리자가 고친 이름 · 로고는 덮지 않는다.
- 지원 방법: 우리 공고(source · source_job_id)에 있고 아직 비어 있는 것만. 관리자가 정한 값은 덮지 않는다.
- 계획(plan)은 DB 없이 계산하고, apply 가 한 트랜잭션으로 쓴다. 명령: manage.py import_recruit_calendar
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.db import connection, transaction

from .models import CompanyProfiles
from .recruit_role_store import canonical_company_key

FILLABLE = ("company_type", "logo_url")


@dataclass
class Plan:
    create: list[dict[str, Any]] = field(default_factory=list)
    fill: dict[str, dict[str, Any]] = field(default_factory=dict)  # company_key → 채울 칸
    apply_methods: dict[tuple[str, str], str] = field(default_factory=dict)  # (source, source_job_id) → 값

    def summary(self) -> dict[str, int]:
        return {
            "create": len(self.create),
            "create_with_logo": sum(1 for c in self.create if c.get("logo_url")),
            "fill": len(self.fill),
            "apply_methods": len(self.apply_methods),
        }


def read_dir(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    def rows(name: str) -> list[dict[str, Any]]:
        with (path / name).open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    return rows("companies.jsonl"), rows("postings.jsonl")


def by_key(companies: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """같은 열쇠로 모이는 이름(「(주)카카오」 「카카오」)은 공고가 많은 쪽 이름을 쓰고 로고 · 형태는 있는 것을 쓴다"""
    out: dict[str, dict[str, Any]] = {}
    for company in sorted(companies, key=lambda c: -int(c.get("postings") or 0)):
        try:
            key = canonical_company_key(company.get("company_name") or "")
        except ValueError:
            continue
        have = out.setdefault(key, {"company_key": key, "company_name": company["company_name"][:255],
                                    "company_type": None, "logo_url": None})
        for name in FILLABLE:
            if not have[name] and company.get(name):
                have[name] = company[name]
    return out


def plan(companies: list[dict[str, Any]], postings: list[dict[str, Any]],
         existing: dict[str, dict[str, Any]], open_methods: set[tuple[str, str]]) -> Plan:
    """existing: 이미 있는 회사(company_key → 칸). open_methods: 우리 공고 중 apply_method 가 빈 것"""
    result = Plan()
    for key, company in by_key(companies).items():
        have = existing.get(key)
        if have is None:
            result.create.append(company)
            continue
        fill = {name: company[name] for name in FILLABLE if company.get(name) and not have.get(name)}
        if fill:
            result.fill[key] = fill
    for row in postings:
        ref = (row.get("source"), str(row.get("source_job_id") or ""))
        if row.get("apply_method") and ref in open_methods:
            result.apply_methods[ref] = row["apply_method"]
    return result


def current_state(postings: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], set[tuple[str, str]]]:
    existing = {row["company_key"]: row for row in CompanyProfiles.objects.values("company_key", *FILLABLE)}
    refs = [(r["source"], str(r["source_job_id"])) for r in postings if r.get("apply_method")]
    open_methods: set[tuple[str, str]] = set()
    with connection.cursor() as cur:
        for source in {s for s, _ in refs}:
            ids = [i for s, i in refs if s == source]
            cur.execute(
                "SELECT source_job_id FROM jobs.jobs WHERE source = %s AND source_job_id = ANY(%s) AND apply_method IS NULL",
                [source, ids],
            )
            open_methods |= {(source, r[0]) for r in cur.fetchall()}
    return existing, open_methods


def apply(result: Plan) -> None:
    with transaction.atomic():
        CompanyProfiles.objects.bulk_create(
            [CompanyProfiles(**company) for company in result.create], batch_size=500, ignore_conflicts=True,
        )
        for key, fill in result.fill.items():
            CompanyProfiles.objects.filter(company_key=key).update(**fill)
        with connection.cursor() as cur:
            for method in sorted(set(result.apply_methods.values())):
                for source in sorted({s for s, _ in result.apply_methods}):
                    ids = [i for (s, i), m in result.apply_methods.items() if s == source and m == method]
                    if ids:
                        cur.execute(
                            """UPDATE jobs.jobs SET apply_method = %s
                               WHERE source = %s AND source_job_id = ANY(%s) AND apply_method IS NULL""",
                            [method, source, ids],
                        )
