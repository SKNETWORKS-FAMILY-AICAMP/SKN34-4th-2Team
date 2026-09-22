"""권한 헬퍼. DRF Permission 클래스 없음 — Ninja 라우트에서 직접 사용."""


def can_access_cohort(user, cohort_id: int) -> bool:
    if not user or not user.get("is_active"):
        return False
    if user.get("role") == "admin":
        return True
    return user.get("cohort_id") == cohort_id


def is_owner(user, firebase_uid: str) -> bool:
    return bool(user and user.get("firebase_uid") == firebase_uid)
