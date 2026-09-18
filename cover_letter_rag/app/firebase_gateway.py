from __future__ import annotations

from typing import Any
from copy import deepcopy
import hashlib
import json

import firebase_admin
from firebase_admin import auth, credentials, firestore
from google.api_core.exceptions import AlreadyExists
from app.review_workflow import ReviewConflict

from app.config import Settings


def tailored_resume_title(base: dict[str, Any], company: str) -> str:
    """Name only a company-specific copy; never synthesize missing identity."""
    company = str(company or '').strip()
    base_title = str(base.get('title') or '').strip()
    if not company:
        return base_title
    return f'{company} 맞춤 이력서'


class FirebaseAuthenticationError(Exception):
    pass


class ResumeNotFoundError(Exception):
    pass


class ResumeAccessError(Exception):
    pass


class FirebaseGateway:
    """Firebase Admin boundary used only by the backend."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._app = self._initialize_app(settings)
        self._db = firestore.client(app=self._app)

    @staticmethod
    def _initialize_app(settings: Settings):
        try:
            return firebase_admin.get_app()
        except ValueError:
            options = {"projectId": settings.firebase_project_id} if settings.firebase_project_id else None
            return firebase_admin.initialize_app(credentials.ApplicationDefault(), options)

    def verify_id_token(self, id_token: str) -> str:
        try:
            decoded = auth.verify_id_token(id_token, app=self._app)
        except (ValueError, auth.InvalidIdTokenError, auth.ExpiredIdTokenError) as exc:
            raise FirebaseAuthenticationError("invalid or expired Firebase ID token") from exc
        uid = decoded.get("uid")
        if not isinstance(uid, str) or not uid:
            raise FirebaseAuthenticationError("Firebase ID token has no uid")
        return uid

    def get_owned_resume(self, cohort_id: str, resume_id: str, uid: str) -> dict[str, Any]:
        user = self._db.collection('users').document(uid).get().to_dict() or {}
        if user.get('isActive') is not True or user.get('cohortId') != cohort_id:
            raise ResumeAccessError('inactive user or cohort mismatch')
        snapshot = self._resume_ref(cohort_id, resume_id).get()
        if not snapshot.exists:
            raise ResumeNotFoundError("resume not found")
        data = snapshot.to_dict() or {}
        if data.get("userId") != uid:
            # Do not reveal whether another user's document exists.
            raise ResumeNotFoundError("resume not found")
        return data

    def _review_ref(self, cohort_id, resume_id, review_id, tailored_resume_id: str | None = None):
        parent = (
            self._tailored_ref(cohort_id, resume_id, tailored_resume_id)
            if tailored_resume_id
            else self._resume_ref(cohort_id, resume_id)
        )
        return parent.collection(self._settings.firestore_ai_reviews_collection).document(review_id)

    def create_tailored_resume(self, cohort_id: str, resume_id: str, uid: str, job_source: dict[str, Any]) -> dict[str, Any]:
        """Clone an owned base resume once per immutable job snapshot.

        The deterministic id makes a repeated button click idempotent while a changed
        job snapshot intentionally creates a new draft instead of overwriting history.
        """
        base = self.get_owned_resume(cohort_id, resume_id, uid)
        source_hash = hashlib.sha256(json.dumps(base.get('content') or {}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        snapshot_hash = str(job_source.get('snapshot_hash') or '')
        job_id = str(job_source.get('job_id') or '')
        if not job_id or not snapshot_hash:
            raise ValueError('job_source_is_incomplete')
        company_name = str(job_source.get('company') or '').strip()
        title = tailored_resume_title(base, company_name)
        tailored_id = 'tailored_' + hashlib.sha256(
            f'{resume_id}:{job_id}:{snapshot_hash}'.encode()
        ).hexdigest()[:24]
        ref = self._tailored_ref(cohort_id, resume_id, tailored_id)
        payload = {
            'userId': uid,
            'baseResumeId': resume_id,
            'jobId': job_id,
            'companyName': company_name,
            'jobTitle': str(job_source.get('title') or ''),
            'jobSnapshotHash': snapshot_hash,
            'sourceResumeHash': source_hash,
            'status': 'draft',
            'title': title,
            'content': deepcopy(base.get('content') or {}),
            'reviewSession': {},
            'createdAt': firestore.SERVER_TIMESTAMP,
            'updatedAt': firestore.SERVER_TIMESTAMP,
        }
        try:
            ref.create(payload)
            return {'tailored_resume_id': tailored_id, **payload}
        except AlreadyExists:
            existing = ref.get().to_dict() or {}
            if existing.get('userId') != uid or existing.get('jobSnapshotHash') != snapshot_hash:
                raise ResumeNotFoundError('tailored resume not found')
            if title and existing.get('title') != title:
                ref.update({'title': title, 'updatedAt': firestore.SERVER_TIMESTAMP})
                existing['title'] = title
            return {'tailored_resume_id': tailored_id, **existing}

    def list_tailored_resumes(self, cohort_id: str, resume_id: str, uid: str) -> list[dict[str, Any]]:
        base = self.get_owned_resume(cohort_id, resume_id, uid)
        result = []
        for snapshot in self._resume_ref(cohort_id, resume_id).collection('tailoredResumes').stream():
            data = snapshot.to_dict() or {}
            if data.get('userId') == uid:
                title = tailored_resume_title(base, data.get('companyName', ''))
                if title and data.get('title') != title:
                    snapshot.reference.update({
                        'title': title,
                        'updatedAt': firestore.SERVER_TIMESTAMP,
                    })
                    data['title'] = title
                result.append({'tailored_resume_id': snapshot.id, **data})
        return result

    def get_owned_tailored_resume(
        self,
        cohort_id: str,
        resume_id: str,
        tailored_resume_id: str,
        uid: str,
    ) -> dict[str, Any]:
        """Read a company-specific draft only after validating its base resume."""
        self.get_owned_resume(cohort_id, resume_id, uid)
        snapshot = self._tailored_ref(cohort_id, resume_id, tailored_resume_id).get()
        if not snapshot.exists:
            raise ResumeNotFoundError('tailored resume not found')
        data = snapshot.to_dict() or {}
        if data.get('userId') != uid or data.get('baseResumeId') != resume_id:
            raise ResumeNotFoundError('tailored resume not found')
        return data

    def save_tailored_resume_session(
        self,
        cohort_id: str,
        resume_id: str,
        tailored_resume_id: str,
        uid: str,
        state: dict[str, Any],
    ) -> None:
        """Persist resumable UI progress beside the company-specific draft."""
        self.get_owned_tailored_resume(cohort_id, resume_id, tailored_resume_id, uid)
        self._tailored_ref(cohort_id, resume_id, tailored_resume_id).update({
            'reviewSession': deepcopy(state),
            'updatedAt': firestore.SERVER_TIMESTAMP,
        })

    def delete_tailored_resume(
        self,
        cohort_id: str,
        resume_id: str,
        tailored_resume_id: str,
        uid: str,
    ) -> None:
        """Delete one owned company-specific draft and its known child records."""
        tailored = self.get_owned_tailored_resume(
            cohort_id, resume_id, tailored_resume_id, uid,
        )
        ref = self._tailored_ref(cohort_id, resume_id, tailored_resume_id)
        workspace_id = str(tailored.get('workspaceResumeId') or '')
        if workspace_id:
            workspace_ref = self._resume_ref(cohort_id, workspace_id)
            workspace = workspace_ref.get().to_dict() or {}
            if (
                workspace.get('userId') == uid and
                workspace.get('sourceTailoredResumeId') == tailored_resume_id
            ):
                self._db.recursive_delete(workspace_ref)
        # Firestore 문서 삭제는 하위 컬렉션을 자동 삭제하지 않는다. SDK의
        # recursive_delete를 사용해야 첨삭/적용/대화 기록까지 남김없이 지워진다.
        self._db.recursive_delete(ref)

    def promote_tailored_resume(
        self,
        cohort_id: str,
        resume_id: str,
        tailored_resume_id: str,
        uid: str,
    ) -> str:
        """Expose a completed tailored draft through the normal resume editor."""
        self.get_owned_tailored_resume(cohort_id, resume_id, tailored_resume_id, uid)
        ref = self._tailored_ref(cohort_id, resume_id, tailored_resume_id)
        workspace_id = 'matched_' + hashlib.sha256(
            f'{resume_id}:{tailored_resume_id}'.encode()
        ).hexdigest()[:24]
        workspace_ref = self._resume_ref(cohort_id, workspace_id)

        @firestore.transactional
        def promote(transaction):
            tailored = ref.get(transaction=transaction).to_dict() or {}
            existing = workspace_ref.get(transaction=transaction).to_dict() or {}
            if tailored.get('userId') != uid or tailored.get('baseResumeId') != resume_id:
                raise ResumeNotFoundError('tailored resume not found')
            if existing and (
                existing.get('userId') != uid or
                existing.get('sourceTailoredResumeId') != tailored_resume_id
            ):
                raise ResumeNotFoundError('workspace resume not found')
            if not existing:
                transaction.create(workspace_ref, {
                    'userId': uid,
                    'title': tailored.get('title') or '맞춤 이력서',
                    'status': 'writing',
                    'sections': {},
                    'content': deepcopy(tailored.get('content') or {}),
                    'isBaseResume': False,
                    'baseResumeId': resume_id,
                    'sourceTailoredResumeId': tailored_resume_id,
                    'jobId': tailored.get('jobId') or '',
                    'jobCompany': tailored.get('companyName') or '',
                    'jobTitle': tailored.get('jobTitle') or '',
                    'feedbackCount': 0,
                    'lastSeenFeedbackCount': 0,
                    'readFeedbackIds': [],
                    'reviewerReadFeedbackIds': [],
                    'revisionCount': 0,
                    'createdAt': firestore.SERVER_TIMESTAMP,
                    'updatedAt': firestore.SERVER_TIMESTAMP,
                })
            elif not existing.get('jobId'):
                transaction.update(workspace_ref, {
                    'jobId': tailored.get('jobId') or '',
                    'jobCompany': tailored.get('companyName') or '',
                    'jobTitle': tailored.get('jobTitle') or '',
                    'updatedAt': firestore.SERVER_TIMESTAMP,
                })
            transaction.update(ref, {
                'workspaceResumeId': workspace_id,
                'status': 'ready',
                'updatedAt': firestore.SERVER_TIMESTAMP,
            })
            return workspace_id

        return promote(self._db.transaction())

    def get_ai_review(self, cohort_id, resume_id, uid, review_id, tailored_resume_id: str | None = None):
        if tailored_resume_id:
            self.get_owned_tailored_resume(cohort_id, resume_id, tailored_resume_id, uid)
        else:
            self.get_owned_resume(cohort_id, resume_id, uid)
        data = self._review_ref(cohort_id, resume_id, review_id, tailored_resume_id).get().to_dict() or {}
        if data.get('userId') != uid or not data.get('response'):
            raise ResumeNotFoundError('review not found')
        return data['response']

    def claim_review(self, cohort_id, resume_id, uid, request_id, fingerprint, tailored_resume_id: str | None = None):
        ref = self._review_ref(cohort_id, resume_id, request_id, tailored_resume_id)
        try:
            ref.create({'userId': uid, 'fingerprint': fingerprint, 'status': 'processing', 'createdAt': firestore.SERVER_TIMESTAMP})
            return {}
        except AlreadyExists:
            state = ref.get().to_dict() or {}
            if state.get('userId') != uid or state.get('fingerprint') != fingerprint:
                raise ReviewConflict('request_id_reused_with_different_input')
            if state.get('response'):
                return state
            raise ReviewConflict('request_processing_or_failed: inspect before issuing a new request_id')

    def complete_review(self, cohort_id, resume_id, uid, request_id, response, tailored_resume_id: str | None = None):
        if tailored_resume_id:
            self.get_owned_tailored_resume(cohort_id, resume_id, tailored_resume_id, uid)
        else:
            self.get_owned_resume(cohort_id, resume_id, uid)
        self._review_ref(cohort_id, resume_id, request_id, tailored_resume_id).update({'response': response, 'status': 'complete', 'telemetry': response['telemetry']})

    def fail_review(self, cohort_id, resume_id, uid, request_id, telemetry, tailored_resume_id: str | None = None):
        # Keep any response committed by an ambiguous successful update recoverable.
        self._review_ref(cohort_id, resume_id, request_id, tailored_resume_id).update({'status': 'failed', 'telemetry': telemetry})

    def save_ai_review(
        self,
        cohort_id: str,
        resume_id: str,
        uid: str,
        payload: dict[str, Any],
    ) -> str:
        document = self._resume_ref(cohort_id, resume_id).collection(
            self._settings.firestore_ai_reviews_collection
        ).document()
        document.set(
            {
                **payload,
                "userId": uid,
                "createdAt": firestore.SERVER_TIMESTAMP,
            }
        )
        return document.id

    def get_job_requirements(self, key: str) -> list[dict] | None:
        """공고별로 한 번 정리해 둔 요건 목록. 공고 원문에서 뽑은 것이라 사용자 데이터가 아니다."""
        snapshot = self._db.collection(self._settings.firestore_job_requirements_collection).document(key).get()
        return (snapshot.to_dict() or {}).get('requirements')

    def save_job_requirements(self, key: str, requirements: list[dict]) -> None:
        self._db.collection(self._settings.firestore_job_requirements_collection).document(key).set({
            'requirements': requirements,
            'createdAt': firestore.SERVER_TIMESTAMP,
        })

    def _resume_ref(self, cohort_id: str, resume_id: str):
        return (
            self._db.collection(self._settings.firestore_cohorts_collection)
            .document(cohort_id)
            .collection(self._settings.firestore_resumes_collection)
            .document(resume_id)
        )

    def _tailored_ref(self, cohort_id: str, resume_id: str, tailored_resume_id: str):
        return self._resume_ref(cohort_id, resume_id).collection('tailoredResumes').document(tailored_resume_id)


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise FirebaseAuthenticationError("Authorization header is required")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token.strip():
        raise FirebaseAuthenticationError("Authorization must use Bearer token")
    return token.strip()
