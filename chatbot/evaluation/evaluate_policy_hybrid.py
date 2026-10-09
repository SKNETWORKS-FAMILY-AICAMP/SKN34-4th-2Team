"""Compare vector-only and BM25/RRF using a completed local embedding run.

This experiment never creates embeddings or calls a model, Pinecone, or a DB.
It intentionally bypasses the supervisor to isolate retrieval ranking changes.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time

from chatbot.cohort_document_rag import valid_cohort_code
from chatbot.evaluation.evaluate_policy_rag import (
    cosine, digest, paired_comparison, score_evidence, validate_cases, write_json,
)
from chatbot.evaluation.policy_hybrid import bm25_rank, rrf_rank


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_inputs(baseline_run, cases_path):
    baseline_run = Path(baseline_run)
    manifest = json.loads((baseline_run / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('mode') != 'embedding' or manifest.get('completed') is not True:
        raise ValueError('A completed embedding run is required; no network fallback is permitted')
    if sha(cases_path) != manifest['cases_sha256']:
        raise ValueError('Use the exact case file from the approved baseline run')
    cases = json.loads(Path(cases_path).read_text(encoding='utf-8'))
    corpora, corpus_hashes = {}, {}
    for source in manifest['sources']:
        cohort = source['cohort']
        if not valid_cohort_code(cohort) or cohort in corpora:
            raise ValueError('Invalid or duplicate cohort in baseline manifest')
        path = baseline_run / f'corpus-{cohort}-B.json'
        rows = json.loads(path.read_text(encoding='utf-8'))
        if not rows or len({r['id'] for r in rows}) != len(rows):
            raise ValueError('Empty corpus or duplicate document IDs')
        versions = {r['metadata']['storage_key'] for r in rows}
        if len(versions) != 1 or any(
            r['metadata'].get('cohort') != cohort
            or r['metadata'].get('document_hash') != source['sha256']
            or r['metadata'].get('kind') != 'policy'
            or r['metadata'].get('structure') != 'article' for r in rows
        ):
            raise ValueError('Mixed cohort, version or document type in corpus')
        corpora[cohort] = {'B': rows}
        corpus_hashes[cohort] = sha(path)
    validate_cases(cases, corpora)
    model, dimensions = manifest['embedding_model'], manifest['embedding_dimensions']
    if isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions <= 0:
        raise ValueError('Invalid embedding dimensions in manifest')
    cache = json.loads((baseline_run / 'embedding-cache.json').read_text(encoding='utf-8'))
    texts = {c['question'] for c in cases}
    texts.update(r['page_content'] for variants in corpora.values() for r in variants['B'])
    embeddings = {}
    for text in texts:
        vector = cache.get(digest(model + '\0' + str(dimensions) + '\0' + text))
        if (not isinstance(vector, list) or len(vector) != dimensions
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector)):
            raise ValueError('Missing or invalid cached embedding; request approval before any new API run')
        embeddings[text] = vector
    return cases, corpora, embeddings, manifest, corpus_hashes


def rank_case(case, rows, embeddings, k=4, candidates=12, rank_constant=60):
    if k <= 0 or candidates < k or rank_constant <= 0:
        raise ValueError('Require candidates >= k > 0 and rank_constant > 0')
    if any(row['metadata'].get('cohort') != case['cohort'] for row in rows):
        raise ValueError('Both retrieval paths must use the authenticated cohort corpus')
    started = time.perf_counter()
    vector = sorted(
        [(cosine(embeddings[case['question']], embeddings[r['page_content']]), r) for r in rows],
        key=lambda item: (-item[0], item[1]['id']),
    )[:candidates]
    vector_seconds = time.perf_counter() - started
    started = time.perf_counter()
    lexical = bm25_rank(case['question'], rows, limit=candidates)
    lexical_seconds = time.perf_counter() - started
    started = time.perf_counter()
    hybrid = rrf_rank([vector, lexical], limit=k, rank_constant=rank_constant)
    fusion_seconds = time.perf_counter() - started
    ranks = {'vector': {r['id']: i for i, (_, r) in enumerate(vector, 1)},
             'bm25': {r['id']: i for i, (_, r) in enumerate(lexical, 1)}}
    results = []
    for label, ranked in [('vector', vector[:k]), ('hybrid', hybrid)]:
        selected = [{**deepcopy(row), 'score': score,
                     'vector_rank': ranks['vector'].get(row['id']),
                     'bm25_rank': ranks['bm25'].get(row['id'])} for score, row in ranked]
        results.append({'case_id': case['id'], 'variant': label, 'cohort': case['cohort'],
            'question': case['question'], 'expected_behavior': case['expected_behavior'],
            'retrieved': selected, 'metrics': score_evidence(case, selected),
            'context_chars': sum(len(r['page_content']) for r in selected),
            'seconds_local_only': vector_seconds + (lexical_seconds + fusion_seconds if label == 'hybrid' else 0),
            'answer': None})
    return results


def run(args):
    if args.k <= 0 or args.candidates < args.k or args.rrf_constant <= 0:
        raise ValueError('Require candidates >= k > 0 and rrf_constant > 0')
    output = Path(args.output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a new empty output directory; previous results are preserved')
    cases, corpora, embeddings, baseline, hashes = load_inputs(args.baseline_run, args.cases)
    output.mkdir(parents=True, exist_ok=True)
    module_root = Path(__file__).resolve().parent
    manifest = {'created_at': datetime.now(timezone.utc).isoformat(),
        'mode': 'cached_embedding_bm25_rrf', 'status': 'pending_review', 'completed': False,
        'case_count': len(cases), 'comparison_count': len(cases) * 2,
        'k': args.k, 'candidates_per_retriever': args.candidates, 'rrf_constant': args.rrf_constant,
        'embedding_model': baseline['embedding_model'], 'embedding_dimensions': baseline['embedding_dimensions'],
        'source_manifest_sha256': sha(Path(args.baseline_run) / 'manifest.json'),
        'cases_sha256': sha(args.cases), 'corpus_sha256': hashes,
        'cache_sha256': sha(Path(args.baseline_run) / 'embedding-cache.json'),
        'implementation_sha256': {p.name: sha(p) for p in [Path(__file__), module_root/'policy_hybrid.py', module_root/'evaluate_policy_rag.py']},
        'external_calls': 0, 'automatic_retries': 0, 'supervisor_executed': False,
        'reference_expansion_executed': False, 'answer_generation_executed': False,
        'limitations': ['Retrieval component comparison only, not an end-to-end chatbot benchmark.',
                       'No production Pinecone, database, or deployment changes.',
                       'A small reused question set is not a held-out quality gate.']}
    write_json(output/'manifest.json', manifest)
    results = []
    for case in cases:
        results.extend(rank_case(case, corpora[case['cohort']]['B'], embeddings,
                                 args.k, args.candidates, args.rrf_constant))
    summary = {'not_a_quality_gate': True, 'variants': {}}
    for label in ('vector', 'hybrid'):
        selected = [r for r in results if r['variant'] == label]
        metrics = {}
        for metric in ('article_recall', 'evidence_recall', 'all_required_articles', 'all_evidence'):
            values = [r['metrics'][metric] for r in selected if r['metrics'][metric] is not None]
            metrics[metric] = {'mean': sum(values)/len(values) if values else None, 'eligible_cases': len(values)}
        metrics['cross_cohort_count'] = sum(r['metrics']['cross_cohort_count'] for r in selected)
        metrics['mean_context_chars'] = sum(r['context_chars'] for r in selected)/len(selected)
        summary['variants'][label] = metrics
    summary['paired_comparison'] = paired_comparison(results, 'vector', 'hybrid')
    write_json(output/'results.json', results)
    write_json(output/'summary.json', summary)
    manifest['completed'] = True
    write_json(output/'manifest.json', manifest)
    return manifest


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--baseline-run', required=True)
    result.add_argument('--cases', required=True)
    result.add_argument('--output', required=True)
    result.add_argument('--k', type=int, default=4)
    result.add_argument('--candidates', type=int, default=12)
    result.add_argument('--rrf-constant', type=int, default=60)
    return result


if __name__ == '__main__':
    options = parser().parse_args()
    report = run(options)
    print(json.dumps({'status': report['status'], 'case_count': report['case_count'], 'external_calls': 0}))
