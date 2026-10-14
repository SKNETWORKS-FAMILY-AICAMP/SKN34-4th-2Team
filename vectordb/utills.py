"""Shared helpers for Pinecone ingestion scripts."""

from __future__ import annotations

import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable

MODULE_DIR = Path(__file__).resolve().parent
ROOT = MODULE_DIR.parent
MEANINGFUL_SYMBOLS = {"+", "=", "<", ">", "|", "₩", "$", "€", "¥"}


def load_env(path: Path | None = None) -> None:
    """Load .env without overriding values already supplied by the host."""
    for candidate in [path] if path else [MODULE_DIR / ".env", ROOT / ".env"]:
        if not candidate.exists():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                os.environ.setdefault(key, value.strip().strip("'\""))


def retry(call: Callable[[], Any], attempts: int = 3) -> Any:
    for attempt in range(attempts):
        try:
            return call()
        except Exception:
            if attempt + 1 == attempts:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(
        char if char == "\n" or char in MEANINGFUL_SYMBOLS or unicodedata.category(char)[0] not in {"C", "S"} else " "
        for char in text
    )
    text = re.sub(r"[^\S\n]+", " ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    if chunk_size <= 0 or not 0 <= chunk_overlap < chunk_size:
        raise ValueError("chunk_size는 양수이고 chunk_overlap보다 커야 합니다")
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError:
        # ponytail: keep local development usable when optional LangChain deps are absent
        step = chunk_size - chunk_overlap
        chunks: list[str] = []
        start = 0
        while start < len(text):
            chunk = text[start:start + chunk_size].strip()
            if chunk:
                chunks.append(chunk)
            if start + chunk_size >= len(text):
                break
            start += step
        return chunks
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )
    return splitter.split_text(text)
