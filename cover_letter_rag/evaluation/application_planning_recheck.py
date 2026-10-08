"""Revalidate saved outputs with current contracts; zero API/DB calls."""
import json
from .application_planning_live import RESULTS, save, render, narrative_warnings
from app.application_planning.engine import parse_constraints, validate_analysis, validate_plan
from app.application_planning.models import Question, PlanningInput, PlanningExperience, AnswerDocument


def reference_diagnostics(data, raw):
    """Report independent violations, without repairing/resampling the output."""
    facts={f.evidence_id:f for e in data.experiences for f in e.evidence}
    errors=[]
    for row in raw['assignments']:
        for key in ('core_evidence_ids','supporting_evidence_ids','result_evidence_ids'):
            for eid in row[key]:
                fact=facts.get(eid)
                if fact is None or fact.experience_id not in row['primary_experience_ids']:
                    errors.append(dict(question_id=row['question_id'],code='evidence_outside_declared_experience',field=key,evidence_id=eid))
        for eid in row['result_evidence_ids']:
            if eid in facts and facts[eid].fact_type!='result':
                errors.append(dict(question_id=row['question_id'],code='non_result_evidence_used_as_result',evidence_id=eid,fact_type=facts[eid].fact_type))
        for gap in row['missing_information']:
            if gap['category'] not in {'applicant_evidence','experience_evidence'} and gap['target_experience_id'] is not None:
                errors.append(dict(question_id=row['question_id'],code='intent_or_context_gap_targets_experience',key=gap['key']))
    return errors


def main():
    directory=RESULTS/'offline_rechecks'
    directory.mkdir(exist_ok=True)
    for path in sorted(RESULTS.glob('*-attempt[12].json')):
        record=json.loads(path.read_text(encoding='utf-8'))
        record['original_validation']=record['validation']
        record['offline_recheck_api_calls']=0
        record['validation']={}
        case=record['fixture']
        stage='analyzer'
        try:
            qs=[Question(question_id=f"{case['set_id']}-Q{i+1}",raw_text=text,
                constraints=parse_constraints(text)) for i,text in enumerate(case['questions'])]
            analysis=validate_analysis(qs,record['raw_analyzer_output'])
            record['validation']['analyzer']='PASS'
            if case['set_id']=='A':
                expected={'A-Q1':{'company_motivation','preparation_effort'},
                    'A-Q2':{'desired_work','differentiating_strength','supporting_experience'},
                    'A-Q3':{'challenge','personal_action','result'}}
                record['validation']['requested_asks_not_extracted']={q.question_id:sorted(expected[q.question_id]-{a.key for a in q.asks_for})
                    for q in analysis.questions if expected[q.question_id]-{a.key for a in q.asks_for}}
            stage='planner'
            if not record.get('raw_planner_output'): raise ValueError('No saved Planner output; not fabricated')
            data=PlanningInput(application_id=f"fictional-{case['set_id']}",questions=analysis.questions,
                experiences=[PlanningExperience.model_validate(e) for e in case['experiences']],
                target_context=case['target_context'],answers=[AnswerDocument.model_validate(a) for a in case['answers']])
            record['validation']['all_reference_violations']=reference_diagnostics(data,record['raw_planner_output'])
            result=validate_plan(data,record['raw_planner_output'])
            record['validated_result']=result.model_dump(mode='json')
            record['validation'].update(planner='PASS',narrative_warnings=narrative_warnings(data,result.plan),
                semantic_quality='HUMAN_REVIEW_REQUIRED')
        except (ValueError,KeyError) as exc:
            record['validation'].update(failed_stage=stage,contract_error=str(exc))
        out=directory/path.name
        save(out,record)
        out.with_suffix('.md').write_text('> Offline recheck: new API calls = 0. Usage below is the original live run.\n\n'+render(record),encoding='utf-8')
        print(f"{record['set_id']} attempt {record['attempt']}: {record['validation']}")


if __name__=='__main__': main()
