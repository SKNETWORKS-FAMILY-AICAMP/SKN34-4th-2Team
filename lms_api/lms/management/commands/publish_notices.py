from django.core.management.base import BaseCommand

from lms.publish import publish_scheduled_notices


class Command(BaseCommand):
    help = "기한이 된 예약 공지를 notices 로 발행한다. --ids 로 즉시 발행."

    def add_arguments(self, parser):
        parser.add_argument("--ids", default="", help="쉼표로 구분한 scheduled_notices.id")

    def handle(self, *args, **options):
        raw = str(options.get("ids") or "").strip()
        ids = [part.strip() for part in raw.split(",") if part.strip()] or None
        count = publish_scheduled_notices(ids=ids)
        self.stdout.write(f"published={count}")
