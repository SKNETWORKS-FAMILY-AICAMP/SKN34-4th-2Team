"""Read two extracted policy corpora and write a local, explicitly hypothetical preview."""
import argparse
from datetime import date
import json
from pathlib import Path

from chatbot.document_calculation_rules import extract_candidates, PreviewPolicy, preview_threshold
from chatbot.evaluation.evaluate_policy_rag import write_json


def run(source, output):
    output = Path(output)
    if output.exists():
        raise ValueError('Choose a new output file')
    policies, candidates = [], []
    for cohort in ('cohort_34','cohort_40'):
        rows = json.loads((Path(source)/f'corpus-{cohort}-B.json').read_text(encoding='utf-8'))
        extracted = extract_candidates(rows)
        if not extracted:
            raise ValueError('No supported rules extracted')
        policies.append(PreviewPolicy(cohort, extracted[0].document_hash, date(2026,10,8), None, tuple(extracted)))
        candidates.extend(c.metadata() for c in extracted)
    results = [preview_threshold(policies, cohort=p.cohort, purpose=purpose, as_of=date(2026,10,8),
        recognized=85,total=100,denominator=basis) for p in policies
        for purpose,basis in (('completion','whole_course'),('allowance','unit_period'))]
    write_json(output, {'status':'unverified_preview', 'external_calls':0,
        'scenario_note':'2026-10-08 적용일 및 85/100일은 테스트 가정이며 실제 일정·개인 기록이 아니다.',
        'candidates':candidates,'results':results})


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    run(args.source,args.output)
