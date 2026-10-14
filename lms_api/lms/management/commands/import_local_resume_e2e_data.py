import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from lms.local_resume_e2e_data import import_bundle


class Command(BaseCommand):
    help = 'Approved DOCX/TXT/site-content JSON registration only; no analysis'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('--approved-data', action='store_true')
        parser.add_argument('--title')
        parser.add_argument('--source-id')

    def handle(self, *args, **options):
        try:
            path = Path(options['path'])
            if path.suffix.lower() in {'.docx', '.txt'}:
                from lms.local_resume_document import document_bundle
                if not options['title'] or not options['source_id']:
                    raise ValueError('Document registration requires --title and --source-id')
                bundle = document_bundle(path, title=options['title'], source_id=options['source_id'])
            else:
                bundle = json.loads(path.read_text(encoding='utf-8-sig'))
            resume = import_bundle(bundle, approved=options['approved_data'])
        except (ValueError, RuntimeError, KeyError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write('Imported/reused approved local source copy: '+str(resume.pk))
