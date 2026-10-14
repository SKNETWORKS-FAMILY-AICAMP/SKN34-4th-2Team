"""Recheck the three saved live outputs with current contracts. No API/DB calls."""
import json
from .application_planning_live import HERE, CASES
from app.application_planning.engine import validate_analysis, validate_plan, parse_constraints
from app.application_planning.models import Question, PlanningInput, PlanningExperience, AnswerDocument


def main():
    cases = {c['set_id']: c for c in json.loads(CASES.read_text(encoding='utf-8'))}
    for sid in ('A', 'B', 'C'):
        record = json.loads((HERE / 'application_planning_phase4a7_results' / f'{sid}-attempt1.json').read_text(encoding='utf-8'))
        assert record['fixture'] == cases[sid]
        assert len(record['calls']) == 1 and record['calls'][0]['stage'] == 'planner'
        questions = [Question(question_id=f'{sid}-Q{i+1}', raw_text=text,
            constraints=parse_constraints(text)) for i, text in enumerate(cases[sid]['questions'])]
        analysis = validate_analysis(questions, record['raw_analyzer_output'])
        data = PlanningInput(application_id=f'fictional-{sid}', questions=analysis.questions,
            experiences=[PlanningExperience.model_validate(e) for e in cases[sid]['experiences']],
            target_context=cases[sid]['target_context'], answers=[AnswerDocument.model_validate(a) for a in cases[sid]['answers']])
        result = validate_plan(data, record['raw_planner_output'])
        assert result.model_dump(mode='json') == record['validated_result']
        if sid == 'A':
            q1 = result.plan.assignments[0]
            assert any(c.requirement == 'preparation_effort' and c.status == 'satisfied' for c in q1.requirement_coverage)
            assert not any(g.key == 'preparation_effort' for g in q1.missing_information)
            assert any(g.key == 'company_motivation' and g.category == 'applicant_intent' for g in q1.missing_information)
            assert any(g.category == 'target_context' for g in q1.missing_information)
            assert not result.plan.assignments[1].missing_information
        elif sid == 'B':
            assert all(row.primary_experience_ids == ['exp-D'] for row in result.plan.assignments)
            assert len({row.story_focus for row in result.plan.assignments}) == 3
            assert len({tuple(row.core_evidence_ids) for row in result.plan.assignments}) == 3
        else:
            row = result.plan.assignments[0]
            assert not row.result_evidence_ids
            assert any(g.key == 'result' and g.category == 'experience_evidence' for g in row.missing_information)
        print(f'{sid}: current contract + expected structural conditions PASS; offline calls=0; semantic human approval not inferred')


if __name__ == '__main__':
    main()
