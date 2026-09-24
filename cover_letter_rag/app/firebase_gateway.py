from __future__ import annotations

from typing import Any
from copy import deepcopy
import hashlib
import json

import firebase_admin
from firebase_admin import auth, credentials
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

    @property
    def _db(self):
        from firebase_admin import firestore
        return firestore.client(app=self._app)

    def _pg(self):
        from chatbot.database import connect
        return connect()

    def _cohort_user(self, conn, cohort_id: str, uid: str):
        row = conn.execute(
            """SELECT u.id, u.is_active, c.code, c.id AS cohort_pk
               FROM users u LEFT JOIN cohorts c ON c.id = u.cohort_id
               WHERE u.firebase_uid = %s""",
            (uid,),
        ).fetchone()
        if not row or row[1] is not True or str(row[2]) != str(cohort_id):
            raise ResumeAccessError("inactive user or cohort mismatch")
        return {"user_pk": row[0], "cohort_pk": row[3], "code": row[2]}

    def _resume_legacy(self, resume_id: str, tailored_resume_id: str | None = None) -> str:
        if tailored_resume_id:
            return f"{resume_id}/tailored/{tailored_resume_id}"
        return resume_id

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
        with self._pg() as conn:
            ident = self._cohort_user(conn, cohort_id, uid)
            row = conn.execute(
                """SELECT r.legacy_id, r.title, r.status, r.content, r.user_id, u.firebase_uid
                   FROM resumes r JOIN users u ON u.id = r.user_id
                   WHERE r.legacy_id = %s AND r.cohort_id = %s""",
                (resume_id, ident["cohort_pk"]),
            ).fetchone()
            if not row or row[5] != uid:
                raise ResumeNotFoundError("resume not found")
            return {
                "title": row[1],
                "status": row[2],
                "content": row[3] or {},
                "userId": row[5],
            }

    def _review_ref(self, cohort_id, resume_id, review_id, tailored_resume_id: str | None = None):
        parent = (
            self._tailored_ref(cohort_id, resume_id, tailored_resume_id)
            if tailored_resume_id
            else self._resume_ref(cohort_id, resume_id)
        )
        return parent.collection(self._settings.firestore_ai_reviews_collection).document(review_id)

    def create_tailored_resume(self, cohort_id: str, resume_id: str, uid: str, job_source: dict[str, Any]) -> dict[str, Any]:
        """Clone an owned base resume once per immutable job snapshot."""
        from psycopg.types.json import Jsonb

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
        legacy = f"{resume_id}/tailored/{tailored_id}"
        sections = {
            "_tailored": {
                "companyName": company_name,
                "jobTitle": str(job_source.get('title') or ''),
                "jobSnapshotHash": snapshot_hash,
                "sourceResumeHash": source_hash,
                "reviewSession": {},
            }
        }
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
        }
        with self._pg() as conn:
            ident = self._cohort_user(conn, cohort_id, uid)
            parent = conn.execute(
                "SELECT id FROM resumes WHERE legacy_id = %s AND cohort_id = %s",
                (resume_id, ident["cohort_pk"]),
            ).fetchone()
            if not parent:
                raise ResumeNotFoundError("resume not found")
            existing = conn.execute(
                "SELECT id, title, content, sections, status, linked_job_id FROM resumes WHERE legacy_id = %s",
                (legacy,),
            ).fetchone()
            if existing:
                # 같은 공고 · 스냅샷으로 만든 이름(tailored_id)이므로 옛 맞춤본이면 정보를 채워 이어 쓴다
                meta = self._adopt_legacy_meta(conn, existing[0], existing[3], sections["_tailored"], job_id)
                if meta.get("jobSnapshotHash") != snapshot_hash:
                    raise ResumeNotFoundError("tailored resume not found")
                if title and existing[1] != title:
                    conn.execute("UPDATE resumes SET title=%s, updated_at=now() WHERE id=%s", (title, existing[0]))
                    conn.commit()
                # 이미 있는 맞춤본은 그 내용과 저장된 첨삭 대화를 돌려준다. 원본 내용을 주면 반영한 수정이
                # 안 보이고, 첨삭 창이 대화를 이어 가지 못했다.
                return {
                    "tailored_resume_id": tailored_id,
                    **payload,
                    "title": title or existing[1],
                    "content": existing[2] or payload["content"],
                    "reviewSession": meta.get("reviewSession") or {},
                }
            conn.execute(
                """INSERT INTO resumes (legacy_id, cohort_id, user_id, title, status, content, sections, is_base_resume, base_resume_id, linked_job_id, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,'draft',%s,%s,false,%s,%s, now(), now())""",
                (legacy, ident["cohort_pk"], ident["user_pk"], title, Jsonb(payload["content"]), Jsonb(sections), parent[0], job_id),
            )
            conn.commit()
        return {"tailored_resume_id": tailored_id, **payload}

    def _tailored_meta(self, sections) -> dict:
        return dict((sections or {}).get("_tailored") or {})

    def _adopt_legacy_meta(self, conn, row_id, sections, fresh_meta: dict, job_id: str) -> dict:
        """Firestore 에서 옮겨 온 맞춤본은 _tailored 정보(공고 스냅샷 · 대화)가 비어 있다.

        그대로 두면 사본 만들기는 404, 스냅샷 확인은 tailored_resume_job_changed 로 매번 막혔다.
        지금 공고 스냅샷을 채워 넣고 이어 쓴다. 이미 정보가 있으면 건드리지 않는다.
        """
        from psycopg.types.json import Jsonb

        sections = dict(sections or {})
        meta = dict(sections.get("_tailored") or {})
        if meta.get("jobSnapshotHash"):
            return meta
        meta = {**fresh_meta, **{k: v for k, v in meta.items() if v}}
        sections["_tailored"] = meta
        conn.execute(
            "UPDATE resumes SET sections=%s, linked_job_id=COALESCE(linked_job_id, %s), updated_at=now() WHERE id=%s",
            (Jsonb(sections), job_id, row_id),
        )
        conn.commit()
        return meta

    def adopt_legacy_tailored(self, cohort_id, resume_id, tailored_resume_id, uid, job_source: dict[str, Any]) -> None:
        """옛 맞춤본을 목록에서 이어 열 때(재첨삭). 연결된 공고가 같을 때만 지금 스냅샷을 채운다."""
        base = self.get_owned_resume(cohort_id, resume_id, uid)
        job_id = str(job_source.get("job_id") or "")
        snapshot_hash = str(job_source.get("snapshot_hash") or "")
        if not job_id or not snapshot_hash:
            return
        legacy = f"{resume_id}/tailored/{tailored_resume_id}"
        with self._pg() as conn:
            row = conn.execute(
                "SELECT id, sections, linked_job_id FROM resumes WHERE legacy_id = %s",
                (legacy,),
            ).fetchone()
            if not row or (row[2] and row[2] != job_id):
                return
            source_hash = hashlib.sha256(
                json.dumps(base.get("content") or {}, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()
            fresh = {
                "companyName": str(job_source.get("company") or "").strip(),
                "jobTitle": str(job_source.get("title") or ""),
                "jobSnapshotHash": snapshot_hash,
                "sourceResumeHash": source_hash,
                "reviewSession": {},
            }
            self._adopt_legacy_meta(conn, row[0], row[1], fresh, job_id)

    def list_tailored_resumes(self, cohort_id: str, resume_id: str, uid: str) -> list[dict[str, Any]]:
        base = self.get_owned_resume(cohort_id, resume_id, uid)
        result = []
        with self._pg() as conn:
            ident = self._cohort_user(conn, cohort_id, uid)
            parent = conn.execute(
                "SELECT id FROM resumes WHERE legacy_id = %s AND cohort_id = %s",
                (resume_id, ident["cohort_pk"]),
            ).fetchone()
            if not parent:
                return []
            rows = conn.execute(
                "SELECT legacy_id, title, status, content, sections, linked_job_id FROM resumes WHERE base_resume_id = %s",
                (parent[0],),
            ).fetchall()
        for legacy, title, status, content, sections, job_id in rows:
            meta = self._tailored_meta(sections)
            company = meta.get("companyName", "")
            wanted = tailored_resume_title(base, company)
            tid = str(legacy).rsplit("/", 1)[-1]
            result.append({
                "tailored_resume_id": tid,
                "title": wanted or title,
                "status": status,
                "content": content or {},
                "userId": uid,
                "baseResumeId": resume_id,
                "jobId": job_id or "",
                **meta,
            })
        return result

    def get_owned_tailored_resume(self, cohort_id, resume_id, tailored_resume_id, uid):
        self.get_owned_resume(cohort_id, resume_id, uid)
        legacy = f"{resume_id}/tailored/{tailored_resume_id}"
        with self._pg() as conn:
            ident = self._cohort_user(conn, cohort_id, uid)
            row = conn.execute(
                """SELECT r.title, r.status, r.content, r.sections, r.linked_job_id, u.firebase_uid, r.base_resume_id
                   FROM resumes r JOIN users u ON u.id = r.user_id
                   WHERE r.legacy_id = %s AND r.cohort_id = %s""",
                (legacy, ident["cohort_pk"]),
            ).fetchone()
        if not row or row[5] != uid:
            raise ResumeNotFoundError("tailored resume not found")
        meta = self._tailored_meta(row[3])
        return {
            "title": row[0],
            "status": row[1],
            "content": row[2] or {},
            "userId": uid,
            "baseResumeId": resume_id,
            "jobId": row[4] or meta.get("jobId") or "",
            **meta,
        }

    def save_tailored_resume_session(self, cohort_id, resume_id, tailored_resume_id, uid, state):
        from psycopg.types.json import Jsonb

        self.get_owned_tailored_resume(cohort_id, resume_id, tailored_resume_id, uid)
        legacy = f"{resume_id}/tailored/{tailored_resume_id}"
        with self._pg() as conn:
            row = conn.execute("SELECT sections FROM resumes WHERE legacy_id = %s", (legacy,)).fetchone()
            sections = dict(row[0] or {})
            meta = dict(sections.get("_tailored") or {})
            meta["reviewSession"] = deepcopy(state)
            sections["_tailored"] = meta
            conn.execute("UPDATE resumes SET sections=%s, updated_at=now() WHERE legacy_id=%s", (Jsonb(sections), legacy))
            conn.commit()

    def delete_tailored_resume(self, cohort_id, resume_id, tailored_resume_id, uid):
        tailored = self.get_owned_tailored_resume(cohort_id, resume_id, tailored_resume_id, uid)
        legacy = f"{resume_id}/tailored/{tailored_resume_id}"
        with self._pg() as conn:
            ident = self._cohort_user(conn, cohort_id, uid)
            workspace_id = str(tailored.get("workspaceResumeId") or "")
            if workspace_id:
                conn.execute(
                    "DELETE FROM resumes WHERE legacy_id = %s AND cohort_id = %s AND user_id = %s",
                    (workspace_id, ident["cohort_pk"], ident["user_pk"]),
                )
            conn.execute("DELETE FROM resumes WHERE legacy_id = %s", (legacy,))
            conn.commit()

    def promote_tailored_resume(self, cohort_id, resume_id, tailored_resume_id, uid) -> str:
        from psycopg.types.json import Jsonb

        tailored = self.get_owned_tailored_resume(cohort_id, resume_id, tailored_resume_id, uid)
        workspace_id = "matched_" + hashlib.sha256(f"{resume_id}:{tailored_resume_id}".encode()).hexdigest()[:24]
        tailored_legacy = f"{resume_id}/tailored/{tailored_resume_id}"
        with self._pg() as conn:
            ident = self._cohort_user(conn, cohort_id, uid)
            parent = conn.execute(
                "SELECT id FROM resumes WHERE legacy_id = %s AND cohort_id = %s",
                (resume_id, ident["cohort_pk"]),
            ).fetchone()
            tailored_row = conn.execute("SELECT id, sections FROM resumes WHERE legacy_id = %s", (tailored_legacy,)).fetchone()
            existing = conn.execute("SELECT id FROM resumes WHERE legacy_id = %s", (workspace_id,)).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO resumes (legacy_id, cohort_id, user_id, title, status, content, sections, is_base_resume, base_resume_id, source_tailored_resume_id, linked_job_id, created_at, updated_at)
                       VALUES (%s,%s,%s,%s,'writing',%s,'{}',false,%s,%s,%s, now(), now())""",
                    (workspace_id, ident["cohort_pk"], ident["user_pk"], tailored.get("title") or "맞춤 이력서",
                     Jsonb(deepcopy(tailored.get("content") or {})), parent[0] if parent else None,
                     tailored_row[0] if tailored_row else None, tailored.get("jobId") or ""),
                )
            sections = dict((tailored_row[1] if tailored_row else {}) or {})
            meta = dict(sections.get("_tailored") or {})
            meta["workspaceResumeId"] = workspace_id
            sections["_tailored"] = meta
            conn.execute(
                "UPDATE resumes SET status='ready', sections=%s, updated_at=now() WHERE legacy_id=%s",
                (Jsonb(sections), tailored_legacy),
            )
            conn.commit()
        return workspace_id

    def apply_or_undo(self, uid, request, undo=False):
        from psycopg.types.json import Jsonb
        from app.resume_apply import ApplyResponse, build_application, rebase_review_response
        from app.review_workflow import digest

        legacy_resume = self._resume_legacy(request.resume_id, request.tailored_resume_id)
        op_legacy = f"{legacy_resume}/{request.request_id}"
        fingerprint = digest([uid, "undo" if undo else "apply", request.model_dump()])
        with self._pg() as conn:
            ident = self._cohort_user(conn, request.cohort_id, uid)
            resume = conn.execute(
                "SELECT id, user_id, status, content FROM resumes WHERE legacy_id = %s AND cohort_id = %s FOR UPDATE",
                (legacy_resume, ident["cohort_pk"]),
            ).fetchone()
            if not resume:
                resume = conn.execute(
                    "SELECT id, user_id, status, content FROM resumes WHERE legacy_id = %s AND cohort_id = %s FOR UPDATE",
                    (request.resume_id, ident["cohort_pk"]),
                ).fetchone()
            if not resume:
                raise ResumeNotFoundError()
            user_uid = conn.execute("SELECT firebase_uid FROM users WHERE id = %s", (resume[1],)).fetchone()
            if not user_uid or user_uid[0] != uid:
                raise ResumeNotFoundError()
            old = conn.execute(
                "SELECT fingerprint, response FROM resume_ai_applications WHERE legacy_id = %s",
                (op_legacy,),
            ).fetchone()
            if old:
                if old[0] != fingerprint:
                    raise ReviewConflict("request_id_reused")
                return ApplyResponse.model_validate(old[1])
            if resume[2] in ("approved", "completed"):
                raise ReviewConflict("approved_resume_read_only")
            before = resume[3] or {}
            if undo:
                source_legacy = f"{legacy_resume}/{request.application_id}"
                source = conn.execute(
                    "SELECT kind, undone_by, after_hash, before, response, source_id, user_id FROM resume_ai_applications WHERE legacy_id = %s",
                    (source_legacy,),
                ).fetchone()
                if not source or source[0] != "apply" or source[1]:
                    raise ReviewConflict("application_not_reversible")
                if digest(before) != request.expected_input_hash or digest(before) != source[2]:
                    raise ReviewConflict("resume_changed_after_application")
                after, changed = source[3], source[4]["changed_fields"]
                review_id = source[5]
                review_legacy = f"{legacy_resume}/{review_id}"
                review_row = conn.execute("SELECT response FROM resume_ai_reviews WHERE legacy_id = %s", (review_legacy,)).fetchone()
            else:
                review_legacy = f"{legacy_resume}/{request.review_id}"
                review_row = conn.execute("SELECT response, user_id FROM resume_ai_reviews WHERE legacy_id = %s", (review_legacy,)).fetchone()
                if not review_row:
                    raise ResumeNotFoundError()
                after, changed = build_application(before, review_row[0] or {}, request)
            result = ApplyResponse(operation_id=request.request_id, input_hash=digest(after), changed_fields=changed)
            conn.execute(
                """INSERT INTO resume_ai_applications (legacy_id, resume_id, user_id, fingerprint, kind, before, after_hash, response, source_id, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now())""",
                (op_legacy, resume[0], ident["user_pk"], fingerprint, "undo" if undo else "apply",
                 Jsonb(before), digest(after), Jsonb(result.model_dump()),
                 request.application_id if undo else request.review_id),
            )
            conn.execute("UPDATE resumes SET content=%s, updated_at=now() WHERE id=%s", (Jsonb(after), resume[0]))
            if not undo and review_row:
                conn.execute(
                    "UPDATE resume_ai_reviews SET response=%s WHERE legacy_id=%s",
                    (Jsonb(rebase_review_response(review_row[0], after)), review_legacy),
                )
            if undo:
                conn.execute(
                    "UPDATE resume_ai_applications SET undone_by=%s WHERE legacy_id=%s",
                    (request.request_id, source_legacy),
                )
                if review_row:
                    conn.execute(
                        "UPDATE resume_ai_reviews SET response=%s WHERE legacy_id=%s",
                        (Jsonb(rebase_review_response(review_row[0], after)), review_legacy),
                    )
            conn.commit()
        return result


    def get_ai_review(self, cohort_id, resume_id, uid, review_id, tailored_resume_id: str | None = None):
        with self._pg() as conn:
            ident = self._cohort_user(conn, cohort_id, uid)
            legacy = f"{self._resume_legacy(resume_id, tailored_resume_id)}/{review_id}"
            row = conn.execute(
                """SELECT r.response, u.firebase_uid FROM resume_ai_reviews r
                   JOIN resumes rs ON rs.id = r.resume_id
                   JOIN users u ON u.id = r.user_id
                   WHERE r.legacy_id = %s AND rs.cohort_id = %s""",
                (legacy, ident["cohort_pk"]),
            ).fetchone()
            if not row or row[1] != uid or not row[0]:
                raise ResumeNotFoundError("review not found")
            return row[0]

    def claim_review(self, cohort_id, resume_id, uid, request_id, fingerprint, tailored_resume_id: str | None = None):
        from psycopg.errors import UniqueViolation

        with self._pg() as conn:
            ident = self._cohort_user(conn, cohort_id, uid)
            legacy_resume = self._resume_legacy(resume_id, tailored_resume_id)
            resume = conn.execute(
                "SELECT id FROM resumes WHERE legacy_id = %s AND cohort_id = %s",
                (legacy_resume, ident["cohort_pk"]),
            ).fetchone()
            if not resume:
                # tailored 행이 없으면 부모 이력서에 붙인다
                resume = conn.execute(
                    "SELECT id FROM resumes WHERE legacy_id = %s AND cohort_id = %s",
                    (resume_id, ident["cohort_pk"]),
                ).fetchone()
            if not resume:
                raise ResumeNotFoundError("resume not found")
            legacy = f"{legacy_resume}/{request_id}"
            try:
                conn.execute(
                    """INSERT INTO resume_ai_reviews (legacy_id, resume_id, user_id, fingerprint, status, payload, created_at)
                       VALUES (%s,%s,%s,%s,'processing','{}', now())""",
                    (legacy, resume[0], ident["user_pk"], fingerprint),
                )
                conn.commit()
                return {}
            except UniqueViolation:
                conn.rollback()
                state = conn.execute(
                    "SELECT user_id, fingerprint, response, status FROM resume_ai_reviews WHERE legacy_id = %s",
                    (legacy,),
                ).fetchone()
                if not state:
                    raise ReviewConflict("request_processing_or_failed: inspect before issuing a new request_id")
                user = conn.execute("SELECT firebase_uid FROM users WHERE id = %s", (state[0],)).fetchone()
                if not user or user[0] != uid or state[1] != fingerprint:
                    raise ReviewConflict("request_id_reused_with_different_input")
                if state[2]:
                    return {"response": state[2], "status": state[3]}
                raise ReviewConflict("request_processing_or_failed: inspect before issuing a new request_id")

    def complete_review(self, cohort_id, resume_id, uid, request_id, response, tailored_resume_id: str | None = None):
        from psycopg.types.json import Jsonb

        if tailored_resume_id:
            self.get_owned_resume(cohort_id, resume_id, uid)
        else:
            self.get_owned_resume(cohort_id, resume_id, uid)
        legacy = f"{self._resume_legacy(resume_id, tailored_resume_id)}/{request_id}"
        with self._pg() as conn:
            conn.execute(
                """UPDATE resume_ai_reviews
                   SET response = %s, status = 'complete', telemetry = %s
                   WHERE legacy_id = %s""",
                (Jsonb(response), Jsonb(response.get("telemetry")) if isinstance(response, dict) else None, legacy),
            )
            conn.commit()

    def fail_review(self, cohort_id, resume_id, uid, request_id, telemetry, tailored_resume_id: str | None = None):
        from psycopg.types.json import Jsonb

        legacy = f"{self._resume_legacy(resume_id, tailored_resume_id)}/{request_id}"
        with self._pg() as conn:
            conn.execute(
                "UPDATE resume_ai_reviews SET status = 'failed', telemetry = %s WHERE legacy_id = %s",
                (Jsonb(telemetry), legacy),
            )
            conn.commit()

    def save_ai_review(
        self,
        cohort_id: str,
        resume_id: str,
        uid: str,
        payload: dict[str, Any],
    ) -> str:
        from psycopg.types.json import Jsonb
        import uuid

        review_id = uuid.uuid4().hex[:20]
        legacy = f"{resume_id}/{review_id}"
        with self._pg() as conn:
            ident = self._cohort_user(conn, cohort_id, uid)
            resume = conn.execute(
                "SELECT id FROM resumes WHERE legacy_id = %s AND cohort_id = %s",
                (resume_id, ident["cohort_pk"]),
            ).fetchone()
            if not resume:
                raise ResumeNotFoundError("resume not found")
            conn.execute(
                """INSERT INTO resume_ai_reviews (legacy_id, resume_id, user_id, status, payload, created_at)
                   VALUES (%s,%s,%s,'complete',%s, now())""",
                (legacy, resume[0], ident["user_pk"], Jsonb({**payload, "userId": uid})),
            )
            conn.commit()
        return review_id

    def get_job_requirements(self, key: str) -> list[dict] | None:
        with self._pg() as conn:
            row = conn.execute(
                "SELECT requirements FROM job_requirement_profiles WHERE key = %s", (key,)
            ).fetchone()
        return None if not row else list(row[0] or [])

    def save_job_requirements(self, key: str, requirements: list[dict]) -> None:
        from psycopg.types.json import Jsonb

        with self._pg() as conn:
            conn.execute(
                """INSERT INTO job_requirement_profiles (key, requirements, created_at)
                   VALUES (%s, %s, now())
                   ON CONFLICT (key) DO UPDATE SET requirements = EXCLUDED.requirements""",
                (key, Jsonb(requirements)),
            )
            conn.commit()

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
