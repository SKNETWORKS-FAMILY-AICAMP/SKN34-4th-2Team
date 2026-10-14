"""Run the unchanged LMS UI/API against the isolated B database only."""
import os
import sys
from pathlib import Path


def configure():
    host = os.environ.get('LOCAL_DB_HOST', '127.0.0.1')
    if host not in ('127.0.0.1', 'localhost'):
        raise RuntimeError('B site requires a loopback PostgreSQL host; RDS is prohibited')
    values = {
        'DB_HOST': host, 'DB_PORT': os.environ.get('LOCAL_DB_PORT', '55439'),
        'DB_NAME': os.environ.get('LOCAL_DB_NAME', 'resume_review_v2_test'),
        'DB_USER': os.environ.get('LOCAL_DB_USER', 'resume_v2_test_admin'),
        'DB_PASSWORD': os.environ.get('LOCAL_DB_PASSWORD', 'local-trust-only'),
        'DB_SSLMODE': 'disable', 'RESUME_REVIEW_ENGINE': 'v2-local',
        'DATABASE_URL': '', 'JOBS_DATABASE_URL': '',
        'LMS_INLINE_PUBLISH': '0', 'DJANGO_SETTINGS_MODULE': 'local_resume_site_settings',
        'LANGCHAIN_TRACING_V2': 'false', 'LANGSMITH_TRACING': 'false',
        'JOBS_URL': 'http://127.0.0.1:8003', 'RESUME_REVIEW_URL': 'http://127.0.0.1:8003',
        'CHATBOT_URL': 'http://127.0.0.1:8003', 'STUDY_NOTES_URL': 'http://127.0.0.1:8003',
    }
    os.environ.update(values)
    # Only the OpenAI key is inherited from .env; never inherit cloud DB addresses.
    env = Path(__file__).resolve().parent.parent / '.env'
    if env.exists() and not os.environ.get('OPENAI_API_KEY'):
        for raw in env.read_text(encoding='utf-8').splitlines():
            key, separator, value = raw.strip().partition('=')
            if separator and key.strip() == 'OPENAI_API_KEY':
                os.environ['OPENAI_API_KEY'] = value.strip().strip('"\'')
    print(f"B SITE | LOCAL DB {host}:{values['DB_PORT']}/{values['DB_NAME']} | engine v2-local")


if __name__ == '__main__':
    configure()
    if len(sys.argv) > 1 and sys.argv[1] == 'ai':
        # AI bootstrap shares exactly the same locked local DB settings.
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'cover_letter_rag'))
        import uvicorn
        uvicorn.run('app.local_resume_site:app', host='127.0.0.1', port=8003)
    else:
        from django.core.management import execute_from_command_line
        execute_from_command_line(sys.argv)
