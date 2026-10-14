"""Build deterministic Pinecone records from PostgreSQL policy revisions."""

from __future__ import annotations

import hashlib
from dataclasses import replace


def records_for_revision(document, revision):
    # Imported lazily so Django commands can first add the repository root to sys.path.
    from vectordb.policy_ingestion import SourceSection, build_records

    source = SourceSection(
        text=revision.extracted_text,
        source_type=document.source_type,
        source_name=document.source_name,
        source_url=document.source_url,
        updated_at=(revision.source_updated_at or revision.ingested_at).isoformat(),
    )
    records = build_records([source], model=None)
    if not records:
        raise ValueError(f"policy document {document.pk} produced no searchable chunks")
    identity = hashlib.sha256(document.source_key.encode("utf-8")).hexdigest()[:20]
    return [
        replace(record, metadata={
            **record.metadata,
            "doc_id": f"p2-{identity}-{position}",
            "policy_document_id": document.pk,
            "policy_revision_id": revision.pk,
            "policy_revision_hash": revision.content_sha256,
        })
        for position, record in enumerate(records)
    ]
