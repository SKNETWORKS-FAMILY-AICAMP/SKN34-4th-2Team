"""Explicit paid evaluation of the same batch engine used by local B. No database.

python -m evaluation.section_quality_live --live --label baseline
Artifacts include every extraction, draft and verdict, not a mock quality score.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from app.resume_review_v2.batch import BatchReviewEngine
from app.resume_review_v2.models import ReviewInput, Experience


class RecordedBatch(BatchReviewEngine):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def _batch(self, method, items):
        rows = super()._batch(method, items)
        self.records.append({'stage': method, 'outputs': {
            key: row.model_dump(mode='json') for key, row in rows.items()}})
        return rows


class EphemeralReviewStore:
    """Only this Golden resume exists. No persistent/database implementation."""
    def __init__(self, content):
        self.content = content
        self.response = None

    def get_owned_resume(self, *_):
        return {'content': self.content}

    def claim_review(self, *_):
        return {}

    def review_progress(self, *_):
        pass

    def complete_review(self, *args):
        self.response = args[4]

    def fail_review(self, *_):
        pass


def through_b_http(cases, settings, engine):
    """Real mounted B route and adapter, real model, ephemeral storage only."""
    os.environ.update(DB_HOST='127.0.0.1', RESUME_REVIEW_ENGINE='v2-local')
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from fastapi.testclient import TestClient
    from app import main, resume_apply
    from app.local_resume_site_adapter import LocalReviewService
    content = {'projects': [], 'selfIntroduction': {}}
    for case in cases:
        if case['section'] == 'project':
            content['projects'].append({'id': 'golden-project', 'name': case['title'], 'description': case['text']})
        else:
            key = 'aspiration' if case['section'] == 'future_plan' else 'motivation'
            content['selfIntroduction'][key] = {'body': case['text']}
    store = EphemeralReviewStore(content)
    old_factory = main.build_resume_review_service
    old_overrides = main.app.dependency_overrides.copy()
    old_apply = resume_apply.gateway_dependency
    try:
        from app.local_resume_site import app
        main.build_resume_review_service = lambda: LocalReviewService(settings, store, engine)
        with TestClient(app) as client:
            response = client.post('/resume-review/api/v1/resumes/reviews/proxy', json={
                'uid': 'golden-user', 'cohort_id': 'golden', 'resume_id': 'golden',
                'request_id': 'golden-review', 'review_mode': 'general'})
        response.raise_for_status()
        return response.json()
    finally:
        main.build_resume_review_service = old_factory
        main.app.dependency_overrides = old_overrides
        resume_apply.gateway_dependency = old_apply


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--label', required=True)
    parser.add_argument('--model')
    parser.add_argument('--rough', action='store_true', help='Same facts, deliberately repetitive/list-like source wording')
    parser.add_argument('--via-http', action='store_true', help='Exercise the mounted B adapter with ephemeral storage')
    args = parser.parse_args()
    if not args.live:
        parser.error('--live explicitly enables paid model calls')
    if not args.label.replace('-', '').replace('_', '').isalnum():
        parser.error('label must contain letters, numbers, hyphens or underscores')
    # Load ONLY the API key; never import the Django/database configuration.
    root = Path(__file__).resolve().parents[2]
    for line in (root / '.env').read_text(encoding='utf-8').splitlines():
        key, sep, value = line.strip().partition('=')
        if sep and key == 'OPENAI_API_KEY' and not os.environ.get(key):
            os.environ[key] = value.strip().strip('\"\'')
    os.environ['LANGCHAIN_TRACING_V2'] = 'false'
    os.environ['LANGSMITH_TRACING'] = 'false'
    from app.config import get_settings
    settings = get_settings()
    cases = json.loads((Path(__file__).parent / 'fixtures/section_quality_golden.json').read_text(encoding='utf-8'))['cases']
    if args.rough:
        for case in cases:
            # Repetition/list formatting introduces no new applicant information.
            sentences = case['text'].split('. ')
            case['text'] = '\n'.join('- ' + s for s in sentences) + '\n' + sentences[0] + '.'
    requests = []
    for case in cases:
        section = case['section']
        path = {'future_plan': 'selfIntroduction.aspiration.body',
                'motivation': 'selfIntroduction.motivation.body',
                'project': 'projects[0].description'}[section]
        requests.append(ReviewInput(experience=Experience(
            experience_id='projects:golden-project' if section == 'project' else path.removesuffix('.body'),
            kind='project' if section == 'project' else 'other',
            title=case.get('title', section), current_text=case['text'],
            field_path=path, content_hash='golden-v1')))
    engine = RecordedBatch(args.model or settings.openai_model, settings.openai_reasoning_effort,
                           on_progress=lambda s: print(json.dumps({'stages': s['stages']}, ensure_ascii=True), flush=True))
    output = Path(__file__).parent / 'runs' / ('section_' + args.label + '.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SystemExit('Choose a new label; existing evidence is never overwritten.')
    from app.resume_review_v2.policy import POLICY_VERSION
    report = {'cases': cases, 'model': engine.model_name, 'policy_version': POLICY_VERSION,
              'variant': 'repetitive' if args.rough else 'clean'}
    try:
        if args.via_http:
            report['http_response'] = through_b_http(cases, settings, engine)
            report['results'] = report['http_response']['telemetry']['v2_results']
        else:
            results = engine.run_many(requests)
            report['results'] = [r.model_dump(mode='json') for r in results]
    finally:
        report.update(stages=engine.records, usage=engine.usage.model_dump())
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(str(output), flush=True)


if __name__ == '__main__':
    main()
