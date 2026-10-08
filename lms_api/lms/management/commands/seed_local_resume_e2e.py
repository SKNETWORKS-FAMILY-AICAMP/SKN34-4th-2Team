from django.core.management.base import BaseCommand
from lms.local_resume_e2e_fixture import seed


class Command(BaseCommand):
    help = 'Idempotent fictional LOCAL E2E fixtures only'

    def handle(self, *args, **options):
        user, base, role = seed()
        self.stdout.write(f'LOCAL seed ready: user={user.pk} base={base.pk} role={role.pk}')
