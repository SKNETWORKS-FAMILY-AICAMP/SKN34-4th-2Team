from django.core.management.base import BaseCommand, CommandError

from lms.external_feeds import FeedError, sync_qual_exams


class Command(BaseCommand):
    help = "공공데이터포털 국가자격 시험 일정을 system_cache 에 받아 둔다. 기본은 올해와 내년."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, action="append", help="받을 연도(여러 번 줄 수 있다)")

    def handle(self, *args, **options):
        try:
            counts = sync_qual_exams(options.get("year") or None)
        except FeedError as exc:
            raise CommandError(exc.detail) from None
        for year, n in counts.items():
            self.stdout.write(f"qualExamSchedules_{year}: {n}건")
