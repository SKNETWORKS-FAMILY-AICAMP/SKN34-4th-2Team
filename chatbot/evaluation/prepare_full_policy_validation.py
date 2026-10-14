"""Prepare full policy DOCX inputs locally; no upload, activation or API calls.

Run from the repository root with
``python -m chatbot.evaluation.prepare_full_policy_validation --help``.
An existing output directory is never reused or overwritten.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from typing import Any


def _heading_inventory(data: bytes) -> dict[str, Any]:
    # Use the same Heading-style chapter/article recognition as load_docx;
    # cover text and plain-text TOC entries are not counted as body headings.
    from docx import Document
    from vectordb.policy_ingestion import ARTICLE_HEADING, CHAPTER_HEADING

    chapters, articles = [], []
    for paragraph in Document(BytesIO(data)).paragraphs:
        if not paragraph.style.name.startswith("Heading"):
            continue
        text = paragraph.text.strip()
        chapter = CHAPTER_HEADING.fullmatch(text)
        article = ARTICLE_HEADING.fullmatch(text)
        if chapter:
            chapters.append(chapter.group("number"))
        elif article:
            number = article.group("number")
            if article.group("sub"):
                number += "-" + article.group("sub")
            articles.append(number)
    return {
        "chapter_count": len(chapters),
        "chapter_numbers": chapters,
        "article_count": len(articles),
        "article_numbers": articles,
    }


def _prepare_document(
    path: Path, *, content_kind: str, source_cohort: str | None,
    test_target: str | None, copy_relative_path: str,
) -> tuple[dict[str, Any], bytes]:
    if path.suffix.lower() != ".docx" or not path.is_file():
        raise ValueError(f"A local DOCX file is required: {path}")
    data = path.read_bytes()
    digest = sha256(data).hexdigest()
    issues: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "filename": path.name,
        "source_path": str(path),
        "sha256": digest,
        "byte_count": len(data),
        "content_kind": content_kind,
        "source_cohort": source_cohort,
        "test_target_mapping": test_target,
        "copy_path": copy_relative_path,
        "chapter_count": None,
        "chapter_numbers": [],
        "article_count": None,
        "article_numbers": [],
        "chunk_count": None,
        "issues": issues,
    }
    try:
        result.update(_heading_inventory(data))
    except Exception as exc:
        issues.append({"stage": "heading_inventory", "error_type": type(exc).__name__,
                       "message": str(exc)})

    if content_kind == "supplement":
        # document_records only supports policy/curriculum. Do not pass a
        # supplement as policy merely to make its parsing appear successful.
        result["document_records"] = {"status": "not_applicable", "records": []}
        result["criteria_snapshot"] = {"status": "not_applicable"}
        issues.append({"stage": "classification", "code": "supplement_not_policy_body",
                       "message": "보충자료는 별도 입력이며 정책 파서·계산 기준 추출 대상이 아닙니다."})
        return result, data

    # These modules import definitions only: connect(), upload_records(),
    # _read_snapshot(), load_env() and remote clients are never invoked here.
    from chatbot.cohort_document_rag import document_records
    from chatbot.active_policy_rules import criteria_snapshot

    key = f"cohorts/{source_cohort}/policy/rag/{digest[:32]}.docx"
    result["local_parser_key"] = key
    result["local_parser_key_note"] = "Synthetic local parser identity; not an uploaded object."
    try:
        records = document_records(data, path.name, source_cohort, "policy", key)
    except Exception as exc:
        result["document_records"] = {"status": "failed", "records": []}
        result["criteria_snapshot"] = {"status": "not_run", "reason": "document_records_failed"}
        issues.append({"stage": "document_records", "error_type": type(exc).__name__,
                       "message": str(exc)})
        return result, data

    result["chunk_count"] = len(records)
    result["document_records"] = {"status": "parsed", "records": [r.to_json() for r in records]}
    parsed_articles = list(dict.fromkeys(
        str(r.metadata["article_number"]) for r in records if r.metadata.get("article_number")
    ))
    result["parsed_article_numbers"] = parsed_articles
    result["parsed_chapter_count"] = len({r.source.chapter_number for r in records if r.source.chapter_number})
    if not parsed_articles:
        issues.append({"stage": "document_records", "code": "no_formal_articles",
                       "message": "파서 결과에서 장/조 형식의 조문을 확인하지 못했습니다."})
    if parsed_articles != result["article_numbers"]:
        issues.append({"stage": "document_records", "code": "article_inventory_mismatch",
                       "message": "원문 Heading 조 번호 목록과 파서 결과가 일치하지 않습니다."})
    try:
        snapshot = criteria_snapshot(records, source_cohort, key)
        result["criteria_snapshot"] = snapshot
        for purpose, reason in snapshot.get("issues", {}).items():
            issues.append({"stage": "criteria_snapshot", "purpose": purpose, "reason": reason})
        if snapshot.get("status") == "unavailable":
            issues.append({"stage": "criteria_snapshot", "code": "unavailable",
                           "message": snapshot.get("reason", "")})
        # Preserve the parser's draft/unverified state. Never infer approval or
        # an effective date from filesystem timestamps or preparation time.
    except Exception as exc:
        result["criteria_snapshot"] = {"status": "failed"}
        issues.append({"stage": "criteria_snapshot", "error_type": type(exc).__name__,
                       "message": str(exc)})
    return result, data


def prepare(
    *, policy_34: Path, policy_40: Path, output_dir: Path,
    supplement: Path | None = None,
) -> Path:
    output_dir = Path(output_dir).resolve()
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"Choose a new output directory: {output_dir}")
    specs = [
        (Path(policy_34).resolve(), "policy_body", "cohort_34", "cohort-test003", "policy-34"),
        (Path(policy_40).resolve(), "policy_body", "cohort_40", "cohort-test004", "policy-40"),
    ]
    if supplement is not None:
        specs.append((Path(supplement).resolve(), "supplement", None, None, "supplement"))
    prepared = []
    for path, kind, cohort, target, folder in specs:
        relative = (Path("sources") / folder / path.name).as_posix()
        prepared.append(_prepare_document(
            path, content_kind=kind, source_cohort=cohort,
            test_target=target, copy_relative_path=relative,
        ))

    # Reserve a new directory exclusively; even concurrent runs cannot
    # overwrite one another. Keep partial output on failure for diagnosis.
    output_dir.mkdir(parents=True, exist_ok=False)
    documents = []
    for result, data in prepared:
        destination = output_dir / result["copy_path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(data)
        copy_hash = sha256(destination.read_bytes()).hexdigest()
        if copy_hash != result["sha256"]:
            raise ValueError(f"Source copy hash mismatch: {destination}")
        result["copy_sha256"] = copy_hash
        result["copy_hash_matches_source"] = True
        documents.append(result)
    manifest = {
        "schema_version": 1,
        "status": "prepared_with_issues" if any(d["issues"] for d in documents) else "prepared",
        "scope": "offline_parsing_and_criteria_extraction_only",
        "external_calls": 0,
        "approval_status": "not_determined_by_preparation",
        "effective_date": None,
        "test_mapping_note": "SKN34/40 원본의 테스트 대상 대응만 기록합니다. 원문 기수명은 변경하지 않았으며 엔코아 규정이 아닙니다.",
        "parser_metadata_note": "created_at/updated_at은 파서 실행 시각이며 승인일·시행일이 아닙니다.",
        "documents": documents,
    }
    manifest_path = output_dir / "manifest.json"
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy-34", type=Path, required=True)
    parser.add_argument("--policy-40", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--supplement", type=Path)
    args = parser.parse_args()
    path = prepare(policy_34=args.policy_34, policy_40=args.policy_40,
                   output_dir=args.output_dir, supplement=args.supplement)
    print(path)


if __name__ == "__main__":
    main()
