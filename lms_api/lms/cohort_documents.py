"""Admin cohort attachments; activate only fully indexed document versions."""
import logging
import sys
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile, BadZipFile

from django.db import ProgrammingError, connection, transaction
from ninja import Router, File, Form, UploadedFile
from ninja.responses import Response
from lms.storage import put_object

router = Router()
# Local manage.py starts in lms_api; production image includes these shared modules.
_repo_root = str(Path(__file__).resolve().parents[2])
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
from chatbot.cohort_document_rag import MAX_BYTES, document_records, index_document, indexed_key


def _document_status(cohort_code, kind, storage_key, active):
    if not active:
        return 'inactive'
    if (storage_key and indexed_key(storage_key)
            and storage_key.startswith(f'cohorts/{cohort_code}/{kind}/rag/')):
        # The upload path publishes this pointer only after search visibility is verified.
        return 'ready'
    return 'registered'


@router.get('/documents')
def get_documents(request, cohortId: str):
    user = request.auth
    if not user or not user.get('is_active') or user.get('role') != 'admin':
        return Response({'detail': '관리자만 문서를 확인할 수 있습니다.'}, status=403)
    with connection.cursor() as cur:
        cur.execute('SELECT id, code FROM cohorts WHERE code=%s', [cohortId])
        cohort = cur.fetchone()
        if not cohort:
            return Response({'detail': '기수를 찾지 못했습니다.'}, status=404)
        cur.execute('''SELECT original_filename, storage_key, published, updated_at
            FROM curriculum_pdfs WHERE cohort_id=%s''', [cohort[0]])
        curriculum = cur.fetchone()
        cur.execute('''SELECT source_name, storage_key, is_active, updated_at
            FROM policy_documents WHERE source_key=%s AND source_type='cohort_policy' ''',
            [f'cohort:{cohort[0]}:policy'])
        policy = cur.fetchone()

    def document(kind, row):
        if not row:
            return None
        name, key, active, updated_at = row
        return {'kind': kind, 'filename': name or '',
                'updatedAt': updated_at.isoformat() if updated_at else None,
                'ragStatus': _document_status(cohort[1], kind, key, active)}

    return {'cohortId': cohort[1], 'documents': {
        'curriculum': document('curriculum', curriculum),
        'policy': document('policy', policy),
    }}


def validate_document(kind, name, data):
    suffix = Path(name).suffix.lower()
    if kind not in ('curriculum', 'policy'):
        raise ValueError('문서 종류가 올바르지 않습니다.')
    if not data or len(data) > MAX_BYTES:
        raise ValueError('파일은 비어 있지 않은 10MB 이하 문서여야 합니다.')
    if suffix == '.pdf' and data.startswith(b'%PDF-'):
        return suffix, 'application/pdf'
    if kind == 'policy' and suffix == '.docx':
        try:
            with ZipFile(BytesIO(data)) as doc:
                if {'[Content_Types].xml', 'word/document.xml'} <= set(doc.namelist()):
                    return suffix, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        except BadZipFile:
            pass
    raise ValueError('커리큘럼은 PDF, 정책은 PDF 또는 DOCX 파일을 선택해 주세요.')


@router.post('/documents')
def upload_document(request, cohortId: str = Form(...), kind: str = Form(...), file: UploadedFile = File(...)):
    user = request.auth
    if not user or not user.get('is_active') or user.get('role') != 'admin':
        return Response({'detail': '관리자만 문서를 등록할 수 있습니다.'}, status=403)
    try:
        data = file.read(MAX_BYTES + 1)
        suffix, content_type = validate_document(kind, file.name, data)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    with connection.cursor() as cur:
        cur.execute('SELECT id, code FROM cohorts WHERE code=%s', [cohortId])
        cohort = cur.fetchone()
    if not cohort:
        return Response({'detail': '기수를 먼저 저장해 주세요.'}, status=404)
    # DB code, never a client-supplied storage key. Do not overwrite older files.
    key = f'cohorts/{cohort[1]}/{kind}/rag/{uuid4().hex}{suffix}'
    name = file.name.replace('\\', '/').rsplit('/', 1)[-1]
    try:
        records = document_records(data, name, cohort[1], kind, key)
    except Exception:
        logging.getLogger(__name__).exception("Cohort document parsing failed")
        return Response({'detail': '문서를 해석하지 못했습니다. 텍스트 PDF 또는 정책집 양식 DOCX를 확인해 주세요.'}, status=400)
    try:
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute('SELECT id, code FROM cohorts WHERE id=%s FOR UPDATE', [cohort[0]])
            locked = cur.fetchone()
            if not locked or locked[1] != cohort[1]:
                return Response({'detail': '기수를 찾지 못했습니다.'}, status=404)
            cur.execute("SELECT 1 FROM cohort_deletion_jobs WHERE cohort_id=%s AND state <> 'complete'", [cohort[0]])
            if cur.fetchone():
                return Response({'detail': '삭제 중인 기수에는 문서를 등록할 수 없습니다.'}, status=409)
            # Hold the cohort row lock until publication; deletion preparation waits
            # for this upload and can then enumerate its exact object/namespace.
            put_object(key, data, content_type)
            index_document(records, key)
            if kind == 'curriculum':
                cur.execute('''INSERT INTO curriculum_pdfs (cohort_id,storage_key,original_filename,published,updated_by,updated_at)
                    VALUES (%s,%s,%s,true,%s,now()) ON CONFLICT (cohort_id) DO UPDATE SET
                    storage_key=EXCLUDED.storage_key,original_filename=EXCLUDED.original_filename,
                    published=true,updated_by=EXCLUDED.updated_by,updated_at=now()''', [cohort[0], key, name, user['id']])
            else:
                cur.execute('''INSERT INTO policy_documents (source_key,source_type,source_name,source_url,storage_key,title,is_active,created_at,updated_at)
                    VALUES (%s,'cohort_policy',%s,'',%s,%s,true,now(),now())
                    ON CONFLICT (source_key) DO UPDATE SET source_name=EXCLUDED.source_name,
                    storage_key=EXCLUDED.storage_key,title=EXCLUDED.title,is_active=true,updated_at=now()''',
                    [f'cohort:{cohort[0]}:policy', name, key, name])
    except ProgrammingError as exc:
        if getattr(exc.__cause__, 'sqlstate', None) == '42P01':
            return Response({'detail': '기수 삭제 보호 migration 0017 적용 후 다시 시도해 주세요.'}, status=503)
        logging.getLogger(__name__).exception("Cohort document database failure")
        return Response({'detail': '문서 DB 연결을 완료하지 못했습니다. 기존 문서는 유지됩니다.'}, status=502)
    except Exception:
        logging.getLogger(__name__).exception("Cohort document indexing failed")
        return Response({'detail': '문서 저장 또는 검색 색인을 완료하지 못했습니다. 기존 문서는 유지됩니다. 다시 업로드해 주세요.'}, status=502)
    return {'kind': kind, 'filename': name, 'policyPending': False, 'ragStatus': 'ready', 'chunks': len(records)}
