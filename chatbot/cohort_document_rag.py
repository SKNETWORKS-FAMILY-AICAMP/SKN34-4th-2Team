"""Versioned cohort documents: publish the DB pointer only after indexing succeeds."""
from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path
import re
import os
import time
from dataclasses import replace
from psycopg.errors import UndefinedTable

from chatbot.database import connect
from vectordb.policy_ingestion import (
    SourceSection, ChunkRecord, load_docx, build_records, split_body, upload_records,
)

MAX_BYTES = 10 * 1024 * 1024


def valid_cohort_code(cohort: str) -> bool:
    return bool(re.fullmatch(r'cohort(?:_\d{1,3}|-[a-z0-9]{7})', cohort))


def document_namespace(key: str) -> str:
    return 'cohort-doc-' + hashlib.sha256(key.encode()).hexdigest()[:32]


def indexed_key(key: str) -> bool:
    return bool(re.fullmatch(r'cohorts/[^/]+/(?:policy|curriculum)/rag/[a-f0-9]{32}\.(?:pdf|docx)', key))


def document_records(data: bytes, filename: str, cohort: str, kind: str, key: str):
    if kind not in ('policy', 'curriculum') or not valid_cohort_code(cohort):
        raise ValueError('지원하지 않는 기수 또는 문서 종류입니다.')
    if not data or len(data) > MAX_BYTES:
        raise ValueError('문서는 10MB 이하여야 합니다.')
    if not key.startswith(f'cohorts/{cohort}/{kind}/'):
        raise ValueError('문서 경로와 기수가 일치하지 않습니다.')
    suffix = Path(filename).suffix.lower()
    if suffix == '.docx' and kind == 'policy':
        records = build_records(load_docx(data, source_name=filename, cohort=cohort))
    elif suffix == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(data))
        records = []
        for page_number, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or '').strip()
            if not text:
                raise ValueError(f'{page_number}쪽에서 텍스트를 읽지 못했습니다. 텍스트 PDF를 올려 주세요.')
            source = SourceSection(text=text, source_type='pdf', source_name=filename,
                                   cohort=cohort, source_page=str(page_number))
            for i, part in enumerate(split_body(text, 1000, 120)):
                records.append(ChunkRecord(part, {'cohort': cohort, 'page': page_number}, source,
                    hashlib.sha256(part.encode()).hexdigest(), f'page-{page_number}-{i}'))
    else:
        raise ValueError('커리큘럼은 PDF, 정책은 정책집 양식 DOCX 또는 PDF여야 합니다.')
    if not records:
        raise ValueError('검색 가능한 본문이 없습니다.')
    namespace = document_namespace(key)
    # Vector IDs are local to this immutable upload namespace. Resolve links
    # only among the articles indexed in this one uploaded document.
    article_vectors: dict[str, list[str]] = {}
    for i, record in enumerate(records):
        article_id = record.metadata.get('article_id')
        if article_id:
            article_vectors.setdefault(str(article_id), []).append(f'doc-{i}')
    result = []
    for i, record in enumerate(records):
        metadata = {**record.metadata,
            'doc_id': f'{namespace}:{i}', 'cohort': cohort, 'kind': kind,
            'source_name': filename, 'title': filename + (' · ' + record.source.section if record.source.section else ''),
            'storage_key': key}
        article_id = metadata.get('article_id')
        if article_id:
            metadata['article_vector_ids'] = article_vectors[str(article_id)]
            prefix = f'{cohort}:{metadata["document_hash"]}:article:'
            metadata['reference_vector_ids'] = [vector_id
                for number in metadata.get('explicit_article_refs', [])
                for vector_id in article_vectors.get(prefix + str(number), [])
                if vector_id not in metadata['article_vector_ids']]
        # Pinecone stores page_content alongside metadata (40 KB/vector).
        # Reject oversized clauses before the S3 write and index activation.
        if len(json.dumps({'page_content': record.page_content, **metadata}, ensure_ascii=False).encode('utf-8')) > 38000:
            raise ValueError(f'조문 또는 메타데이터가 검색 색인 한도를 초과했습니다: {record.source.section}')
        result.append(replace(record, vector_id=f'doc-{i}', metadata=metadata))
    return result


def index_document(records, key: str):
    # Unique namespace per upload; failed/partial uploads are never selected by DB.
    if len(records) > 10000:
        raise ValueError('문서 청크 수가 검색 한도를 초과했습니다.')
    namespace = document_namespace(key)
    result = upload_records(records, namespace=namespace,
                            index_name=os.getenv('PINECONE_STUDENT_INDEX_NAME', 'student'))
    from pinecone import Pinecone
    index = Pinecone(api_key=os.getenv('PINECONE_API_KEY2') or os.getenv('PINECONE_API_KEY')).Index(
        os.getenv('PINECONE_STUDENT_INDEX_NAME', 'student'))
    expected = {r.vector_id for r in records}
    deadline = time.monotonic() + 30
    # Wait for query visibility before activating the database pointer.
    while True:
        fetched = index.fetch(ids=[records[0].vector_id], namespace=namespace)
        vector = fetched.vectors.get(records[0].vector_id)
        if vector:
            matches = index.query(namespace=namespace, vector=vector.values, top_k=len(records),
                include_metadata=False, include_values=False,
                filter={'cohort': {'$eq': records[0].metadata['cohort']}}).matches
            if {m.id for m in matches} == expected:
                return result
        if time.monotonic() >= deadline:
            raise TimeoutError('검색 색인의 반영을 확인하지 못했습니다.')
        time.sleep(1)


def active_policy_namespace(cohort: str) -> str:
    try:
        with connect(options='-c default_transaction_read_only=on', connect_timeout=10) as conn:
            deleting = conn.execute('''SELECT 1 FROM cohort_deletion_jobs
                WHERE cohort_code=%s''', (cohort,)).fetchone()
            if deleting:
                raise ValueError('삭제 중이거나 삭제된 기수의 정책 자료는 검색할 수 없습니다.')
            row = conn.execute('''SELECT p.storage_key FROM policy_documents p
                JOIN cohorts c ON p.source_key = 'cohort:' || c.id::text || ':policy'
                WHERE c.code=%s AND p.source_type='cohort_policy' AND p.is_active=true''', (cohort,)).fetchone()
    except UndefinedTable as exc:
        raise RuntimeError('기수 삭제 보호 migration 0017 적용 후 다시 시도해 주세요.') from exc
    if row:
        key = row[0] or ''
        if not indexed_key(key) or not key.startswith(f'cohorts/{cohort}/policy/'):
            raise ValueError('활성 정책의 검색 연결이 유효하지 않습니다.')
        return document_namespace(key)
    return 'policy'


def expand_policy_context(index, namespace: str, cohort: str, documents: list,
                          max_extra: int = 8, max_chars: int = 6000) -> list:
    """Restore bounded same-article context and explicit local references.

    Every fetched vector must still match the authenticated cohort and the
    upload version that supplied the search hit. No second vector search or
    inferred policy relationship is used here.
    """
    if not valid_cohort_code(cohort):
        raise ValueError('기수별 정책 검색 범위가 올바르지 않습니다.')
    seeds = []
    for doc in documents:
        metadata = doc.metadata
        if metadata.get('cohort') != cohort:
            continue
        if namespace.startswith('cohort-doc-'):
            key = str(metadata.get('storage_key', ''))
            if (not indexed_key(key) or document_namespace(key) != namespace
                or not key.startswith(f'cohorts/{cohort}/policy/')
                or metadata.get('kind') != 'policy'):
                continue
            if (metadata.get('structure') == 'article'
                and not re.fullmatch(r'[a-f0-9]{64}', str(metadata.get('document_hash', '')))):
                continue
        seeds.append(doc)
    if not namespace.startswith('cohort-doc-') or max_extra <= 0:
        return seeds
    requested: list[tuple[str, str]] = []
    truncated = False
    origins: dict[str, tuple[str, str]] = {}
    seed_ids = {str(doc.id) for doc in seeds}
    for doc in seeds:
        metadata = doc.metadata
        if metadata.get('kind') != 'policy' or metadata.get('structure') != 'article':
            continue
        key = str(metadata.get('storage_key', ''))
        digest = str(metadata.get('document_hash', ''))
        if not key.startswith(f'cohorts/{cohort}/policy/') or len(digest) != 64:
            continue
        for relation, ids in (('same_article', metadata.get('article_vector_ids', [])),
                              ('explicit_reference', metadata.get('reference_vector_ids', []))):
            for vector_id in ids:
                if not isinstance(vector_id, str) or vector_id in seed_ids or any(vector_id == item[0] for item in requested):
                    continue
                if len(requested) >= max_extra:
                    truncated = True
                    break
                requested.append((vector_id, relation))
                origins[vector_id] = (key, digest)
    if not requested:
        if truncated:
            for doc in seeds:
                doc.metadata['context_truncated'] = True
        return seeds
    from langchain_core.documents import Document
    fetched = index.fetch(ids=[item[0] for item in requested], namespace=namespace)
    extra = []
    added_chars = 0
    vectors = fetched.vectors or {}
    for vector_id, relation in requested:
        vector = vectors.get(vector_id)
        if vector is None:
            truncated = True
            continue
        metadata = dict(vector.metadata or {})
        key, digest = origins[vector_id]
        if (metadata.get('cohort') != cohort or metadata.get('kind') != 'policy'
            or metadata.get('storage_key') != key or metadata.get('document_hash') != digest
            or metadata.get('structure') != 'article'):
            truncated = True
            continue
        content = str(metadata.pop('page_content', '')).strip()
        if not content:
            truncated = True
            continue
        if added_chars + len(content) > max_chars:
            truncated = True
            continue
        added_chars += len(content)
        metadata['context_relation'] = relation
        extra.append(Document(id=vector_id, page_content=content, metadata=metadata))
    if truncated:
        for doc in seeds:
            doc.metadata['context_truncated'] = True
    return seeds + extra


def curriculum_context(cur, cid: int, cohort: str, query: str):
    try:
        deleting = cur.execute('''SELECT 1 FROM cohort_deletion_jobs
            WHERE cohort_id=%s''', (cid,)).fetchone()
    except UndefinedTable as exc:
        raise RuntimeError('기수 삭제 보호 migration 0017 적용 후 다시 시도해 주세요.') from exc
    if deleting:
        return {'items': [], 'unavailable_reason': 'cohort_deleting'}
    row = cur.execute('''SELECT storage_key, original_filename FROM curriculum_pdfs
        WHERE cohort_id=%s AND published=true''', (cid,)).fetchone()
    if not row or not row['storage_key']:
        return {'items': [], 'unavailable_reason': 'published_curriculum_not_found'}
    key = row['storage_key']
    if not key.startswith(f'cohorts/{cohort}/curriculum/'):
        raise ValueError('커리큘럼 경로와 기수가 일치하지 않습니다.')
    if indexed_key(key):
        import os
        from pinecone import Pinecone
        from langchain_openai import OpenAIEmbeddings
        index = Pinecone(api_key=os.getenv('PINECONE_API_KEY2') or os.getenv('PINECONE_API_KEY')).Index(
            os.getenv('PINECONE_STUDENT_INDEX_NAME', 'student'))
        embedding = OpenAIEmbeddings(model=os.getenv('OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small'),
            dimensions=int(os.getenv('OPENAI_EMBEDDING_DIMENSION', '1536')))
        response = index.query(namespace=document_namespace(key), vector=embedding.embed_query(query),
            top_k=8, include_metadata=True, filter={'cohort': {'$eq': cohort}})
        excerpts = [{'page': m.metadata.get('page'), 'text': m.metadata.get('page_content', '')}
                    for m in response.matches]
    else:
        # Legacy published PDFs have no index. Search chunks across the entire file,
        # never scan the prefix or silently cut off the back of the document.
        import boto3, os
        client = boto3.client('s3', region_name=os.getenv('AWS_REGION') or os.getenv('AWS_DEFAULT_REGION'))
        body = client.get_object(Bucket=os.getenv('AWS_S3_BUCKET') or os.getenv('S3_BUCKET'), Key=key)['Body']
        data = body.read(MAX_BYTES + 1)
        records = document_records(data, row['original_filename'] or 'curriculum.pdf', cohort, 'curriculum', key)
        words = set(re.findall(r'[0-9A-Za-z가-힣]{2,}', query.lower()))
        ranked = sorted(enumerate(records), key=lambda pair: (-sum(w in pair[1].page_content.lower() for w in words), pair[0]))
        excerpts = [{'page': r.metadata.get('page'), 'text': r.page_content} for _, r in ranked[:8]]
    return {'items': [{'path': key, 'name': row['original_filename'], 'excerpts': excerpts}],
            'retrieval': 'current_published_document', 'truncated': True}
