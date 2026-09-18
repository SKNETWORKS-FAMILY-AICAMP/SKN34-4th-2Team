"""운영 백엔드와 같은 Firebase 프로젝트를 읽는 lab 전용 어댑터."""

from __future__ import annotations

import os
from typing import Any, Callable

from firebase_admin import auth, firestore, storage

from chatbot.api import _firebase_app
from chatbot.firebase_student_context import load_student_context


StudentLoader = Callable[[str, str, list[str], str], dict[str, Any]]


def create_firebase_student_loader(identifier: str) -> tuple[StudentLoader, str, str]:
    """UID 또는 이메일로 학생 한 명을 고정하고 운영 loader를 재사용한다."""
    identifier = identifier.strip()
    if not identifier:
        raise ValueError("실제 Firebase 모드에는 학생 UID 또는 이메일이 필요합니다")

    app = _firebase_app()
    user = (
        auth.get_user_by_email(identifier, app=app)
        if "@" in identifier
        else auth.get_user(identifier, app=app)
    )
    db = firestore.client(app=app)
    profile = db.collection("users").document(user.uid).get().to_dict() or {}
    if profile.get("role") != "student" or profile.get("isActive") is not True:
        raise ValueError("활성화된 학생 계정만 실험에 사용할 수 있습니다")
    cohort = str(profile.get("cohortId") or "").strip()
    if not cohort:
        raise ValueError("선택한 학생에게 기수 정보가 없습니다")

    project_id = app.project_id
    bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET") or (
        f"{project_id}.firebasestorage.app" if project_id else None
    )
    bucket = storage.bucket(bucket_name, app=app)

    def loader(uid: str, requested_cohort: str, scopes: list[str], query: str) -> dict[str, Any]:
        if uid != user.uid or requested_cohort != cohort:
            raise ValueError("선택한 학생 범위를 벗어난 Firebase 조회를 차단했습니다")
        return load_student_context(
            db=db, bucket=bucket, uid=user.uid, cohort=cohort, scopes=scopes, query=query,
        )

    return loader, user.uid, cohort
