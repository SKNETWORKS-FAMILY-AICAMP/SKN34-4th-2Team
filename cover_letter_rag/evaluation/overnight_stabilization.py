"""Explicit small live replay of saved B Writer/Verifier inputs, read-only DB.

No Analyst rerun, recommendation, whole-resume review or persistent review write.
Every request/response is recorded; a used label cannot be repeated accidentally.
"""
import argparse
import json
import os
from pathlib import Path

import psycopg

from app.resume_review_v2.engine import ReviewEngineV2
from app.resume_review_v2.llm import LangChainReviewLLM
from app.resume_review_v2.models import (ReviewInput, Experience, Evidence,
    SourceDocument, SectionSemanticProfile, RevisionPlan, Usage)
from app.resume_review_v2.validation import _exact_source_quote


CASES = {
    'verifier': [(20, 'projects:prj1790844850071sxa'),
                 (23, 'projects:prj1790844850071sxa')],
    'writer': [(21, 'projects:prj17908447284945fx'),
               (22, 'projects:prj1790844823849w4d')],
}


class RecordedLLM(LangChainReviewLLM):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def _call(self, system, payload, schema):
        row = dict(stage=schema.__name__, system=system, input=payload)
        self.records.append(row)
        try:
            parsed, usage = super()._call(system, payload, schema)
            row.update(output=parsed.model_dump(mode='json'), usage=usage.model_dump())
            return parsed, usage
        except Exception as exc:
            row['error'] = type(exc).__name__
            raise


def load_cases(stage):
    # Hard-bound to the historical local cluster, never project DB environment.
    with psycopg.connect('host=127.0.0.1 port=55439 dbname=resume_review_v2_test '
                         'user=resume_v2_test_admin',
                         options='-c default_transaction_read_only=on') as db:
        cases = []
        for review_id, owner in CASES[stage]:
            with db.cursor() as cur:
                cur.execute('SELECT r.telemetry,s.content,r.resume_id FROM resume_ai_reviews r '
                            'JOIN resumes s ON s.id=r.resume_id WHERE r.id=%s', (review_id,))
                telemetry, content, resume_id = cur.fetchone()
                cur.execute('SELECT id,telemetry FROM resume_ai_reviews '
                            'WHERE resume_id=%s AND id<=%s ORDER BY id', (resume_id, review_id))
                history = cur.fetchall()
            record = next(r for r in telemetry['v2_results']
                          if r['experience']['experience_id'] == owner)
            exp = Experience.model_validate(record['experience'])
            item = next(p for p in content['projects'] if owner.endswith(':' + p['id']))
            sources = [SourceDocument(source_id=owner + ':' + key,
                       text=value if isinstance(value, str) else ', '.join(v for v in value if isinstance(v, str)))
                       for key, value in item.items() if key in
                       ('name', 'title', 'role', 'techStack', 'technologies') and value]
            facts = [Evidence.model_validate(e) for e in record['evidence_state']]
            source_map = {s.source_id: s.text for s in sources}
            source_map[owner] = exp.current_text
            # Do not infer historical provenance from a normalized paraphrase.
            for fact in facts:
                source = record['answer'] if fact.source_type == 'user_answer' else source_map.get(fact.source_id, '')
                if (fact.source_type == 'resume_text' and fact.source_id == owner
                        and not _exact_source_quote(source, fact.evidence_quote)):
                    # Applying an earlier revision changes current_text; recover
                    # the immutable source from an actual earlier review, not from
                    # a paraphrase or from an invented document. Eval-only alias
                    # explicitly records that historical owning field and review.
                    for rid, prior in history:
                        original = next((r['experience']['current_text'] for r in
                            (prior or {}).get('v2_results', []) if
                            r['experience']['experience_id'] == owner), '')
                        if _exact_source_quote(original, fact.evidence_quote):
                            source = original
                            fact.source_id = f'{owner}:historical_description:review-{rid}'
                            sources.append(SourceDocument(source_id=fact.source_id, text=source))
                            break
                if not _exact_source_quote(source, fact.evidence_quote):
                    raise ValueError(f'Historical source not available: {fact.evidence_id}')
            req = ReviewInput(experience=exp, question=record['question'],
                answer=record['answer'], answer_source_id='historical-replay' if record['answer'] else '',
                resume_sources=sources,
                section_profile=SectionSemanticProfile.model_validate(record['section_profile']))
            cases.append((review_id, record, req, facts))
    return cases


def replay(record, request, facts, llm):
    """Reuse saved extraction/selection; real same core validation/rewrite path."""
    plan = RevisionPlan.model_validate(record['plan'])
    pool = {e.evidence_id: e for e in facts}
    approved = [pool[eid] for eid in dict.fromkeys(
        plan.core_evidence_ids + plan.supporting_evidence_ids + plan.preserved_evidence_ids)]
    engine = ReviewEngineV2(llm)
    usage = Usage()
    writer, verdict = engine._draft_and_validate(request, plan, pool, approved, usage)
    attempts = [dict(writer=writer.model_dump(mode='json'), validation=verdict.model_dump(mode='json'))]
    if verdict.status == 'REWRITE':
        previous = attempts[-1]
        writer, added = llm.write(request, plan, approved, verdict.all_issues, writer.suggested_text)
        usage.calls += added.calls
        usage.input_tokens += added.input_tokens
        usage.output_tokens += added.output_tokens
        usage.latency_ms += added.latency_ms
        verdict = engine._validate(request, writer, plan, pool, approved, usage, previous)
        attempts.append(dict(writer=writer.model_dump(mode='json'), validation=verdict.model_dump(mode='json')))
    if verdict.status == 'REWRITE':
        verdict.status = 'REJECTED'
    return dict(attempts=attempts, final_text=writer.suggested_text,
                validation=verdict.model_dump(mode='json'), usage=usage.model_dump())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--stage', choices=CASES, required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--review', type=int, help='Restrict to one failed case for a justified recheck')
    args = parser.parse_args()
    if not args.live or not args.label.replace('_', '').replace('-', '').isalnum():
        parser.error('Explicit --live and a safe unique label required')
    output = Path(__file__).parent / 'runs' / ('overnight_' + args.label + '.json')
    if output.exists():
        raise SystemExit('Existing live report: do not repeat or overwrite')
    cases = load_cases(args.stage)  # All sources checked before spending API tokens.
    if args.review is not None:
        cases = [c for c in cases if c[0] == args.review]
        if not cases:
            parser.error('Review must belong to the specified stage')
    root = Path(__file__).resolve().parents[2]
    for line in (root / '.env').read_text(encoding='utf-8').splitlines():
        key, sep, value = line.strip().partition('=')
        if sep and key == 'OPENAI_API_KEY' and not os.environ.get(key):
            os.environ[key] = value.strip().strip('\"\'')
    os.environ.update(LANGCHAIN_TRACING_V2='false', LANGSMITH_TRACING='false')
    from app.config import get_settings
    settings = get_settings()
    report = dict(stage=args.stage, cases=[], model=settings.openai_model,
                  scope='Saved extraction/selection, real single-Experience Writer/Verifier; no Analyst call')
    output.parent.mkdir(parents=True, exist_ok=True)
    for review_id, record, req, facts in cases:
        llm = RecordedLLM(settings.openai_model, settings.openai_reasoning_effort)
        row = dict(review_id=review_id, experience=req.experience.title,
                   request=req.model_dump(mode='json'), before=record['candidate'],
                   evidence=[e.model_dump(mode='json') for e in facts],
                   human_judgement='', reason='')
        report['cases'].append(row)
        try:
            row['result'] = replay(record, req, facts, llm)
        except Exception as exc:
            row['error'] = type(exc).__name__
        finally:
            row.update(calls=llm.records, usage=llm.recorded_usage.model_dump(),
                       attempted_calls=llm.attempted_calls)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(dict(review=review_id, status=row.get('result', {}).get('validation', {}),
                       error=row.get('error'), usage=row['usage']), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
