"""공지 청크/임베딩. functions/src/noticeVectors.ts 와 같은 순서."""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime
from typing import Any

MEANINGFUL_SYMBOLS = {"+", "=", "<", ">", "|", "₩", "$", "€", "¥"}
CHUNK_SIZE = 500
CHUNK_OVERLAP = 40
INDEX_NAME = os.environ.get("PINECONE_STUDENT_INDEX_NAME", "student")
NAMESPACE = "notice"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(
        char if char == "\n" or char in MEANINGFUL_SYMBOLS or unicodedata.category(char)[0] not in {"C", "S"} else " "
        for char in text
    )
    text = re.sub(r"[^\S\n]+", " ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP) -> list[str]:
    if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunkSize는 양수이고 chunkOverlap보다 커야 합니다.")
    text = normalize_text(text)
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            window = text[start:end]
            minimum_boundary = chunk_size // 2
            for separator in ("\n\n", "\n", ". ", " "):
                boundary = window.rfind(separator)
                if boundary >= minimum_boundary:
                    end = start + boundary + (1 if separator == ". " else 0)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - chunk_overlap)
    return chunks


def vector_id(cohort_code: str, notice_id: int, chunk_index: int) -> str:
    return f"{cohort_code}_n{notice_id}_{chunk_index}"


def timestamp_to_iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return ""


def build_records(cohort_code: str, notice_id: int, data: dict[str, Any]) -> list[dict[str, Any]]:
    chunks = chunk_text(str(data.get("content") or ""))
    records = []
    for index, page_content in enumerate(chunks):
        vid = vector_id(cohort_code, notice_id, index)
        records.append({
            "id": vid,
            "values": None,
            "metadata": {
                "page_content": page_content,
                "doc_id": vid,
                "cohort": cohort_code,
                "author_id": str(data.get("author_id") or data.get("authorId") or ""),
                "author_name": str(data.get("author_name") or data.get("authorName") or ""),
                "is_favorite": data.get("is_favorite") is True or data.get("isFavorite") is True,
                "created_at": timestamp_to_iso(data.get("created_at") or data.get("createdAt")),
                "updated_at": timestamp_to_iso(data.get("updated_at") or data.get("updatedAt")),
                "priority": data.get("priority") if isinstance(data.get("priority"), int) else 0,
                "title": str(data.get("title") or ""),
            },
            "page_content": page_content,
        })
    return records


def _index():
    from pinecone import Pinecone

    api_key = os.environ.get("PINECONE_API_KEY2") or os.environ.get("PINECONE_API_KEY")
    if not api_key:
        raise RuntimeError("PINECONE_API_KEY2 가 없습니다")
    return Pinecone(api_key=api_key).Index(INDEX_NAME)


def _embed(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts, dimensions=EMBEDDING_DIMENSION)
    return [item.embedding for item in response.data]


def delete_notice_vectors(cohort_code: str, notice_id: int, chunk_count: int) -> None:
    if chunk_count <= 0:
        return
    index = _index()
    ids = [vector_id(cohort_code, notice_id, i) for i in range(chunk_count)]
    index.delete(ids=ids, namespace=NAMESPACE)


def upsert_notice_vectors(cohort_code: str, notice_id: int, data: dict[str, Any]) -> int:
    records = build_records(cohort_code, notice_id, data)
    if not records:
        delete_notice_vectors(cohort_code, notice_id, int(data.get("vector_chunk_count") or 0))
        return 0
    vectors = _embed([row["page_content"] for row in records])
    index = _index()
    index.upsert(
        vectors=[
            {"id": row["id"], "values": values, "metadata": row["metadata"]}
            for row, values in zip(records, vectors)
        ],
        namespace=NAMESPACE,
    )
    return len(records)


def clear_notice_namespace() -> None:
    _index().delete(delete_all=True, namespace=NAMESPACE)


def smoke_search(cohort_code: str) -> int:
    vectors = _embed(["공지"])
    result = _index().query(
        vector=vectors[0],
        top_k=3,
        namespace=NAMESPACE,
        filter={"cohort": {"$eq": cohort_code}},
        include_metadata=True,
    )
    return len(result.matches or [])
