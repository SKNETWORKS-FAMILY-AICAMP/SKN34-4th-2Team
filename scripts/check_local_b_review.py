"""One explicitly invoked local B review through the normal Django API."""
import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lms_api'))
from local_resume_site import configure
configure()
import django
django.setup()
from django.test import Client
from lms.jwt_auth import issue_tokens, load_lms_user

if '--live-once' not in sys.argv:
    raise SystemExit('Explicit --live-once required; this performs paid LLM calls.')
client = Client(HTTP_AUTHORIZATION='Bearer ' + issue_tokens(load_lms_user('local-resume-e2e'))['access'])
payload = dict(resumeId='local-ab-source-resume-33', selectedJobId='SARAMIN-55149877',
    tailoredResumeId='tailored_125f5e7e52a26b6357c4d7e6', requestId='batch_smoke_' + uuid.uuid4().hex)
context = client.post('/api/resume-review/context', json.dumps(payload), content_type='application/json')
if context.status_code != 200:
    raise SystemExit(f'Context failed: {context.status_code}')
snapshot = context.json()
payload.update(expectedInputHash=snapshot['input_hash'], expectedJobHash=snapshot['job_source']['snapshot_hash'])
started = time.monotonic()
response = client.post('/api/resume-review', json.dumps(payload), content_type='application/json')
body = response.json()
print(json.dumps({'status': response.status_code, 'seconds': round(time.monotonic()-started, 2),
    'request_id': payload['requestId'], 'telemetry': {k: v for k, v in body.get('telemetry', {}).items() if k != 'v2_results'},
    'revisions': [{'field': r['field_path'], 'status': r['status'], 'issues': r.get('validation_issues', [])}
                  for r in body.get('sentence_reviews', [])], 'error': body.get('detail')}, ensure_ascii=True))
