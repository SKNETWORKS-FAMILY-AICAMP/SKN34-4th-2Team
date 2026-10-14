"""Three fictional sets, single sampling; no Django/DB import or final Writer.

Results checkpoint before each call prevents accidental repeated spending.
Run: python -m evaluation.application_planning_live --live --env-file ../.env
"""
import argparse
import json
import os
import re
import time
from pathlib import Path

from app.application_planning.engine import (StructuredPlanningClient, parse_constraints, validate_analysis,
    validate_plan, ANALYZER_PROMPT, PLANNER_PROMPT)
from app.application_planning.models import Question, PlanningExperience, PlanningInput, AnswerDocument

HERE = Path(__file__).resolve().parent
CASES = HERE / 'application_planning_cases.json'
RESULTS = HERE / 'application_planning_live_results'


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


class RecordingModel:
    """Transparent include_raw wrapper around the current injected model adapter."""
    def __init__(self, model, record, path):
        self.model, self.record, self.path = model, record, path

    def with_structured_output(self, schema):
        inner = self.model.with_structured_output(schema, include_raw=True)
        outer = self
        class Call:
            def invoke(self, messages):
                stage = 'analyzer' if schema.__name__ == 'AnalysisBatch' else 'planner'
                item = dict(stage=stage, status='started', input_tokens=None, output_tokens=None, latency_ms=None)
                outer.record['calls'].append(item)
                save(outer.path, outer.record)
                print(f"{outer.record['set_id']} {stage}: started", flush=True)
                start = time.monotonic()
                try:
                    response = inner.invoke(messages)
                    raw = response['raw']
                    usage = raw.usage_metadata or {}
                    item.update(status='returned', input_tokens=usage.get('input_tokens'),
                        output_tokens=usage.get('output_tokens'), latency_ms=round((time.monotonic()-start)*1000),
                        token_details=usage, response_id=raw.id, provider_model=raw.response_metadata.get('model_name'))
                    parsed = response.get('parsed')
                    outer.record[f'raw_{stage}_output'] = parsed.model_dump(mode='json') if parsed else None
                    if response.get('parsing_error') or parsed is None:
                        item['status'] = 'parse_failure'
                        outer.record[f'{stage}_raw_content_on_parse_failure'] = raw.content
                        raise ValueError('Structured output parse failure')
                    save(outer.path, outer.record)
                    print(f"{outer.record['set_id']} {stage}: returned ({item['latency_ms']} ms)", flush=True)
                    return parsed
                except Exception as exc:
                    item.update(status='failed' if item['status']=='started' else item['status'],
                                latency_ms=round((time.monotonic()-start)*1000), error_type=type(exc).__name__)
                    if hasattr(exc, 'status_code'): item['http_status'] = exc.status_code
                    # Schema errors are useful, but never persist API-key/auth text.
                    if getattr(exc, 'status_code', None) == 400:
                        item['error_message'] = re.sub(r'sk-[\w-]+', '[REDACTED]', str(exc))
                    save(outer.path, outer.record)
                    raise
        return Call()


def narrative_warnings(data, plan):
    """Candidate warnings only, not a semantic fact validator or quality score."""
    facts = {f.evidence_id:f.normalized_fact for e in data.experiences for f in e.evidence}
    issues=[]
    pattern=r'\d+(?:\.\d+)?\s*(?:만\s*건|%|배|초|명|건|원)'
    for row in plan.assignments:
        approved=' '.join(facts[eid] for eid in row.core_evidence_ids+row.supporting_evidence_ids+row.result_evidence_ids)
        text=' '.join([row.story_focus,row.rationale]+[g.reason+' '+g.question_proposal for g in row.missing_information])
        novel=set(re.findall(pattern,text))-set(re.findall(pattern,approved))
        if novel: issues.append(dict(question_id=row.question_id,warning='unsupported_numeric_claim_candidate',values=sorted(novel)))
        if re.search(r'(속도|효율|만족도|비용|응답\s*시간).{0,15}(크게|절반|높였|향상|감소|개선)',text):
            issues.append(dict(question_id=row.question_id,warning='outcome_wording_needs_human_review'))
    return issues


def render(record):
    raw_plan = record.get('raw_planner_output') or {}
    facts = {f['evidence_id']: f for e in record['fixture']['experiences'] for f in e['evidence']}
    assignments = raw_plan.get('assignments', [])
    sections=[('Questions',record['fixture']['questions']),
        ('Question Analyzer Output',record.get('raw_analyzer_output')),
        ('Available Experiences',record['fixture']['experiences']),
        ('Available Evidence',[f for e in record['fixture']['experiences'] for f in e['evidence']]),
        ('Applicant Intent',dict(confirmed=record['fixture']['applicant_intent'],unconfirmed=record['fixture']['unconfirmed_intent'])),
        ('Target Context',record['fixture']['target_context']),
        ('Raw Application Plan',record.get('raw_planner_output')),
        ('Experience Scope',[dict(question_id=a['question_id'], primary_experience_ids=a['primary_experience_ids']) for a in assignments]),
        ('Core Evidence',[dict(question_id=a['question_id'], evidence=[facts.get(eid, {'unknown_id': eid}) for eid in a['core_evidence_ids']]) for a in assignments]),
        ('Supporting Evidence',[dict(question_id=a['question_id'], evidence=[facts.get(eid, {'unknown_id': eid}) for eid in a['supporting_evidence_ids']]) for a in assignments]),
        ('Result Evidence',[dict(question_id=a['question_id'], evidence=[facts.get(eid, {'unknown_id': eid}) for eid in a['result_evidence_ids']]) for a in assignments]),
        ('Gap Type',[dict(question_id=a['question_id'], gaps=a['missing_information']) for a in assignments]),
        ('Validated Application Plan / Proposed Question',record.get('validated_result')),
        ('Duplicate Story Warnings',(record.get('validated_result') or {}).get('duplicate_story_warnings')),
        ('Deterministic Validation',record.get('validation')),
        ('Original Live Validation (offline recheck only)',record.get('original_validation')),
        ('LLM Calls / Input Tokens / Output Tokens / Latency',record['calls'])]
    lines=[f"# Set {record['set_id']} — attempt {record['attempt']}",f"Model: {record['model']} / effort: {record['reasoning_effort']}"]
    for title,value in sections:
        lines.extend(['',f'[{title}]','```json',json.dumps(value,ensure_ascii=False,indent=2),'```'])
    lines.extend(['','## Human Review','',
        'Question Analysis (GOOD | NEEDS_FIX):','',
        'Experience Assignment (GOOD | NEEDS_FIX):','',
        'Result Semantics (GOOD | NEEDS_FIX):','',
        'Gap Classification (GOOD | NEEDS_FIX):','',
        'Evidence Selection (GOOD | NEEDS_FIX):','',
        'Gap Decision (GOOD | NEEDS_FIX):','',
        'Would this plan give a good Writer enough material? (YES | NO):','',
        'Reviewer Notes:',''])
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--env-file',type=Path,required=True)
    parser.add_argument('--sets',default='A,B,C')
    parser.add_argument('--attempt',type=int,choices=[1,2],default=1)
    parser.add_argument('--retry-reason')
    parser.add_argument('--phase', choices=['4a5', '4a6', '4a7'], default='4a5')
    parser.add_argument('--a-reviewed-pass', action='store_true',
        help='Phase4A.7 only: reviewer inspected A semantic output before requesting B/C')
    args=parser.parse_args()
    selected=args.sets.split(',')
    if len(set(selected))!=len(selected) or set(selected)-{'A','B','C'}: parser.error('Only unique A/B/C sets allowed')
    if not args.live: parser.error('Use --live explicitly; this sends fictional fixtures to OpenAI')
    if args.attempt==2 and (len(selected)!=1 or not args.retry_reason): parser.error('One classified set per retry')
    if args.phase in {'4a6','4a7'} and args.attempt==2 and selected!=['A']:
        parser.error('Phase4A.6 permits only one A retry; B/C each once')
    results = RESULTS if args.phase=='4a5' else HERE / f'application_planning_phase{args.phase}_results'
    results.mkdir(exist_ok=True)
    if args.phase in {'4a6','4a7'} and any(sid in {'B','C'} for sid in selected):
        checkpoints = [json.loads(p.read_text(encoding='utf-8')) for p in results.glob('A-attempt*.json')]
        if not any(r.get('validation', {}).get('planner')=='PASS' for r in checkpoints):
            parser.error('A must pass and be inspected before B/C regression is requested')
        if args.phase=='4a7':
            if not args.a_reviewed_pass: parser.error('Inspect A semantics then use --a-reviewed-pass for B/C')
            latest=max(checkpoints,key=lambda r:r['attempt'])
            q1=(latest.get('validated_result') or {}).get('plan',{}).get('assignments',[{}])[0]
            gaps=q1.get('missing_information',[])
            if (any(g['key']=='preparation_effort' for g in gaps) or not any(
                g['key']=='company_motivation' and g['category']=='applicant_intent' for g in gaps)):
                parser.error('A Q1 required semantic gate failed')
    from dotenv import dotenv_values
    env=dotenv_values(args.env_file)
    model=env.get('RESUME_V2_MODEL') or env.get('OPENAI_MODEL')
    effort=env.get('OPENAI_REASONING_EFFORT') or 'medium'
    if args.phase in {'4a6','4a7'}:
        baseline=json.loads((RESULTS/'A-attempt2.json').read_text(encoding='utf-8'))
        model,effort=baseline['model'],baseline['reasoning_effort']
    if not env.get('OPENAI_API_KEY') or not model: parser.error('Model/API key missing')
    os.environ['LANGCHAIN_TRACING_V2']='false'
    os.environ['LANGSMITH_TRACING']='false'
    from langchain_openai import ChatOpenAI
    chat=ChatOpenAI(model=model,api_key=env['OPENAI_API_KEY'],reasoning_effort=effort,
        use_responses_api=True,max_retries=0,timeout=180)
    cases=json.loads(CASES.read_text(encoding='utf-8'))
    for case in cases:
        sid=case['set_id']
        if sid not in selected: continue
        path=results/f'{sid}-attempt{args.attempt}.json'
        if path.exists():
            print(f'{sid}: existing checkpoint; skipped (no new calls)',flush=True)
            continue
        if args.attempt==2 and not (results/f'{sid}-attempt1.json').exists(): parser.error('Retry needs original checkpoint')
        record=dict(set_id=sid,attempt=args.attempt,phase=args.phase,retry_reason=args.retry_reason,
            model=model,reasoning_effort=effort,fixture=case,calls=[],validation={},
            system_prompts=dict(analyzer=ANALYZER_PROMPT,planner=PLANNER_PROMPT))
        if args.phase=='4a7':
            # Analyzer is out of scope: reuse identical validated analysis, not another paid sample.
            source=(HERE/'application_planning_phase4a6_results/A-attempt2.json' if sid=='A'
                    else RESULTS/f'{sid}-attempt1.json')
            previous=json.loads(source.read_text(encoding='utf-8'))
            if previous['fixture'] != case: raise ValueError('Phase4A.7 fixture must match previous run exactly')
            record['raw_analyzer_output']=previous['raw_analyzer_output']
            record['analyzer_reused_from']=str(source.relative_to(HERE))
        client=StructuredPlanningClient(RecordingModel(chat,record,path))
        stage='analyzer'
        start=time.monotonic()
        try:
            qs=[Question(question_id=f'{sid}-Q{i+1}',raw_text=text,constraints=parse_constraints(text)) for i,text in enumerate(case['questions'])]
            analyzed=validate_analysis(qs, record['raw_analyzer_output'] if args.phase=='4a7'
                else client.analyze([q.model_copy(deep=True) for q in qs],case['target_context']))
            record['validation']['analyzer']='PASS'
            data=PlanningInput(application_id=f'fictional-{sid}',questions=analyzed.questions,
                experiences=[PlanningExperience.model_validate(e) for e in case['experiences']],
                target_context=case['target_context'],answers=[AnswerDocument.model_validate(a) for a in case['answers']])
            stage='planner'
            plan=client.plan(data.model_copy(deep=True))
            result=validate_plan(data,plan)
            record['validated_result']=result.model_dump(mode='json')
            record['validation'].update(planner='PASS',narrative_warnings=narrative_warnings(data,plan),
                semantic_quality='HUMAN_REVIEW_REQUIRED')
        except Exception as exc:
            record['validation'].update(failed_stage=stage,error_type=type(exc).__name__)
            if isinstance(exc,ValueError): record['validation']['contract_error']=str(exc)
            print(f'{sid}: {stage} failed ({type(exc).__name__}); no automatic retry',flush=True)
        record['total_latency_ms']=round((time.monotonic()-start)*1000)
        save(path,record)
        path.with_suffix('.md').write_text(render(record),encoding='utf-8')
    records=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(results.glob('*-attempt*.json'))]
    calls=[c for r in records for c in r['calls']]
    totals=dict(attempts=len(records),calls=len(calls),input_tokens=sum(c.get('input_tokens') or 0 for c in calls),
        output_tokens=sum(c.get('output_tokens') or 0 for c in calls),
        latency_ms=sum(c.get('latency_ms') or 0 for c in calls),
        usage_missing_calls=sum(c.get('input_tokens') is None for c in calls))
    save(results/'usage-summary.json',dict(totals=totals,sets=[dict(set_id=r['set_id'],attempt=r['attempt'],
        calls=len(r['calls']),input_tokens=sum(c.get('input_tokens') or 0 for c in r['calls']),
        output_tokens=sum(c.get('output_tokens') or 0 for c in r['calls']),
        latency_ms=r['total_latency_ms'],validation=r['validation']) for r in records]))
    print(json.dumps(totals),flush=True)


if __name__=='__main__': main()
