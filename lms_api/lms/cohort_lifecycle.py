"""Admin-only cohort retirement and recoverable deletion of cohort-owned documents."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import boto3
from django.db import ProgrammingError, connection, transaction
from ninja import Router
from ninja.responses import Response
from pydantic import BaseModel

_repo_root = str(Path(__file__).resolve().parents[2])
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
from chatbot.cohort_document_rag import document_namespace, indexed_key
from lms.models import Cohorts, CohortDeletionJobs, CurriculumPdfs, PolicyDocuments
from lms.storage import _s3_target, local_path

router = Router()
_BLOCKER_NAMES = {
    'users': '연결 사용자', 'attendances': '출결', 'seat_presences': '자리 출결',
    'curriculum_sheets': '교육과정 시트', 'notices': '공지', 'scheduled_notices': '예약 공지',
    'assignments': '과제', 'submission_task_cohorts': '제출 과제',
    'student_counsel_notes': '상담', 'resumes': '이력서', 'cohort_seating': '좌석 배치',
}


class DeleteCohortInput(BaseModel):
    confirmName: str


class DeletionInspectionError(RuntimeError):
    """The database cannot prove that the cohort is safe to delete."""


def _missing_deletion_jobs(exc: ProgrammingError) -> bool:
    return (getattr(exc.__cause__, 'sqlstate', None) == '42P01'
            and 'cohort_deletion_jobs' in str(exc).lower())


def _admin(request):
    user = request.auth
    return bool(user and user.get('is_active') and user.get('role') == 'admin')


def _blockers(cohort_id: int) -> list[dict]:
    """Inspect actual PostgreSQL FKs, using the same catalog scope as migration 0017."""
    with connection.cursor() as cur:
        cur.execute('''SELECT child_ns.nspname, child.relname, att.attname,
                              array_length(fk.conkey, 1), parent_ns.nspname
            FROM pg_constraint fk
            JOIN pg_class child ON child.oid = fk.conrelid
            JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace
            JOIN pg_class parent ON parent.oid = fk.confrelid
            JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace
            LEFT JOIN pg_attribute att ON att.attrelid = child.oid AND att.attnum = fk.conkey[1]
            WHERE fk.contype = 'f' AND fk.confrelid = 'cohorts'::regclass
            ORDER BY child_ns.nspname, child.relname, fk.conname''')
        relationships = cur.fetchall()
        probes = []
        labels = {}
        quote = connection.ops.quote_name
        for schema, table, column, arity, parent_schema in relationships:
            if arity != 1 or not column:
                raise DeletionInspectionError(f'지원하지 않는 기수 FK 관계: {schema}.{table}')
            if schema == parent_schema and table == 'curriculum_pdfs':
                continue  # Explicitly owned document pointer, removed in final DB transaction.
            qualified_table = f'{quote(schema)}.{quote(table)}'
            identity = table if schema == parent_schema else f'{schema}.{table}'
            labels[identity] = _BLOCKER_NAMES.get(table, table) if schema == parent_schema else identity
            probes.append((identity, qualified_table, quote(column)))
        if not probes:
            return []
        # One PostgreSQL round trip for every real FK table; each EXISTS stops
        # at its first matching row. Identifiers come only from pg_catalog.
        sql = ' UNION ALL '.join(
            f'SELECT %s WHERE EXISTS(SELECT 1 FROM {table} WHERE {column}=%s)'
            for _, table, column in probes)
        params = [item for identity, _, _ in probes for item in (identity, cohort_id)]
        cur.execute(sql, params)
        present = {row[0] for row in cur.fetchall()}
    return [{'table': identity, 'label': labels[identity]} for identity in sorted(present)]


def _document_pointers(cohort: Cohorts) -> tuple[list[dict], list[str]]:
    documents, unsafe = [], []
    curriculum = CurriculumPdfs.objects.filter(cohort_id=cohort.id).first()
    policy = PolicyDocuments.objects.filter(source_key=f'cohort:{cohort.id}:policy',
                                             source_type='cohort_policy').first()
    for kind, row, name, key in (
        ('curriculum', curriculum, getattr(curriculum, 'original_filename', ''), getattr(curriculum, 'storage_key', '')),
        ('policy', policy, getattr(policy, 'source_name', ''), getattr(policy, 'storage_key', '')),
    ):
        if row is None:
            continue
        documents.append({'kind': kind, 'filename': name or '파일명 없음'})
        if key and not _owned_key(cohort.code, kind, key):
            unsafe.append(kind)
        if kind == 'policy' and not key:
            unsafe.append(kind)
    return documents, sorted(set(unsafe))


def _owned_key(code: str, kind: str, key: str) -> bool:
    return indexed_key(key) and key.startswith(f'cohorts/{code}/{kind}/rag/')


def _list_owned_keys(code: str) -> list[str]:
    """Enumerate only this cohort's document subtree, including replaced/failed uploads."""
    prefix = f'cohorts/{code}/'
    target = _s3_target()
    if target:
        bucket, region = target
        client = boto3.client('s3', region_name=region)
        keys = [item['Key'] for page in client.get_paginator('list_objects_v2').paginate(
            Bucket=bucket, Prefix=prefix) for item in page.get('Contents', [])]
    else:
        root = local_path(prefix)
        if root is None:
            raise ValueError('invalid_document_prefix')
        keys = [prefix + str(path.relative_to(root)).replace('\\', '/') for path in root.rglob('*') if path.is_file()] if root.exists() else []
    if len(keys) > 10000:
        raise ValueError('too_many_cohort_documents')
    for key in keys:
        kind = key[len(prefix):].split('/', 1)[0]
        if kind not in ('curriculum', 'policy') or not _owned_key(code, kind, key):
            raise ValueError('unrecognized_cohort_object')
    return sorted(set(keys))


def _delete_vector_namespace(namespace: str) -> None:
    if not namespace.startswith('cohort-doc-'):
        raise ValueError('invalid_document_namespace')
    from pinecone import Pinecone
    key = os.getenv('PINECONE_API_KEY2') or os.getenv('PINECONE_API_KEY')
    if not key:
        raise RuntimeError('pinecone_not_configured')
    index = Pinecone(api_key=key).Index(os.getenv('PINECONE_STUDENT_INDEX_NAME', 'student'))
    index.delete(delete_all=True, namespace=namespace)


def _delete_stored_object(key: str) -> None:
    target = _s3_target()
    if target:
        bucket, region = target
        boto3.client('s3', region_name=region).delete_object(Bucket=bucket, Key=key)
    else:
        path = local_path(key)
        if path is None:
            raise ValueError('invalid_document_key')
        path.unlink(missing_ok=True)


def _preview(cohort: Cohorts) -> dict:
    documents, unsafe = _document_pointers(cohort)
    blockers = _blockers(cohort.id)
    job = CohortDeletionJobs.objects.filter(cohort_id=cohort.id).first()
    return {'cohortId': cohort.code, 'name': cohort.name, 'documents': documents,
            'blockers': blockers, 'unsafeDocuments': unsafe,
            'canDelete': not blockers and not unsafe,
            'state': job.state if job else 'not_started', 'error': job.error if job else ''}


@router.get('/{cohort_code}/deletion-preview')
def deletion_preview(request, cohort_code: str):
    if not _admin(request):
        return Response({'detail': '관리자만 기수를 삭제할 수 있습니다.'}, status=403)
    cohort = Cohorts.objects.filter(code=cohort_code).first()
    if not cohort:
        return Response({'detail': '기수를 찾지 못했습니다.'}, status=404)
    try:
        return _preview(cohort)
    except ProgrammingError as exc:
        if _missing_deletion_jobs(exc):
            return Response({'detail': '기수 삭제 보호 migration 0017 적용 후 다시 시도해 주세요.'}, status=503)
        return Response({'detail': '기수 삭제 안전성 DB 검사에 실패했습니다. 삭제는 진행되지 않았습니다.'}, status=503)
    except DeletionInspectionError as exc:
        return Response({'detail': str(exc)}, status=503)


def _prepare_job(cohort_code: str, confirm_name: str):
    with transaction.atomic():
        cohort = Cohorts.objects.select_for_update().filter(code=cohort_code).first()
        if not cohort:
            raise LookupError('cohort_not_found')
        if confirm_name != cohort.name:
            raise ValueError('confirmation_name_mismatch')
        preview = _preview(cohort)
        if not preview['canDelete']:
            raise ValueError('cohort_has_operational_records_or_unowned_documents')
        job, _ = CohortDeletionJobs.objects.select_for_update().get_or_create(
            cohort_id=cohort.id,
            defaults={'cohort_code': cohort.code, 'cohort_name': cohort.name, 'state': 'preparing'},
        )
        if job.state == 'complete':
            raise ValueError('cohort_already_deleted')
        return cohort.id


def _cleanup_targets(job: CohortDeletionJobs) -> None:
    """Persist each completed external step so a retry resumes without broad deletes."""
    for target in job.targets or []:
        key, namespace = target['key'], target['namespace']
        kind = key.split('/')[2] if len(key.split('/')) > 2 else ''
        if not _owned_key(job.cohort_code, kind, key) or namespace != document_namespace(key):
            raise ValueError('invalid_cleanup_manifest')
        if namespace not in job.deleted_vectors:
            _delete_vector_namespace(namespace)
            job.deleted_vectors = [*job.deleted_vectors, namespace]
            job.save(update_fields=['deleted_vectors', 'updated_at'])
        if key not in job.deleted_objects:
            _delete_stored_object(key)
            job.deleted_objects = [*job.deleted_objects, key]
            job.save(update_fields=['deleted_objects', 'updated_at'])


def _delete_database_rows(cohort_id: int, target_keys: set[str]) -> None:
    """Delete exact owned rows without Django's stale reverse-relation Collector.

    The caller holds the cohort row lock and a DB transaction. Actual database
    FKs still reject any unexpected dependent row and roll back all SQL deletes.
    """
    source_key = f'cohort:{cohort_id}:policy'
    with connection.cursor() as cur:
        cur.execute('''SELECT id, storage_key FROM policy_documents
            WHERE source_key=%s AND source_type='cohort_policy' FOR UPDATE''', [source_key])
        policy = cur.fetchone()
        cur.execute('SELECT storage_key FROM curriculum_pdfs WHERE cohort_id=%s FOR UPDATE', [cohort_id])
        curriculum = cur.fetchone()
        current_keys = [key for key in (policy[1] if policy else None,
                                         curriculum[0] if curriculum else None) if key]
        if any(key not in target_keys for key in current_keys):
            raise DeletionInspectionError('삭제 준비 후 기수 문서 연결이 변경됐습니다. 외부 문서는 더 삭제하지 않습니다.')
        if policy:
            cur.execute('DELETE FROM policy_document_revisions WHERE document_id=%s', [policy[0]])
            cur.execute('''DELETE FROM policy_documents
                WHERE id=%s AND source_key=%s AND source_type='cohort_policy' ''', [policy[0], source_key])
            if cur.rowcount != 1:
                raise DeletionInspectionError('기수 정책 문서가 삭제 준비 후 변경됐습니다.')
        cur.execute('DELETE FROM curriculum_pdfs WHERE cohort_id=%s', [cohort_id])
        cur.execute('DELETE FROM cohorts WHERE id=%s', [cohort_id])
        if cur.rowcount != 1:
            raise DeletionInspectionError('삭제할 기수 행이 변경됐습니다.')


def _run_deletion(cohort_id: int):
    with connection.cursor() as cur:
        cur.execute('SELECT pg_try_advisory_lock(%s)', [cohort_id])
        if not cur.fetchone()[0]:
            raise ValueError('cohort_deletion_in_progress')
    try:
        job = CohortDeletionJobs.objects.get(cohort_id=cohort_id)
        if job.targets is None:
            cohort = Cohorts.objects.get(id=cohort_id)
            _documents, unsafe = _document_pointers(cohort)
            if unsafe:
                raise ValueError('unowned_document_pointer')
            keys = set(_list_owned_keys(cohort.code))
            curriculum = CurriculumPdfs.objects.filter(cohort_id=cohort.id).first()
            policy = PolicyDocuments.objects.filter(source_key=f'cohort:{cohort.id}:policy',
                                                     source_type='cohort_policy').first()
            keys.update(key for key in (getattr(curriculum, 'storage_key', None),
                                        getattr(policy, 'storage_key', None)) if key)
            for key in keys:
                kind = key.split('/')[2]
                if not _owned_key(cohort.code, kind, key):
                    raise ValueError('unowned_document_pointer')
            job.targets = [{'key': key, 'namespace': document_namespace(key)} for key in sorted(keys)]
            job.state = 'deleting'
            job.error = ''
            job.save(update_fields=['targets', 'state', 'error', 'updated_at'])
        elif job.state != 'deleting':
            job.state = 'deleting'
            job.error = ''
            job.save(update_fields=['state', 'error', 'updated_at'])
        _cleanup_targets(job)
        with transaction.atomic():
            Cohorts.objects.select_for_update().get(id=cohort_id)
            if _blockers(cohort_id):
                raise ValueError('cohort_received_operational_records_during_deletion')
            _delete_database_rows(cohort_id, {target['key'] for target in job.targets})
            job.state = 'complete'
            job.error = ''
            job.save(update_fields=['state', 'error', 'updated_at'])
    except Exception as exc:
        job = CohortDeletionJobs.objects.filter(cohort_id=cohort_id).first()
        if job:
            job.state = 'failed'
            job.error = type(exc).__name__
            job.save(update_fields=['state', 'error', 'updated_at'])
        raise
    finally:
        with connection.cursor() as cur:
            cur.execute('SELECT pg_advisory_unlock(%s)', [cohort_id])


@router.delete('/{cohort_code}')
def delete_cohort(request, cohort_code: str, body: DeleteCohortInput):
    if not _admin(request):
        return Response({'detail': '관리자만 기수를 삭제할 수 있습니다.'}, status=403)
    try:
        cohort_id = _prepare_job(cohort_code, body.confirmName)
        _run_deletion(cohort_id)
    except LookupError:
        completed = CohortDeletionJobs.objects.filter(cohort_code=cohort_code, state='complete',
                                                       cohort_name=body.confirmName).exists()
        return {'state': 'complete'} if completed else Response({'detail': '기수를 찾지 못했습니다.'}, status=404)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=409)
    except ProgrammingError as exc:
        if _missing_deletion_jobs(exc):
            return Response({'detail': '기수 삭제 보호 migration 0017 적용 후 다시 시도해 주세요.'}, status=503)
        return Response({'detail': '기수 삭제 DB 검증에 실패했습니다.'}, status=502)
    except DeletionInspectionError as exc:
        return Response({'detail': str(exc)}, status=503)
    except Exception:
        return Response({'detail': '외부 문서 정리가 완료되지 않았습니다. 같은 기수에서 다시 시도해 주세요.'}, status=502)
    return {'state': 'complete'}
