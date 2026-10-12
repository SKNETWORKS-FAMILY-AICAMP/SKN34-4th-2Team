"""Numbered policy or chapter/article DOCX -> contextual Pinecone chunks.

Preview: python -m vectordb.policy_ingestion ingest --dry-run
Upload:  python -m vectordb.policy_ingestion ingest
Cover and TOC are excluded by accepting only numbered body headings.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import quote

try:
    from vectordb.utills import load_env, retry
except ModuleNotFoundError:  # python vectordb/policy_ingestion.py
    from utills import load_env, retry

MODULE_DIR = Path(__file__).resolve().parent
ROOT = MODULE_DIR.parent
DEFAULT_INPUT = ROOT / "output/documents/policy/SKN34_학생_정책집.docx"
DEFAULT_OUTPUT = MODULE_DIR / "policy_chunks.jsonl"
INDEX_NAME = "student"
NAMESPACE = "policy"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 40
POLICY_TYPES = [
    "Mileage", "Resource_Payment_and_Refund", "Retrospective_Writing_Guide",
    "Programmers_Exam_Registration", "Training_Method", "Training_Schedule",
    "Project", "Final_Project", "Post-Completion_Employment_Support",
    "Communication_Channel", "Book_Rental", "Attendance", "Official_Leave",
    "Completion_and_Dismissal", "Training_Incentive",
    "Educational_Facilities_and_Equipment", "Life_and_Miscellaneous",
]
POLICY_LABELS = dict(zip(POLICY_TYPES, [
    "마일리지", "리소스 결제 및 환급", "회고 작성 가이드", "프로그래머스 시험 접수",
    "훈련 방식", "훈련 일정", "단위 프로젝트", "최종 프로젝트", "수료 후 취업지원",
    "커뮤니케이션 채널", "도서 대여", "출결", "공가", "수료 및 제적", "훈련장려금",
    "교육시설 및 장비", "생활 및 기타",
]))
LABEL_TO_TYPE = {label: kind for kind, label in POLICY_LABELS.items()}
LABEL_TO_TYPE.update({"훈련 시간표": "Training_Schedule", "프로젝트": "Project", "최종프로젝트": "Final_Project"})
ITEM_HEADING = re.compile(r"^(?:#{1,6}\s+)?(?P<number>\d+-\d+)\s+\S.*$")
TYPE_LINE = re.compile(r"^정책\s*(?:번호\s*)?(\d+-\d+)\s*\|\s*(?:정책\s*타입\s*)?(.+?)\s*$")
CHAPTER_HEADING = re.compile(r"^제\s*(?P<number>\d+)\s*장(?:\s+.+)?$")
ARTICLE_HEADING = re.compile(r"^제\s*(?P<number>\d+)\s*조(?:의\s*(?P<sub>\d+))?\s*(?:\[.*\]|\(.*\)|.+)?$")
ARTICLE_REFERENCE = re.compile(r"제\s*(?P<number>\d+)\s*조(?:의\s*(?P<sub>\d+))?(?:\s*제\s*(?P<paragraph>\d+)\s*항)?")


@dataclass(frozen=True)
class SourceSection:
    text: str
    source_type: str
    source_name: str
    source_url: str = ""
    source_page: str = ""
    section: str = ""
    cohort: str = ""
    updated_at: str = ""
    chapter: str = ""
    chapter_number: str = ""
    article_number: str = ""
    document_hash: str = ""
    approval_status: str = "unverified"

    @property
    def document_key(self) -> str:
        return f"{self.source_type}:{self.source_url or self.source_name}:"

    @property
    def key(self) -> str:
        return self.document_key + self.section


@dataclass(frozen=True)
class ChunkRecord:
    page_content: str
    metadata: dict[str, Any]
    source: SourceSection
    content_hash: str
    vector_id: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def upload_timestamp(value: str | datetime | None = None) -> str:
    """Upload time rather than the DOCX file modification time."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    date = value or datetime.now(timezone.utc)
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    return date.astimezone(timezone.utc).isoformat()


def infer_cohort(text: str, explicit: str | None = None) -> str:
    if explicit is not None:
        value = str(explicit).strip()
        if not value:
            raise ValueError("기수(cohort)는 비어 있을 수 없습니다")
        number = re.fullmatch(r"(\d{1,3})(?:\s*기)?", value)
        return f"cohort_{number.group(1)}" if number else value
    matches = re.findall(r"(?i)SKN\s*(\d+)|(\d+)\s*기", text)
    cohorts = {a or b for a, b in matches}
    if len(cohorts) != 1:
        raise ValueError("표지/파일명에서 기수를 하나로 확인할 수 없습니다. --cohort를 지정하세요")
    return f"cohort_{cohorts.pop()}"


def policy_type(label: str) -> str:
    label = label.strip()
    if label in POLICY_TYPES:
        return label
    if label in LABEL_TO_TYPE:
        return LABEL_TO_TYPE[label]
    raise ValueError(f"알 수 없는 정책 타입: {label}")


def load_docx(
    file: Path | bytes, *, source_name: str | None = None,
    cohort: str | None = None, created_at: str | datetime | None = None,
) -> list[SourceSection]:
    """Read body items in document order, retaining paragraphs and body tables.

    Word has no fixed pages without rendering. Skip cover/TOC structurally:
    start at Heading-style N-N items or chapters/articles, ignoring cover tables.
    Bytes input supports an LMS UploadedFile.read() call.
    """
    from docx import Document as DocxDocument
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    if isinstance(file, bytes):
        if not source_name:
            raise ValueError("바이트 입력에는 source_name(원본 파일명)이 필요합니다")
        data = file
    else:
        file = Path(file)
        if file.suffix.lower() != ".docx":
            raise ValueError("정책집은 DOCX 형식이어야 합니다")
        source_name = source_name or file.name
        data = file.read_bytes()
    document = DocxDocument(io.BytesIO(data))

    cover = [source_name]
    items: list[tuple[str, list[str], str, str, str]] = []
    title, lines = "", []
    chapter, chapter_number, article_number = "", "", ""
    formal = False
    for block in document.element.body.iterchildren():
        if block.tag == qn("w:p"):
            p = Paragraph(block, document)
            text = p.text.strip()
            if p.style.name.startswith("Heading") and (match := CHAPTER_HEADING.fullmatch(text)):
                if title:
                    items.append((title, lines, chapter, chapter_number, article_number))
                    title, lines, article_number = "", [], ""
                chapter, chapter_number = text, match.group("number")
                formal = True
            elif p.style.name.startswith("Heading") and (match := ARTICLE_HEADING.fullmatch(text)):
                if title:
                    items.append((title, lines, chapter, chapter_number, article_number))
                if not chapter:
                    raise ValueError(f"장 제목 없이 조문이 시작됩니다: {text}")
                article_number = match.group("number") + ("-" + match.group("sub") if match.group("sub") else "")
                title, lines = text, []
                formal = True
            elif p.style.name.startswith("Heading") and ITEM_HEADING.fullmatch(text):
                if title:
                    items.append((title, lines, chapter, chapter_number, article_number))
                title, lines, article_number = text, [], ""
            elif title and text:
                prefix = "- " if p.style.name.startswith("List Bullet") else ""
                lines.append(prefix + text)
            elif not title:
                cover.append(text)
        elif block.tag == qn("w:tbl") and title:
            for row in Table(block, document).rows:
                lines.append(" | ".join(c.text.strip().replace("\n", "; ") for c in row.cells))
    if title:
        items.append((title, lines, chapter, chapter_number, article_number))
    if not items:
        raise ValueError("DOCX에서 '1-1 제목' 또는 '제N장/제N조' 본문 제목을 찾지 못했습니다")
    if formal and any(not number for _, _, _, _, number in items):
        raise ValueError("규정 문서에는 모든 본문이 장/조 구조에 속해야 합니다")
    cohort_value = infer_cohort("\n".join(cover), cohort)
    timestamp = upload_timestamp(created_at)
    digest = hashlib.sha256(data).hexdigest()
    status_text = "\n".join(cover)
    approval_status = "draft" if re.search(r"초안|검토\s*중|\(안\)|（안）|(?:^|[_\s])안(?:[_\s.]|$)", status_text) else "unverified"
    sections = [SourceSection(
        text="\n".join(body), source_type="docx", source_name=source_name,
        section=heading, cohort=cohort_value, updated_at=timestamp,
        chapter=chapter_title, chapter_number=chapter_id, article_number=article_id,
        document_hash=digest, approval_status=approval_status,
    ) for heading, body, chapter_title, chapter_id, article_id in items]
    build_records(sections)  # Validate every item before persisting any of them.
    return sections


def load_file(path: Path, model: Any | None = None, **kwargs: Any) -> list[SourceSection]:
    return load_docx(Path(path), **kwargs)


def discover_files(paths: Sequence[str]) -> list[Path]:
    found: set[Path] = set()
    for value in paths or [str(DEFAULT_INPUT)]:
        path = Path(value).resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        if path.is_dir():
            found.update(path.rglob("*.docx"))
        elif path.suffix.lower() == ".docx":
            found.add(path)
        else:
            raise ValueError(f"지원하지 않는 파일 형식: {path.suffix}")
    return sorted(path for path in found if not path.name.startswith("~$"))


def split_heading_sections(source: SourceSection) -> list[SourceSection]:
    """Handle numbered Markdown headings persisted by policy_sources.py too."""
    if ITEM_HEADING.fullmatch(source.section.strip()):
        return [source]
    items: list[SourceSection] = []
    title, lines = "", []
    for line in source.text.splitlines():
        text = line.strip()
        if text.startswith("#") and ITEM_HEADING.fullmatch(text):
            if title:
                items.append(replace(source, section=title, text="\n".join(lines)))
            title, lines = re.sub(r"^#{1,6}\s+", "", text), []
        elif title:
            lines.append(line)
    if title:
        items.append(replace(source, section=title, text="\n".join(lines)))
    if not items:
        raise ValueError(f"항목별 정책 제목이 없습니다: {source.source_name}")
    return items


def item_body(source: SourceSection) -> tuple[str, str, str]:
    number = ITEM_HEADING.fullmatch(source.section.strip()).group("number")
    types: set[str] = set()
    lines = []
    for line in source.text.splitlines():
        match = TYPE_LINE.fullmatch(line.strip())
        if match:
            if match.group(1) != number:
                raise ValueError(f"제목/정책 번호 불일치: {number} / {match.group(1)}")
            types.add(policy_type(match.group(2)))
        else:
            lines.append(line)
    if len(types) != 1:
        raise ValueError(f"{number}: 정책 타입이 없거나 충돌합니다")
    body = "\n".join(lines).strip()
    if not body:
        raise ValueError(f"{number}: 정책 본문이 비어 있습니다")
    return number, types.pop(), body


def split_body(body: str, capacity: int, overlap: int) -> list[str]:
    """Prefer paragraph/sentence/word boundaries and retain exact body overlap."""
    if capacity <= overlap or overlap < 0:
        raise ValueError("제목을 제외한 본문 용량은 chunk_overlap보다 커야 합니다")
    parts, start = [], 0
    while start < len(body):
        end = min(start + capacity, len(body))
        if end < len(body):
            minimum = start + max(capacity // 2, overlap + 1)
            for separator in ("\n\n", "\n", ". ", " "):
                boundary = body.rfind(separator, minimum, end)
                if boundary != -1:
                    end = boundary + len(separator)
                    break
        parts.append(body[start:end])
        if end == len(body):
            break
        start = end - overlap
    return parts


def vector_prefix(source: SourceSection, cohort: str) -> str:
    identity = hashlib.sha256(source.document_key.encode("utf-8")).hexdigest()[:20]
    return f"policy:{quote(cohort, safe='')}:{identity}:"


def explicit_article_references(body: str, article_numbers: set[str]) -> tuple[list[str], list[str]]:
    """Only link unqualified references to articles in this exact document version.

    Numbered body paragraphs are not assumed to be legal ``항``. A reference to
    one remains unresolved until a reviewed clause hierarchy is available.
    """
    resolved: list[str] = []
    unresolved: list[str] = []
    external_scope = False
    previous_end = 0
    for match in ARTICLE_REFERENCE.finditer(body):
        if re.search(r"[.!?。\n]", body[previous_end:match.start()]):
            external_scope = False
        label = match.group()
        number = match.group("number") + ("-" + match.group("sub") if match.group("sub") else "")
        before = body[max(0, match.start() - 40):match.start()]
        quoted_title = re.search(r"[「『][^」』]{1,40}[」』]\s*$", before)
        external = re.search(
            r"([가-힣A-Za-z0-9·]+)\s*(시행규칙|시행령|법률|법|고시|지침|규정집|규정|정책집|매뉴얼|가이드|기준)\s*[」』\]\)]?\s*$",
            before,
        )
        local_label = external and external.group(1) in ("이", "본") and external.group(2) == "규정"
        if local_label:
            external_scope = False
        elif quoted_title or external:
            external_scope = True
        if external_scope:
            unresolved.append(label)
        elif match.group("paragraph") or number not in article_numbers:
            unresolved.append(label)
        elif number not in resolved:
            resolved.append(number)
        previous_end = match.end()
    return resolved, list(dict.fromkeys(unresolved))


def formal_article_parts(source: SourceSection) -> list[tuple[str, list[str]]]:
    """Keep the entire article, including its conditions and exceptions."""
    header = source.chapter + "\n" + source.section + "\n"
    lines = source.text.splitlines()
    ids = [f"{source.article_number}:unit:{ordinal:03d}" for ordinal in range(1, len(lines) + 1)]
    return [(header + "\n".join(lines), ids)]


def build_records(
    sections: Iterable[SourceSection], model: Any | None = None,
    chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP,
) -> list[ChunkRecord]:
    if not 0 <= chunk_overlap < chunk_size:
        raise ValueError("0 <= chunk_overlap < chunk_size여야 합니다")
    raw_sections = list(sections)
    sources = [part for raw in raw_sections if not raw.article_number for part in split_heading_sections(raw)]
    # Structured DOCX sections already represent complete articles; legacy
    # Markdown and N-N policy headings continue through the original parser.
    structured = [raw for raw in raw_sections if raw.article_number]
    records: list[ChunkRecord] = []
    seen = set()
    timestamp = upload_timestamp()
    numbers_by_version: dict[tuple[str, str, str], set[str]] = {}
    for source in structured:
        cohort = infer_cohort(source.source_name, source.cohort or None)
        version = (source.document_key, cohort, source.document_hash)
        numbers = numbers_by_version.setdefault(version, set())
        if source.article_number in numbers:
            raise ValueError("같은 규정 문서에 중복 조문 번호가 있습니다")
        numbers.add(source.article_number)
    for source in structured:
        if not source.text.strip():
            raise ValueError(f"{source.section}: 조문 본문이 비어 있습니다")
        cohort = infer_cohort(source.source_name, source.cohort or None)
        article_id = f"{cohort}:{source.document_hash}:article:{source.article_number}"
        chapter_id = f"{cohort}:{source.document_hash}:chapter:{source.chapter_number}"
        references, unresolved = explicit_article_references(
            source.text, numbers_by_version[(source.document_key, cohort, source.document_hash)])
        for index, (content, units) in enumerate(formal_article_parts(source)):
            records.append(ChunkRecord(
                page_content=content,
                metadata={
                    "doc_id": f"{article_id}:chunk:{index + 1}",
                    "cohort": cohort, "created_at": upload_timestamp(source.updated_at) if source.updated_at else timestamp,
                    "structure": "article", "chapter_id": chapter_id, "chapter_title": source.chapter,
                    "article_id": article_id, "article_number": source.article_number,
                    "unit_ids": [f"{article_id}:{unit}" for unit in units],
                    "document_hash": source.document_hash,
                    "approval_status": source.approval_status,
                    "explicit_article_refs": references,
                    "unresolved_article_refs": unresolved,
                },
                source=source,
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                vector_id=f"{vector_prefix(source, cohort)}article:{source.article_number}:{index:04d}",
            ))
    for source in sources:
            title = source.section.strip()
            number, kind, body = item_body(source)
            cohort = infer_cohort(source.source_name, source.cohort or None)
            key = (source.document_key, cohort, number)
            if key in seen:
                raise ValueError(f"같은 문서/기수에 중복 항목 번호가 있습니다: {number}")
            seen.add(key)
            header = title + "\n"
            parts = split_body(body, chunk_size - len(header), chunk_overlap)
            for index, part in enumerate(parts):
                content = header + part
                records.append(ChunkRecord(
                    page_content=content,
                    metadata={"doc_id": f"{number}-{index + 1}", "type": kind, "cohort": cohort,
                              "created_at": upload_timestamp(source.updated_at) if source.updated_at else timestamp},
                    source=source,
                    content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    vector_id=f"{vector_prefix(source, cohort)}{number}:{index:04d}",
                ))
    return records


def to_documents(records: Iterable[ChunkRecord]) -> list[Any]:
    from langchain_core.documents import Document
    return [Document(page_content=r.page_content, metadata=dict(r.metadata)) for r in records]


def chunk_policy_docx(file: Path | bytes, **kwargs: Any) -> list[Any]:
    """LMS entry point: uploaded DOCX -> LangChain Document objects."""
    return to_documents(build_records(load_docx(file, **kwargs)))


def write_jsonl(records: Iterable[ChunkRecord], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record.to_json(), ensure_ascii=False) + "\n")
            count += 1
    return count


def upsert_vectors(
    index: Any, records: Sequence[ChunkRecord], vectors: Sequence[Sequence[float]],
    namespace: str = NAMESPACE, batch_size: int = 100,
) -> int:
    if len(records) != len(vectors):
        raise ValueError("청크와 임베딩 개수가 다릅니다")
    if batch_size <= 0:
        raise ValueError("batch_size는 양수여야 합니다")
    if len({r.vector_id for r in records}) != len(records):
        raise ValueError("중복 Pinecone vector ID가 있습니다")
    for start in range(0, len(records), batch_size):
        payload = [{"id": r.vector_id, "values": list(v),
                    "metadata": {"page_content": r.page_content, **r.metadata}}
                   for r, v in zip(records[start:start + batch_size], vectors[start:start + batch_size])]
        retry(lambda: index.upsert(vectors=payload, namespace=namespace))
    return len(records)


def upload_records(records: Sequence[ChunkRecord], *, namespace: str = NAMESPACE, index_name: str = INDEX_NAME) -> dict[str, Any]:
    """Upsert all batches before deleting stale IDs of these documents/cohorts.

    No delete_all or local manifest. Prefixes isolate different documents/cohorts.
    Re-ingesting the same source_name/cohort updates the same stable vector IDs.
    Supply a complete document snapshot rather than selected items.
    """
    if not records:
        raise ValueError("적재할 정책 청크가 없습니다")
    ids = {r.vector_id for r in records}
    if len(ids) != len(records):
        raise ValueError("중복 Pinecone vector ID가 있습니다")
    # ponytail: serialize ingestion of the same document/cohort; LMS workers
    # should take a per-document DB lock if concurrent replacements are allowed.
    load_env()
    key = os.getenv("PINECONE_API_KEY2") or os.getenv("PINECONE_API_KEY")
    if not key or not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY와 PINECONE_API_KEY2(또는 PINECONE_API_KEY)가 필요합니다")
    from openai import OpenAI
    from pinecone import Pinecone

    model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    dimensions = int(os.getenv("OPENAI_EMBEDDING_DIMENSION", "1536"))
    pc = Pinecone(api_key=key)
    description = retry(lambda: pc.describe_index(index_name))
    if description.dimension != dimensions or description.metric != "cosine":
        raise ValueError(f"student 인덱스는 dimension={dimensions}, metric=cosine이어야 합니다")
    index = pc.Index(host=description.host)
    prefixes = {vector_prefix(r.source, str(r.metadata["cohort"])) for r in records}
    old_ids: set[str] = set()
    for prefix in sorted(prefixes):
        for batch in index.list(prefix=prefix, namespace=namespace):
            old_ids.update(batch)
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], max_retries=2)
    vectors: list[list[float]] = []
    for start in range(0, len(records), 96):
        inputs = [r.page_content for r in records[start:start + 96]]
        response = retry(lambda: client.embeddings.create(model=model, input=inputs, dimensions=dimensions))
        vectors.extend(item.embedding for item in sorted(response.data, key=lambda item: item.index))
    if any(len(v) != dimensions for v in vectors):
        raise ValueError("임베딩 차원이 student 인덱스와 다릅니다")
    upserted = upsert_vectors(index, records, vectors, namespace)
    stale = sorted(old_ids - ids)
    for start in range(0, len(stale), 1000):
        batch = stale[start:start + 1000]
        retry(lambda: index.delete(ids=batch, namespace=namespace))
    return {"index": index_name, "namespace": namespace, "upserted": upserted, "deleted_stale": len(stale)}


def ingest_policy_docx(file: Path | bytes, *, dry_run: bool = False, **kwargs: Any) -> dict[str, Any]:
    """LMS supplies source_name, cohort and the persisted upload timestamp."""
    sections = load_docx(file, **kwargs)
    records = build_records(sections)
    result = {"items": len(sections), "chunks": len(records), "dry_run": dry_run}
    if not dry_run:
        result.update(upload_records(records))
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["ingest"], nargs="?", default="ingest")
    parser.add_argument("paths", nargs="*", help="DOCX paths; default: SKN34_학생_정책집.docx")
    parser.add_argument("--cohort", help="기수; 생략하면 표지/파일명에서 확인")
    parser.add_argument("--created-at", help="업로드 일시 ISO 8601; 생략하면 현재 UTC 일시")
    parser.add_argument("--dry-run", action="store_true", help="JSONL만 생성; API 호출/Pinecone 변경 없음")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    try:
        timestamp = upload_timestamp(args.created_at)
        sections = [s for path in discover_files(args.paths)
                    for s in load_docx(path, cohort=args.cohort, created_at=timestamp)]
        records = build_records(sections)
        if not records:
            raise ValueError("적재할 정책 항목이 없습니다")
        output = Path(args.output).resolve()
        write_jsonl(records, output)
        result = {"items": len(sections), "chunks": len(records),
                  "max_chars": max(len(r.page_content) for r in records),
                  "index": INDEX_NAME, "namespace": NAMESPACE,
                  "output": str(output), "dry_run": args.dry_run}
        if not args.dry_run:
            result.update(upload_records(records))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
