from django.db import connection, transaction

from lms import notice_vectors

SCHEDULED_ATTENDANCE_TITLE = "[출결] 오늘 예외 출결 제출"


def sync_notice_vector(cohort_code: str, notice_id: int, data: dict, previous_chunk_count: int = 0):
    """저장/삭제 후 on_commit 에서만 호출. 뷰에 직접 걸지 않는다."""
    if data is None:
        notice_vectors.delete_notice_vectors(cohort_code, notice_id, previous_chunk_count)
        return 0
    old = int(previous_chunk_count or 0)
    scheduled_attendance = False
    if str(data.get("title") or "").strip() == SCHEDULED_ATTENDANCE_TITLE:
        with connection.cursor() as cursor:
            cursor.execute("SELECT source FROM notices WHERE id = %s", [notice_id])
            scheduled_attendance = (cursor.fetchone() or [None])[0] == "scheduled"
    chunk_count = 0 if scheduled_attendance else notice_vectors.upsert_notice_vectors(cohort_code, notice_id, data)
    if old > chunk_count:
        notice_vectors.delete_notice_vectors(cohort_code, notice_id, old, start=chunk_count)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE notices SET vector_chunk_count = %s WHERE id = %s",
            [chunk_count, notice_id],
        )
    return chunk_count


def schedule_notice_vector(*, cohort_code: str, notice_id: int, data: dict | None, previous_chunk_count: int = 0):
    transaction.on_commit(
        lambda: sync_notice_vector(cohort_code, notice_id, data, previous_chunk_count)
    )
