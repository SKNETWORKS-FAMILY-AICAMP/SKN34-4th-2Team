from celery import shared_task

from lms.publish import publish_scheduled_notices


@shared_task
def publish_due_notices():
    return publish_scheduled_notices()


@shared_task
def reindex_all_notices():
    from lms.management.commands.reindex_notices import run_reindex

    return run_reindex()
