"""Lossless answer-context variants and local-only text size measurements.

The builder and meter do not mutate input state, access DBs or call APIs.
Token estimates exclude provider message framing and are not provider usage.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from types import FunctionType
from typing import Any, Callable, Iterable


CATEGORIES = ('system', 'history', 'question', 'shared', 'student', 'policy', 'notice', 'project', 'other')
_SHARED_LABEL = '[서버 계산 학생 단위기간 컨텍스트]\n'
_STUDENT_LABEL = '[인증된 로그인 학생 Firebase 데이터]\n'
_DOCUMENT_LABEL = '[검색 문서]\n'
_REFERENCE_NOTE = ('[공유 값 참조]\n$context_ref는 이 항목의 값이 지정된 원래 경로의 값과 완전히 같다는 뜻이다. '
                   'unit_period_context는 서버 계산 학생 단위기간 컨텍스트를 가리킨다.')


@dataclass(frozen=True)
class ContextBuild:
    legacy_text: str
    compact_text: str
    mode: str
    references: tuple[tuple[str, str], ...]
    legacy_parts: tuple[tuple[str, str], ...]
    compact_parts: tuple[tuple[str, str], ...]
    document_parts: tuple[tuple[str, str, str, str], ...]

    @property
    def text(self) -> str:
        return self.legacy_text if self.mode == 'legacy' else self.compact_text


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _identities(context: dict) -> tuple[set[str], set[str]]:
    cohorts, versions = set(), set()
    roots = [context.get('calendar_basis'), context.get('policy_calculation'), context.get('calculation_rules')]
    policy = context.get('policy_calculation')
    if isinstance(policy, dict):
        roots.append(policy.get('calendar_basis'))
        criteria = policy.get('criteria')
        if isinstance(criteria, dict):
            roots.extend(criteria.values())
    roots.append(context)
    for root in roots:
        if not isinstance(root, dict):
            continue
        if root.get('cohort') is not None:
            cohorts.add(str(root['cohort']))
        for key in ('document_hash', 'version', 'policy_version', 'snapshot_hash'):
            if root.get(key) is not None:
                versions.add(str(root[key]))
    return cohorts, versions


def _compatible(shared: dict, personal: dict, cohort: str, student_cohort: Any) -> bool:
    shared_cohorts, shared_versions = _identities(shared)
    personal_cohorts, personal_versions = _identities(personal)
    known_cohorts = shared_cohorts | personal_cohorts
    if student_cohort is not None:
        known_cohorts.add(str(student_cohort))
    if cohort:
        known_cohorts.add(cohort)
    if len(known_cohorts) > 1:
        return False
    if shared_versions and personal_versions and shared_versions != personal_versions:
        return False
    # Compare provenance/state at the same paths before removing *any* subtree.
    def conflict(left, right):
        if not isinstance(left, dict) or not isinstance(right, dict):
            return False
        for key in left.keys() & right.keys():
            if key in ('storage_key', 'document_hash', 'version', 'policy_version',
                       'snapshot_hash', 'cohort', 'approval_status', 'review_status'):
                if _json(left[key]) != _json(right[key]):
                    return True
            if conflict(left[key], right[key]):
                return True
        return False
    return not conflict(shared, personal)


def _reference_equal_subtrees(shared: dict, personal: dict, source_path: str,
                              target_path: str, references: list) -> None:
    for key in shared:
        if key not in personal:
            continue
        # Paths are fixed schema identifiers, never keys from records/lists.
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
            continue
        left, right = shared[key], personal[key]
        destination, origin = f'{source_path}.{key}', f'{target_path}.{key}'
        if (isinstance(left, (dict, list)) and left
                and type(left) is type(right)
                and json.dumps(left, ensure_ascii=False, sort_keys=True)
                    == json.dumps(right, ensure_ascii=False, sort_keys=True)):
            marker = {'$context_ref': destination}
            if len(_json(marker)) < len(_json(right)):
                personal[key] = marker
                references.append((origin, destination))
        elif isinstance(left, dict) and isinstance(right, dict):
            _reference_equal_subtrees(left, right, destination, origin, references)


def build_answer_context(*, unit_period_context: dict, student_context: dict,
                         documents: Iterable[Any] = (), mode: str = 'compact',
                         cohort: str = '') -> ContextBuild:
    """Keep exact legacy serialization; compact only equal scoped subtrees.

    References remain at their original JSON paths, pointing to the unchanged
    unit_period_context tree. Scalar values, records and document metadata are
    never dropped or summarized. Input dictionaries/documents remain intact.
    """
    if mode not in ('legacy', 'compact'):
        raise ValueError('Context mode must be legacy or compact')
    document_parts = []
    search_parts = []
    for number, document in enumerate(documents, 1):
        namespace = document.metadata['_namespace']
        metadata = str(document.metadata)
        header = f'[{number}] namespace={namespace} metadata={metadata}\n'
        body = document.page_content
        category = {'policy': 'policy', 'notice': 'notice', 'project_reference': 'project'}.get(namespace, 'other')
        document_parts.append((category, header, body, metadata))
        search_parts.append(header + body)
    search_context = '\n\n'.join(search_parts)

    def parts(student, note=''):
        result = []
        if unit_period_context:
            result.append(('shared', _SHARED_LABEL + _json(unit_period_context)))
        if student:
            result.append(('student', _STUDENT_LABEL + _json(student)))
        if note:
            result.append(('other', note))
        if search_context:
            result.append(('documents', _DOCUMENT_LABEL + search_context))
        return tuple(result)

    legacy_parts = parts(student_context)
    legacy = '\n\n'.join(text for _, text in legacy_parts)
    compact_student = deepcopy(student_context)
    references: list[tuple[str, str]] = []
    data = compact_student.get('data', {})
    if isinstance(data, dict) and unit_period_context:
        for scope in ('student_attendance', 'student_private'):
            scoped = data.get(scope)
            personal = scoped.get('unit_period_context') if isinstance(scoped, dict) else None
            if (isinstance(personal, dict) and _compatible(unit_period_context, personal, cohort,
                                                          compact_student.get('cohort'))):
                _reference_equal_subtrees(unit_period_context, personal, 'unit_period_context',
                    f'student_context.data.{scope}.unit_period_context', references)
    compact_parts = parts(compact_student, _REFERENCE_NOTE if references else '')
    compact = '\n\n'.join(text for _, text in compact_parts)
    # Do not add reference overhead when it fails to reduce serialized size.
    if len(compact) >= len(legacy):
        compact, compact_parts, references = legacy, legacy_parts, []
    return ContextBuild(legacy, compact, mode, tuple(references), legacy_parts,
                        compact_parts, tuple(document_parts))


@dataclass(frozen=True)
class LocalTokenizer:
    counter: Callable[[str], int] | None = None
    status: str = 'unavailable'
    reason: str = 'not_requested'
    encoding: str = 'o200k_base'


@lru_cache(maxsize=1)
def get_local_tokenizer() -> LocalTokenizer:
    """Use installed tiktoken definitions and existing cache only, never fetch.

    A private copy of the constructor globals replaces its loader with a
    file-only reader. No tiktoken registry/global/environment is modified.
    Missing/corrupt cache stays unavailable until the process is restarted.
    """
    try:
        from tiktoken import Encoding
        from tiktoken_ext.openai_public import cl100k_base, o200k_base
    except ImportError:
        return LocalTokenizer(reason='not_installed')
    cache_dir = os.getenv('TIKTOKEN_CACHE_DIR', os.getenv('DATA_GYM_CACHE_DIR',
                           str(Path(tempfile.gettempdir()) / 'data-gym-cache')))
    if not cache_dir:
        return LocalTokenizer(reason='cache_missing')

    def local_ranks(url, expected_hash=None):
        path = Path(cache_dir) / hashlib.sha1(url.encode()).hexdigest()
        data = path.read_bytes()
        if expected_hash is None or hashlib.sha256(data).hexdigest() != expected_hash:
            raise ValueError('Invalid local tokenizer cache')
        return {base64.b64decode(token, validate=True): int(rank)
                for token, rank in (line.split() for line in data.splitlines() if line)}
    failures = []
    for name, definition in (('o200k_base', o200k_base), ('cl100k_base', cl100k_base)):
        try:
            globals_copy = {**definition.__globals__, 'load_tiktoken_bpe': local_ranks}
            constructor = FunctionType(definition.__code__, globals_copy)
            encoding = Encoding(**constructor())
            return LocalTokenizer(lambda text, enc=encoding: len(enc.encode(text, disallowed_special=())),
                                  'available', 'none', name)
        except FileNotFoundError:
            failures.append('cache_missing')
        except ValueError:
            failures.append('cache_invalid')
        except Exception:
            failures.append('load_failed')
    reason = next((reason for reason in ('load_failed', 'cache_invalid') if reason in failures), 'cache_missing')
    return LocalTokenizer(reason=reason)


def measure_answer_context(build: ContextBuild, *, system: str, history: Iterable[Any],
                           question: str, tokenizer: LocalTokenizer | None = None) -> dict:
    """Measure both variants without logging text, paths, document IDs or UID.

    Estimates sum message text tokenizations and exclude role/framing tokens.
    Per-category estimates are attribution aids, not additive provider billing.
    The request-local memo exists only during this call; no text is cached
    across requests. Document bodies and original metadata are measured apart.
    """
    tokenizer = tokenizer or LocalTokenizer()
    history_texts = [str(message.content) for message in history]
    cache: dict[str, int] = {}
    encoding_failed = False

    def size(text):
        nonlocal encoding_failed
        result = {'chars': len(text)}
        if tokenizer.counter is not None and not encoding_failed:
            try:
                if text not in cache:
                    cache[text] = tokenizer.counter(text)
                result['token_estimate'] = cache[text]
            except Exception:
                encoding_failed = True
        return result

    def variant(parts, context_text):
        category_texts = {category: [] for category in CATEGORIES}
        evidence = []
        category_counts = {category: 0 for category in CATEGORIES}

        def add(category, text, *, body=None, metadata=None, identity_key=None):
            ordinal = category_counts[category]
            category_counts[category] += 1
            identity = hashlib.sha256(f'{category}:{identity_key or ordinal}'.encode()).hexdigest()[:24]
            row = {'id': identity, 'category': category, **size(text)}
            if body is not None:
                row.update({f'body_{key}': value for key, value in size(body).items()})
            if metadata is not None:
                row.update({f'metadata_{key}': value for key, value in size(metadata).items()})
            evidence.append(row)
            category_texts[category].append(text)

        add('system', system)
        for text in history_texts:
            add('history', text)
        add('question', question)
        for category, text in parts:
            if category != 'documents':
                add(category, text)
        for index, (category, header, body, metadata) in enumerate(build.document_parts):
            add(category, header + body, body=body, metadata=metadata, identity_key=f'document:{index}')
        # Include exact context/template separators as overhead, not evidence.
        overhead = '검색 문맥:\n' + '\n\n학생 질문: '
        overhead += '\n\n' * max(0, len(parts) - 1)
        if build.document_parts:
            overhead += _DOCUMENT_LABEL + '\n\n' * (len(build.document_parts) - 1)
        category_texts['other'].append(overhead)
        categories = [{'category': category,
            'chars': sum(len(text) for text in texts),
            **({'token_estimate': sum(size(text).get('token_estimate', 0) for text in texts)}
               if tokenizer.counter is not None and not encoding_failed else {}),
        } for category, texts in category_texts.items()]
        message_texts = [system, *history_texts, f'검색 문맥:\n{context_text}\n\n학생 질문: {question}']
        total = {'chars': sum(len(text) for text in message_texts),
                 'categories': categories, 'evidence': evidence}
        if tokenizer.counter is not None and not encoding_failed:
            estimates = [size(text) for text in message_texts]
            if not encoding_failed:
                total['token_estimate'] = sum(item['token_estimate'] for item in estimates)
        return total

    legacy = variant(build.legacy_parts, build.legacy_text)
    compact = legacy if build.compact_text == build.legacy_text else variant(build.compact_parts, build.compact_text)
    report = {'mode': build.mode, 'tokenizer_status': 'unavailable' if encoding_failed else tokenizer.status,
              'tokenizer_reason': 'encode_failed' if encoding_failed else tokenizer.reason,
              'encoding': tokenizer.encoding, 'measurement': 'local_text_only_estimate',
              'legacy': legacy, 'compact': compact,
              'saved_chars': legacy['chars'] - compact['chars'],
              'reference_count': len(build.references)}
    if encoding_failed:
        def remove_estimates(value):
            if isinstance(value, dict):
                for key in list(value):
                    if key.endswith('token_estimate'):
                        del value[key]
                    else:
                        remove_estimates(value[key])
            elif isinstance(value, list):
                for item in value:
                    remove_estimates(item)
        remove_estimates(report)
    elif 'token_estimate' in legacy and 'token_estimate' in compact:
        report['saved_token_estimate'] = legacy['token_estimate'] - compact['token_estimate']
    return report


def safe_context_metrics(value: Any) -> dict:
    """Rebuild an explicit telemetry allowlist; never accept arbitrary strings."""
    if not isinstance(value, dict) or not value:
        return {}
    clean = {}
    for key, allowed in {
        'mode': {'legacy', 'compact'}, 'tokenizer_status': {'available', 'unavailable'},
        'tokenizer_reason': {'none', 'not_requested', 'not_installed', 'cache_missing',
                             'cache_invalid', 'load_failed', 'encode_failed'},
        'encoding': {'o200k_base', 'cl100k_base'}, 'measurement': {'local_text_only_estimate'},
    }.items():
        if isinstance(value.get(key), str) and value[key] in allowed:
            clean[key] = value[key]
    for key in ('saved_chars', 'saved_token_estimate', 'reference_count'):
        if type(value.get(key)) is int:
            clean[key] = value[key]

    def numbers(source):
        if not isinstance(source, dict):
            return {}
        return {key: source[key] for key in ('chars', 'token_estimate', 'body_chars',
            'body_token_estimate', 'metadata_chars', 'metadata_token_estimate')
            if type(source.get(key)) is int and source[key] >= 0}
    for name in ('legacy', 'compact'):
        source = value.get(name)
        if not isinstance(source, dict):
            continue
        target = numbers(source)
        categories = source.get('categories')
        if isinstance(categories, list):
            target['categories'] = [{**numbers(row), 'category': row['category']}
                for row in categories if isinstance(row, dict) and row.get('category') in CATEGORIES]
        rows = source.get('evidence')
        if isinstance(rows, list):
            target['evidence'] = [{**numbers(row), 'id': row['id'], 'category': row['category']}
                for row in rows if isinstance(row, dict) and row.get('category') in CATEGORIES
                and isinstance(row.get('id'), str) and re.fullmatch(r'[a-f0-9]{24}', row['id'])]
        clean[name] = target
    return clean
