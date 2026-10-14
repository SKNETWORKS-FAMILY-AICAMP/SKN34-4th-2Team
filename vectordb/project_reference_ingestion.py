"""Project reference CSV -> Pinecone ingestion."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    from vectordb.utills import load_env, normalize_text, retry
except ModuleNotFoundError:  # Support `python vectordb/project_reference_ingestion.py`.
    from utills import load_env, normalize_text, retry

MODULE_DIR = Path(__file__).resolve().parent
DATA_DIR = MODULE_DIR / "data" / "project_reference"
DEFAULT_OUTPUT = MODULE_DIR / "project_reference_documents.jsonl"
INDEX_NAME = "student"
NAMESPACE = "project_reference"
REQUIRED_COLUMNS = {"기수", "구분", "주제", "기획설명", "활용데이터", "활용기술", "깃허브 주소"}
GITHUB_REPOSITORY = re.compile(r"SKNETWORKS-FAMILY-AICAMP/[A-Za-z0-9_.-]+", re.IGNORECASE)
TEAM_RE = re.compile(r"[-_](\d+)team", re.IGNORECASE)


def _field(value: str) -> str:
    return " ".join(normalize_text(value).split())


def _project_round(category: str) -> str:
    match = re.fullmatch(r"교과목실습(\d+)", category.strip())
    if match:
        return str(int(match.group(1)))
    if category.strip() == "최종프로젝트":
        return "final"
    raise ValueError(f"알 수 없는 프로젝트 구분입니다: {category!r}")


def _project_heading(cohort: str, project_round: str, team: str | None) -> str:
    round_label = "최종 프로젝트" if project_round == "final" else f"{project_round}차 프로젝트"
    return f"SKN {cohort}기 {round_label} {team}팀" if team else f"SKN {cohort}기 {round_label} (팀 번호 미상)"


def _github_url(value: str) -> str:
    match = GITHUB_REPOSITORY.search(value)
    if not match:
        raise ValueError(f"GitHub 저장소 주소를 찾을 수 없습니다: {value!r}")
    return f"https://github.com/{match.group(0).rstrip('.')}"


def _team(value: str) -> str | None:
    match = TEAM_RE.search(_github_url(value))
    if not match:
        return None
    return str(int(match.group(1)))


def _csv_files(path: Path) -> list[Path]:
    files = sorted(path.glob("*.csv")) if path.is_dir() else [path]
    if not files or any(not file.is_file() for file in files):
        raise FileNotFoundError(f"프로젝트 레퍼런스 CSV를 찾을 수 없습니다: {path}")
    return files


def load_documents(path: Path = DATA_DIR) -> tuple[list[Any], int]:
    try:
        from langchain_core.documents import Document
    except ImportError as exc:
        raise RuntimeError("Document 생성에는 langchain-core가 필요합니다") from exc

    documents: list[Any] = []
    skipped = 0
    indexes: defaultdict[tuple[str, str], int] = defaultdict(int)
    for file in _csv_files(path):
        with file.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"CSV 필수 열이 없습니다: {', '.join(sorted(missing))}")
            for row in reader:
                subject = _field(row["주제"] or "")
                if not subject:
                    skipped += 1
                    continue
                cohort = _field(row["기수"] or "")
                if not cohort.isdigit():
                    raise ValueError(f"기수는 숫자여야 합니다: {row['기수']!r}")
                project_round = _project_round(row["구분"] or "")
                team = _team(row["깃허브 주소"] or "")
                key = (str(int(cohort)), project_round)
                index = indexes[key]
                indexes[key] += 1
                page_content = "\n".join([
                    _project_heading(key[0], project_round, team),
                    f"주제: {subject}",
                    f"기획 설명: {_field(row['기획설명'] or '')}",
                    f"활용 데이터: {_field(row['활용데이터'] or '')}",
                    f"활용기술: {_field(row['활용기술'] or '')}",
                ])
                documents.append(Document(page_content=page_content, metadata={
                    "doc_id": f"{key[0]}_{project_round}_{index}",
                    "cohort": key[0],
                    "project_round": project_round,
                    "github_url": _github_url(row["깃허브 주소"] or ""),
                }))
    return documents, skipped


def write_jsonl(documents: Iterable[Any], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as stream:
        for document in documents:
            stream.write(json.dumps({
                "page_content": document.page_content,
                "metadata": document.metadata,
            }, ensure_ascii=False) + "\n")
            count += 1
    return count


def upload_documents(documents: Sequence[Any]) -> int:
    if not documents:
        return 0
    missing = [name for name in ("OPENAI_API_KEY", "PINECONE_API_KEY2") if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"필수 환경변수가 없습니다: {', '.join(missing)}")
    try:
        from langchain_openai import OpenAIEmbeddings
        from pinecone import Pinecone
    except ImportError as exc:
        raise RuntimeError("적재에는 langchain-openai와 pinecone이 필요합니다") from exc

    embeddings = OpenAIEmbeddings(
        model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        dimensions=int(os.getenv("OPENAI_EMBEDDING_DIMENSION", "1536")),
    )
    index = Pinecone(api_key=os.environ["PINECONE_API_KEY2"]).Index(INDEX_NAME)
    total = 0
    for start in range(0, len(documents), 100):
        batch = documents[start:start + 100]
        vectors = retry(lambda batch=batch: embeddings.embed_documents([
            document.page_content for document in batch
        ]))
        if len(vectors) != len(batch):
            raise RuntimeError("문서와 embedding 개수가 다릅니다")
        payload = [
            {
                "id": document.metadata["doc_id"],
                "values": vector,
                "metadata": {"page_content": document.page_content, **document.metadata},
            }
            for document, vector in zip(batch, vectors)
        ]
        retry(lambda payload=payload: index.upsert(vectors=payload, namespace=NAMESPACE))
        total += len(batch)
    return total


def run(args: argparse.Namespace) -> dict[str, Any]:
    load_env()
    documents, skipped = load_documents(Path(args.input).resolve())
    if not documents:
        raise ValueError("적재할 프로젝트 레퍼런스가 없습니다")
    output = Path(args.output).resolve()
    write_jsonl(documents, output)
    upserted = 0 if args.dry_run else upload_documents(documents)
    return {
        "documents": len(documents),
        "skipped": skipped,
        "index": INDEX_NAME,
        "namespace": NAMESPACE,
        "upserted": upserted,
        "output": str(output),
        "dry_run": args.dry_run,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--input", default=str(DATA_DIR))
    root.add_argument("--output", default=str(DEFAULT_OUTPUT))
    root.add_argument("--dry-run", action="store_true", help="JSONL까지만 생성하고 Pinecone을 변경하지 않음")
    return root


def main(argv: Sequence[str] | None = None) -> int:
    try:
        print(json.dumps(run(parser().parse_args(argv)), ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
