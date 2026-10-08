"""Local entry point. Unlike manage.py, never loads repository .env."""
import os
import sys

if any(arg == '--settings' or arg.startswith('--settings=') for arg in sys.argv[1:]):
    raise SystemExit('Local E2E refuses --settings overrides; production settings are prohibited')

os.environ['DJANGO_SETTINGS_MODULE'] = 'local_resume_e2e_settings'
os.environ['LMS_INLINE_PUBLISH'] = '0'
os.environ['LANGSMITH_TRACING'] = 'false'
os.environ['LANGCHAIN_TRACING_V2'] = 'false'
from django.core.management import execute_from_command_line
execute_from_command_line(sys.argv)
