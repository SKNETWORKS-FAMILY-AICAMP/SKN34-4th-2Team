"""Dependency-free lexical retrieval and fusion for offline policy evaluation.

Callers must scope rows to the permitted cohort and document version before
retrieval. This module does not connect to Pinecone or change production search.
"""

from collections import Counter
import math
import re
import unicodedata


_TOKEN = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?\s*%|\d+(?:,\d{3})*(?:\.\d+)?|[가-힣]+|[^\W\d_]+", re.UNICODE)
_KOREAN = re.compile(r"[가-힣]+\Z")


def tokenize(text: str) -> list[str]:
    """Keep words/numbers and add Korean bigrams within each Korean word.

    Percentages are separate tokens from bare numbers, and thousands separators
    are retained. Korean bigrams provide partial matching without a morphological
    analyzer; they never join syllables across word boundaries.
    """
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    normalized = unicodedata.normalize("NFKC", text).lower()
    result = []
    for match in _TOKEN.finditer(normalized):
        token = re.sub(r"\s+", "", match.group())
        result.append(token)
        if _KOREAN.fullmatch(token) and len(token) > 2:
            result.extend(token[offset : offset + 2] for offset in range(len(token) - 1))
    return result


def _positive_integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _row_id(row: dict) -> str:
    if not isinstance(row, dict):
        raise ValueError("each row must be a dictionary")
    row_id = row.get("id")
    if not isinstance(row_id, str) or not row_id.strip():
        raise ValueError("each row must have a non-empty string id")
    return row_id


def bm25_rank(query: str, rows: list[dict], limit: int = 12) -> list[tuple[float, dict]]:
    """Rank a scoped corpus with BM25 (k1=1.2, b=0.75).

    Duplicate corpus IDs are rejected. Documents with no query-token overlap
    are excluded rather than contributing arbitrary zero-score fusion results.
    """
    _positive_integer(limit, "limit")
    query_tokens = set(tokenize(query))
    documents = []
    seen = set()
    document_frequency = Counter()
    for row in rows:
        row_id = _row_id(row)
        if row_id in seen:
            raise ValueError(f"duplicate corpus id: {row_id}")
        seen.add(row_id)
        content = row.get("page_content")
        if not isinstance(content, str):
            raise ValueError(f"page_content must be a string for row {row_id}")
        frequencies = Counter(tokenize(content))
        length = sum(frequencies.values())
        documents.append((row, frequencies, length))
        document_frequency.update(frequencies.keys())
    if not documents or not query_tokens:
        return []
    corpus_size = len(documents)
    average_length = sum(length for _, _, length in documents) / corpus_size
    if not average_length:
        return []
    k1, b = 1.2, 0.75
    ranked = []
    for row, frequencies, length in documents:
        score = 0.0
        for token in sorted(query_tokens.intersection(frequencies)):
            frequency = frequencies[token]
            idf = math.log(1 + (corpus_size - document_frequency[token] + 0.5) / (document_frequency[token] + 0.5))
            denominator = frequency + k1 * (1 - b + b * length / average_length)
            score += idf * frequency * (k1 + 1) / denominator
        if score > 0:
            ranked.append((score, row))
    return sorted(ranked, key=lambda item: (-item[0], item[1]["id"]))[:limit]


def rrf_rank(
    rankings: list[list[tuple[float, dict]]],
    limit: int = 4,
    rank_constant: int = 60,
) -> list[tuple[float, dict]]:
    """Fuse ordered scoped rankings by reciprocal rank, not raw score scale.

    IDs are local to the already scoped corpus. Repeated IDs in one ranking
    contribute once and do not consume an additional rank. Finite negative
    retrieval scores are valid. The first row for each ID is retained.
    """
    _positive_integer(limit, "limit")
    _positive_integer(rank_constant, "rank_constant")
    totals = Counter()
    rows_by_id = {}
    for ranking in rankings:
        seen = set()
        for score, row in ranking:
            row_id = _row_id(row)
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
                raise ValueError(f"ranking score must be a finite number for row {row_id}")
            if row_id in seen:
                continue
            seen.add(row_id)
            totals[row_id] += 1.0 / (rank_constant + len(seen))
            rows_by_id.setdefault(row_id, row)
    ordered = sorted(totals, key=lambda row_id: (-totals[row_id], row_id))[:limit]
    return [(totals[row_id], rows_by_id[row_id]) for row_id in ordered]
