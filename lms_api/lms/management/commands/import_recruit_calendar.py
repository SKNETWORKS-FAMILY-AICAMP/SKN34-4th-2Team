"""공채 달력 수집 결과를 company_profiles · jobs.jobs.apply_method 에 넣는다(lms/recruit_calendar_import.py).

기본은 미리 보기만 한다. --apply 를 줘야 쓴다.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from lms.recruit_calendar_import import apply, current_state, plan, read_dir

DEFAULT_ROOT = Path(__file__).resolve().parents[4] / "job_matching_bot" / "artifacts" / "recruit_calendar"


class Command(BaseCommand):
    help = "공채 달력 수집 결과로 회사 로고 · 기업 형태와 공고 지원 방법을 채운다(빈 칸만)."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", help="수집 폴더(postings · companies.jsonl). 생략하면 가장 최근 날짜")
        parser.add_argument("--apply", action="store_true", help="실제로 쓴다. 없으면 미리 보기")

    def handle(self, *args, **options):
        path = Path(options["path"]) if options["path"] else self._latest()
        if not (path / "companies.jsonl").exists():
            raise CommandError(f"수집 결과가 없습니다: {path}")
        companies, postings = read_dir(path)
        existing, open_methods = current_state(postings)
        result = plan(companies, postings, existing, open_methods)
        self.stdout.write(f"{path.name}: {json.dumps(result.summary(), ensure_ascii=False)}")
        if not options["apply"]:
            self.stdout.write("미리 보기만 했습니다. 쓰려면 --apply")
            return
        apply(result)
        self.stdout.write("넣었습니다.")

    @staticmethod
    def _latest() -> Path:
        days = sorted(p for p in DEFAULT_ROOT.glob("*") if p.is_dir())
        if not days:
            raise CommandError(f"수집 결과가 없습니다: {DEFAULT_ROOT}")
        return days[-1]
