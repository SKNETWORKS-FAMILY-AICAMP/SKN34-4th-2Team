from celery import shared_task

from lms.publish import publish_scheduled_notices


@shared_task
def publish_due_notices():
    return publish_scheduled_notices()


@shared_task
def reindex_all_notices():
    from lms.management.commands.reindex_notices import run_reindex

    return run_reindex()


@shared_task
def sync_study_sources():
    """기수에 연결한 GitHub 조직·계정에서 새 수업 저장소를 찾아 공부방에 올린다"""
    from lms.study_source_service import sync_all

    return sync_all()


@shared_task
def run_practice_auto():
    """매일 18:30 — 공개된 수업 저장소마다 그날 새로 올라온 내용으로 복습 문제를 낸다"""
    from lms.practice_auto import run_daily

    return run_daily()


@shared_task
def sync_qual_exams():
    """매일 새벽 — 공공데이터포털 국가자격 시험 일정을 system_cache 에 받아 둔다"""
    from lms.external_feeds import sync_qual_exams as sync

    return sync()
