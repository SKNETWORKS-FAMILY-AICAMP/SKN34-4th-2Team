from django.db import transaction

from lms import notice_vectors


def sync_notice_vector(cohort_code: str, notice_id: int, data: dict, previous_chunk_count: int = 0):
    """저장/삭제 후 on_commit 에서만 호출. 뷰에 직접 걸지 않는다."""
    if data is None:
        notice_vectors.delete_notice_vectors(cohort_code, notice_id, previous_chunk_count)
        return 0
    old = int(previous_chunk_count or 0)
    if old:
        notice_vectors.delete_notice_vectors(cohort_code, notice_id, old)
    return notice_vectors.upsert_notice_vectors(cohort_code, notice_id, data)


def schedule_notice_vector(*, cohort_code: str, notice_id: int, data: dict | None, previous_chunk_count: int = 0):
    transaction.on_commit(
        lambda: sync_notice_vector(cohort_code, notice_id, data, previous_chunk_count)
    )
