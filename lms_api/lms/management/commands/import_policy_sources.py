"""Stage extracted policy/FAQ source snapshots in PostgreSQL."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from lms.policy_sources import persist_documents, prepare_documents


class Command(BaseCommand):
    help = "Preview or import policy/FAQ source snapshots. Never updates Pinecone."

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="*", help="File or directory; defaults to policy_* directories")
        parser.add_argument("--source", choices=("files", "notion", "all"), default="files")
        parser.add_argument("--notion-url", action="append", default=[])
        parser.add_argument("--allow-ai-extraction", action="store_true", help="Allow paid AI PDF extraction")
        parser.add_argument("--target-db", help="Exact DB_NAME; required with --apply")
        parser.add_argument("--apply", action="store_true", help="Write to PostgreSQL")

    def handle(self, *args, **options):
        repo = Path(settings.REPO_DIR)
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        from vectordb.policy_ingestion import _chat_model, discover_files, load_file, load_notion

        source = options["source"]
        sections = []
        try:
            if source in ("files", "all"):
                paths = discover_files(options["paths"])
                if not paths:
                    raise CommandError("처리할 정책 파일이 없습니다")
                pdfs = [path for path in paths if path.suffix.lower() == ".pdf"]
                if pdfs and not options["allow_ai_extraction"]:
                    raise CommandError("PDF 추출은 유료 AI 호출이 필요합니다. --allow-ai-extraction을 명시하세요")
                model = _chat_model() if pdfs else None
                if pdfs and model is None:
                    raise CommandError("PDF 추출에는 OPENAI_API_KEY가 필요합니다")
                for path in paths:
                    sections.extend(load_file(path, model))
            if source in ("notion", "all"):
                urls = options["notion_url"]
                if not urls:
                    raise CommandError("Notion 원본 URL을 --notion-url로 명시하세요")
                token = os.environ.get("NOTION_TOKEN", "")
                if not token:
                    raise CommandError("NOTION_TOKEN이 필요합니다")
                for url in urls:
                    sections.extend(load_notion(url, token))
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(f"정책 원본 수집 실패: {exc}") from exc

        prepared = prepare_documents(sections)
        if not prepared:
            raise CommandError("추출된 정책 본문이 없습니다")
        self.stdout.write(f"sources={len(prepared)} sections={len(sections)}")
        if not options["apply"]:
            self.stdout.write("preview only; PostgreSQL/Pinecone 변경 없음")
            return
        target = options["target_db"]
        actual = connections["default"].settings_dict["NAME"]
        if not target or target != actual:
            raise CommandError("--apply에는 현재 연결 DB_NAME과 일치하는 --target-db가 필요합니다")
        counts = persist_documents(prepared)
        self.stdout.write(f"created={counts['created']} revised={counts['revised']} unchanged={counts['unchanged']}")
        self.stdout.write("Pinecone was not updated")
