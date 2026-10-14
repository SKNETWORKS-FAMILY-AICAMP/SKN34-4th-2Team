"""Existing B/C baseline replay + both new A outputs. No API or DB calls.

Replaying B/C is NOT a new live regression. Preserve this distinction in reports.
"""
import json
from .application_planning_live import HERE, RESULTS, render, save, narrative_warnings
from .application_planning_recheck import reference_diagnostics
from app.application_planning.engine import parse_constraints, validate_analysis, validate_plan
from app.application_planning.models import Question, PlanningInput, PlanningExperience, AnswerDocument


def main():
    current=HERE/'application_planning_phase4a6_results'
    destination=current/'offline_rechecks'
    destination.mkdir(parents=True,exist_ok=True)
    paths=list(sorted(current.glob('A-attempt*.json')))+[RESULTS/f'{sid}-attempt1.json' for sid in ('B','C')]
    for path in paths:
        record=json.loads(path.read_text(encoding='utf-8'))
        record['original_validation']=record['validation']
        record['offline_recheck_api_calls']=0
        record['artifact_source']=str(path.relative_to(HERE))
        record['validation']={}
        case=record['fixture']
        try:
            qs=[Question(question_id=f"{case['set_id']}-Q{i+1}",raw_text=text,
                constraints=parse_constraints(text)) for i,text in enumerate(case['questions'])]
            analysis=validate_analysis(qs,record['raw_analyzer_output'])
            record['validation']['analyzer']='PASS'
            data=PlanningInput(application_id=f"fictional-{case['set_id']}",questions=analysis.questions,
                experiences=[PlanningExperience.model_validate(e) for e in case['experiences']],
                target_context=case['target_context'],answers=[AnswerDocument.model_validate(a) for a in case['answers']])
            record['validation']['all_reference_violations']=reference_diagnostics(data,record['raw_planner_output'])
            result=validate_plan(data,record['raw_planner_output'])
            record['validated_result']=result.model_dump(mode='json')
            record['validation'].update(planner='PASS',narrative_warnings=narrative_warnings(data,result.plan),
                                        semantic_quality='HUMAN_REVIEW_REQUIRED')
        except ValueError as exc:
            record.pop('validated_result',None)
            record['validation']['contract_error']=str(exc)
        out=destination/path.name
        save(out,record)
        out.with_suffix('.md').write_text(
            '> OFFLINE REPLAY: no new API calls. B/C usage is historical Phase4A.5, NOT this phase.\n\n'+render(record),encoding='utf-8')
        print(f"{record['set_id']} attempt {record['attempt']}: {record['validation']}")


if __name__=='__main__': main()
