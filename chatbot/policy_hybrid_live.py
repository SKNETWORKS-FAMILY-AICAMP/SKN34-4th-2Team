"""Opt-in local preview: read-only Pinecone corpus + BM25/RRF.

No vector writes or S3 operations. Cache is process-local and expires after 60s.
The active namespace is resolved by the normal authenticated cohort retriever.
"""
from copy import deepcopy
from threading import Lock
import time

from langchain_core.documents import Document
from chatbot.evaluation.policy_hybrid import bm25_rank, rrf_rank

_cache = {}
_lock = Lock()


def corpus(index, namespace, cohort):
    from chatbot.cohort_document_rag import document_namespace, valid_cohort_code
    if not valid_cohort_code(cohort):
        raise ValueError('Invalid policy cohort')
    key = (id(index), namespace, cohort)
    with _lock:
        entry = _cache.get(key)
        if entry and time.monotonic() - entry[0] < 60:
            return deepcopy(entry[1])
        ids = []
        for page in index.list(namespace=namespace):
            ids.extend(page)
            if len(ids) > 5000:
                raise ValueError('Local hybrid preview corpus exceeds 5000 vectors')
        rows = []
        for offset in range(0, len(ids), 100):
            response = index.fetch(ids=ids[offset:offset+100], namespace=namespace)
            for vector_id, vector in (response.vectors or {}).items():
                metadata = dict(vector.metadata or {})
                if metadata.get('cohort') != cohort:
                    continue
                if namespace.startswith('cohort-doc-'):
                    storage = str(metadata.get('storage_key', ''))
                    if (metadata.get('kind') != 'policy'
                        or not storage.startswith(f'cohorts/{cohort}/policy/')
                        or document_namespace(storage) != namespace):
                        continue
                content = str(metadata.pop('page_content', '')).strip()
                if content:
                    rows.append({'id': str(vector_id), 'page_content': content, 'metadata': metadata})
        # Do not silently present vector-only results as hybrid on a failed load.
        if not rows:
            raise ValueError('No scoped policy corpus available for hybrid preview')
        if len(_cache) >= 16:
            _cache.clear()
        _cache[key] = (time.monotonic(), rows)
        return deepcopy(rows)


def fuse(index, namespace, cohort, query, vector_documents, k):
    rows = corpus(index, namespace, cohort)
    vectors = [(1.0, {'id': str(d.id), 'page_content': d.page_content,
                     'metadata': deepcopy(d.metadata)}) for d in vector_documents]
    lexical = bm25_rank(query, rows, limit=max(k, 12))
    ranked = rrf_rank([vectors, lexical], limit=k)
    documents = []
    for _, row in ranked:
        row['metadata']['retrieval_method'] = 'hybrid_bm25_rrf_local_preview'
        documents.append(Document(id=row['id'], page_content=row['page_content'], metadata=row['metadata']))
    return documents
