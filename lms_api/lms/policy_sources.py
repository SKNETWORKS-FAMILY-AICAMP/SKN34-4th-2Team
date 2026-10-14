"""Persist extracted policy sources before projecting them to search indexes."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import timezone
from typing import Iterable

from django.db import transaction
from django.utils.dateparse import parse_datetime

from lms.models import PolicyDocumentRevisions, PolicyDocuments


def prepare_documents(sections: Iterable[object]) -> list[dict]:
    """Group the existing SourceSection objects by their stable document_key."""
    grouped: dict[str, list[object]] = defaultdict(list)
    for section in sections:
        if not section.text.strip():
            continue
        grouped[section.document_key].append(section)

    prepared = []
    for key, parts in sorted(grouped.items()):
        first = parts[0]
        body = "\n\n".join(
            (f"## {part.section}\n" if part.section else "") + part.text.strip()
            for part in parts
        )
        edited = [parse_datetime(part.updated_at) for part in parts if part.updated_at]
        edited = [value if value.tzinfo else value.replace(tzinfo=timezone.utc) for value in edited if value]
        prepared.append({
            "source_key": key,
            "source_type": first.source_type,
            "source_name": first.source_name,
            "source_url": first.source_url,
            "title": first.source_name,
            "extracted_text": body,
            "content_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "source_updated_at": max(edited) if edited else None,
            "extraction_metadata": {
                "parts": [
                    {"section": part.section, "source_page": part.source_page, "cohort": part.cohort}
                    for part in parts
                ]
            },
        })
    return prepared


def persist_documents(prepared: Iterable[dict], *, using: str = "default") -> dict[str, int]:
    """Append a revision only when extracted content differs from the latest one."""
    counts = {"created": 0, "revised": 0, "unchanged": 0}
    for item in prepared:
        with transaction.atomic(using=using):
            document, created = PolicyDocuments.objects.using(using).get_or_create(
                source_key=item["source_key"],
                defaults={
                    "source_type": item["source_type"],
                    "source_name": item["source_name"],
                    "source_url": item["source_url"],
                    "title": item["title"],
                },
            )
            document = PolicyDocuments.objects.using(using).select_for_update().get(pk=document.pk)
            changed_fields = []
            for field in ("source_type", "source_name", "source_url", "title"):
                if getattr(document, field) != item[field]:
                    setattr(document, field, item[field])
                    changed_fields.append(field)
            if not document.is_active:
                document.is_active = True
                changed_fields.append("is_active")
            if changed_fields:
                document.save(using=using, update_fields=[*changed_fields, "updated_at"])
            latest = (PolicyDocumentRevisions.objects.using(using)
                      .filter(document=document).order_by("-revision_no").first())
            if latest and latest.content_sha256 == item["content_sha256"]:
                counts["unchanged"] += 1
                continue
            PolicyDocumentRevisions.objects.using(using).create(
                document=document,
                revision_no=(latest.revision_no + 1) if latest else 1,
                content_sha256=item["content_sha256"],
                extracted_text=item["extracted_text"],
                source_updated_at=item["source_updated_at"],
                extraction_metadata=item["extraction_metadata"],
            )
            counts["created" if created else "revised"] += 1
    return counts
