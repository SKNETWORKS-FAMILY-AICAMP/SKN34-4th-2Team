"""Explicit selection only; atomic apply/undo without an LLM call."""
from copy import deepcopy
import re

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field
from firebase_admin import firestore
from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import GoogleAuthError

from app.models import StrictModel
from app.config import get_settings
from app.firebase_gateway import FirebaseGateway, FirebaseAuthenticationError, ResumeAccessError, ResumeNotFoundError, extract_bearer_token
from app.review_workflow import digest, ReviewConflict, ReviewInputError

ID = r'^[A-Za-z0-9_-]{1,100}$'


class ApplyRequest(StrictModel):
    cohort_id: str = Field(pattern=ID)
    resume_id: str = Field(pattern=ID)
    tailored_resume_id: str | None = Field(default=None, pattern=ID)
    request_id: str = Field(pattern=ID)
    review_id: str = Field(pattern=ID)
    expected_input_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    selected_indices: list[int] = Field(min_length=1, max_length=100)


class UndoRequest(StrictModel):
    cohort_id: str = Field(pattern=ID)
    resume_id: str = Field(pattern=ID)
    tailored_resume_id: str | None = Field(default=None, pattern=ID)
    request_id: str = Field(pattern=ID)
    application_id: str = Field(pattern=ID)
    expected_input_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


class ApplyResponse(StrictModel):
    operation_id: str
    input_hash: str
    changed_fields: list[str]


def locate(content, path):
    """Only fields the review extractor exposes can be written."""
    from app.resume_review import extract_review_fields
    if path not in extract_review_fields(content)[0]:
        raise ReviewConflict('field_not_found')
    target = content
    parts = path.split('.')
    for part in parts[:-1]:
        match = re.fullmatch(r'(\w+)\[(\d+)\]', part)
        target = target[match[1]][int(match[2])] if match else target[part]
    return target, parts[-1]


def build_application(content, review, request):
    if digest(content) != request.expected_input_hash or review.get('input_hash') != request.expected_input_hash:
        raise ReviewConflict('resume_version_changed')
    indices = request.selected_indices
    edits = review.get('sentence_reviews', [])
    if len(indices) != len(set(indices)) or any(i < 0 or i >= len(edits) for i in indices):
        raise ReviewInputError('invalid_selection')
    updated, spans, additions = deepcopy(content), {}, []
    for i in indices:
        edit = edits[i]
        replacement, quote, path = edit.get('suggested_revision'), edit.get('original_quote'), edit.get('field_path')
        new_item = edit.get('new_item')
        if new_item:
            # 기존 칸을 고치지 않고 프로젝트 목록 끝에 항목을 하나 더한다. 기존 항목은 건드리지 않는다.
            if (edit.get('validation_issues') or edit.get('status') != 'improved'
                    or new_item.get('section') != 'projects' or not str(new_item.get('description') or '').strip()
                    or not str(new_item.get('name') or '').strip()):
                raise ReviewInputError('selection_not_applicable')
            additions.append((path, new_item))
            continue
        if edit.get('validation_issues') or edit.get('status') not in ('improved', 'formatting') or not replacement or not replacement.strip() or not quote:
            raise ReviewInputError('selection_not_applicable')
        target, key = locate(content, path)
        original = target[key]
        # Masked quotations cannot be located safely in raw source. Never substitute PII.
        if '[연락처 삭제]' in replacement or original.count(quote) != 1:
            raise ReviewConflict('ambiguous_or_masked_quote')
        start = original.index(quote)
        end = start + len(quote)
        for left, right, _ in spans.get(path, []):
            if start < right and left < end:
                raise ReviewConflict('overlapping_edits')
        spans.setdefault(path, []).append((start, end, replacement))
    for path, changes in spans.items():
        target, key = locate(updated, path)
        value = target[key]
        for start, end, replacement in sorted(changes, reverse=True):
            value = value[:start] + replacement + value[end:]
        target[key] = value
    added = []
    for path, item in additions:
        projects = updated.setdefault('projects', [])
        if not isinstance(projects, list):
            raise ReviewConflict('field_not_found')
        # 제안할 때의 목록 길이와 같아야 한다. 입력 해시가 같으면 늘 같지만, 한 번에 둘을 고르면 두 번째가 어긋난다.
        if path != f'projects[{len(projects)}].description':
            raise ReviewConflict('resume_item_changed')
        projects.append({
            'id': 'ai' + digest([request.review_id, path, item.get('name')])[:20],
            'name': str(item.get('name') or '').strip(),
            'startDate': '',
            'endDate': '',
            'role': str(item.get('role') or '').strip(),
            'techStack': str(item.get('tech_stack') or '').strip(),
            'description': str(item['description']).strip(),
            'url': '',
        })
        added.append(path)
    return updated, sorted([*spans, *added])


def rebase_review_response(response, content):
    """Move an existing chat review onto an edit it just applied.

    Applying one suggestion changes the Firestore resume.  The remaining
    questions are still useful, but their review snapshot must point at that
    new content; otherwise the next answer is rejected as a stale request.
    No LLM call is made here.
    """
    from app.resume_review import extract_review_fields
    from app.review_workflow import redact

    rebased = deepcopy(response)
    fields, _ = extract_review_fields(content)
    rebased['input_hash'] = digest(content)
    rebased['input_fields'] = {path: redact(value) for path, value in fields.items()}
    return rebased


def mutate(gateway, uid, request, undo=False):
    # 공고 맞춤 첨삭은 기본 이력서 하위의 공고별 사본만 변경한다.
    resume_ref = (
        gateway._tailored_ref(request.cohort_id, request.resume_id, request.tailored_resume_id)
        if request.tailored_resume_id
        else gateway._resume_ref(request.cohort_id, request.resume_id)
    )
    operations = resume_ref.collection('aiApplications')
    op_ref = operations.document(request.request_id)
    source_ref = (
        operations.document(request.application_id)
        if undo
        else gateway._review_ref(
            request.cohort_id,
            request.resume_id,
            request.review_id,
            request.tailored_resume_id,
        )
    )
    fingerprint = digest([uid, 'undo' if undo else 'apply', request.model_dump()])

    @firestore.transactional
    def execute(transaction):
        user = gateway._db.collection('users').document(uid).get(transaction=transaction).to_dict() or {}
        resume = resume_ref.get(transaction=transaction).to_dict() or {}
        old_op = op_ref.get(transaction=transaction).to_dict() or {}
        source = source_ref.get(transaction=transaction).to_dict() or {}
        if user.get('isActive') is not True or user.get('cohortId') != request.cohort_id:
            raise ResumeAccessError()
        if resume.get('userId') != uid:
            raise ResumeNotFoundError()
        if old_op:
            if old_op.get('userId') != uid or old_op.get('fingerprint') != fingerprint:
                raise ReviewConflict('request_id_reused')
            return ApplyResponse.model_validate(old_op['response'])
        if resume.get('status') in ('approved', 'completed'):
            raise ReviewConflict('approved_resume_read_only')
        if source.get('userId') != uid:
            raise ResumeNotFoundError()
        before = resume.get('content') or {}
        if undo:
            if source.get('kind') != 'apply' or source.get('undoneBy'):
                raise ReviewConflict('application_not_reversible')
            if digest(before) != request.expected_input_hash or digest(before) != source.get('after_hash'):
                raise ReviewConflict('resume_changed_after_application')
            after, changed = source['before'], source['response']['changed_fields']
            review_id = source.get('source_id')
            if not review_id:
                raise ReviewConflict('application_source_review_missing')
            review_ref = gateway._review_ref(
                request.cohort_id,
                request.resume_id,
                review_id,
                request.tailored_resume_id,
            )
            review_source = review_ref.get(transaction=transaction).to_dict() or {}
            if review_source.get('userId') != uid:
                raise ResumeNotFoundError()
        else:
            after, changed = build_application(before, source.get('response') or {}, request)
        result = ApplyResponse(operation_id=request.request_id, input_hash=digest(after), changed_fields=changed)
        transaction.create(op_ref, {'userId': uid, 'fingerprint': fingerprint, 'kind': 'undo' if undo else 'apply',
                                   'before': before, 'after_hash': digest(after), 'response': result.model_dump(),
                                   'source_id': request.application_id if undo else request.review_id,
                                   'createdAt': firestore.SERVER_TIMESTAMP})
        transaction.update(resume_ref, {'content': after, 'updatedAt': firestore.SERVER_TIMESTAMP})
        if not undo:
            # Keep the same chat session usable after a selected revision is
            # applied.  The review itself was already generated; only its
            # snapshot is rebased to the just-persisted resume content.
            transaction.update(source_ref, {'response': rebase_review_response(source['response'], after)})
        if undo:
            transaction.update(source_ref, {'undoneBy': request.request_id})
            # Undo restores the resume snapshot, so restore the chat review's
            # snapshot as well. Otherwise the next answer compares the restored
            # resume with the post-apply hash and rejects the conversation as stale.
            transaction.update(
                review_ref,
                {'response': rebase_review_response(review_source['response'], after)},
            )
        return result

    return execute(gateway._db.transaction())


router = APIRouter()


def gateway_dependency():
    try:
        return FirebaseGateway(get_settings())
    except (GoogleAuthError, GoogleAPIError, ValueError) as exc:
        raise HTTPException(503, 'Firebase unavailable') from exc


def authenticated_token(authorization: str | None = Header(default=None)):
    try:
        return extract_bearer_token(authorization)
    except FirebaseAuthenticationError as exc:
        raise HTTPException(401, 'Firebase authentication failed') from exc


def dispatch(request, token, gateway, undo):
    try:
        return mutate(gateway, gateway.verify_id_token(token), request, undo)
    except FirebaseAuthenticationError as exc:
        raise HTTPException(401, 'Firebase authentication failed') from exc
    except ResumeAccessError as exc:
        raise HTTPException(403, 'Resume access denied') from exc
    except ResumeNotFoundError as exc:
        raise HTTPException(404, 'Resume or source not found') from exc
    except ReviewConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ReviewInputError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(503, 'Firebase unavailable') from exc


@router.post('/api/v1/resumes/reviews/apply', response_model=ApplyResponse)
def apply_review(request: ApplyRequest, token: str = Depends(authenticated_token), gateway=Depends(gateway_dependency)):
    return dispatch(request, token, gateway, False)


@router.post('/api/v1/resumes/reviews/undo', response_model=ApplyResponse)
def undo_review(request: UndoRequest, token: str = Depends(authenticated_token), gateway=Depends(gateway_dependency)):
    return dispatch(request, token, gateway, True)
