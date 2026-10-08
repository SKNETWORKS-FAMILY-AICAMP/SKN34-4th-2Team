"""Actual verifier on intentionally bad drafts with deceptively valid citations.

Not production rules: these three mutations are evaluation-only counterexamples.
"""
import argparse
import json
import os
from pathlib import Path
from app.resume_review_v2.models import ReviewInput, Evidence, WriterOutput, RevisionSentence
from evaluation.section_quality_live import RecordedBatch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--source', required=True)
    parser.add_argument('--label', required=True)
    args = parser.parse_args()
    if not args.live:
        parser.error('--live required for paid calls')
    if not args.label.replace('-', '').replace('_', '').isalnum():
        parser.error('invalid label')
    root = Path(__file__).resolve().parents[2]
    for line in (root / '.env').read_text(encoding='utf-8').splitlines():
        key, sep, value = line.strip().partition('=')
        if sep and key == 'OPENAI_API_KEY' and not os.environ.get(key):
            os.environ[key] = value.strip().strip('\"\'')
    os.environ.update(LANGCHAIN_TRACING_V2='false', LANGSMITH_TRACING='false')
    source = json.loads(Path(args.source).read_text(encoding='utf-8'))
    from app.config import get_settings
    settings = get_settings()
    engine = RecordedBatch(source['model'], settings.openai_reasoning_effort)
    mutations = {
        'future_plan': 'Python과 SQL을 활용해 실무에 기여하고 반복 분석과 데이터 확인 업무를 자동화하겠습니다. 장기적으로 분석 결과를 서비스 개선과 의사결정에 연결하고 싶습니다.',
        'motivation': 'KKBOX 이탈 예측, 위치 기반 정비소 검색, AI LMS 프로젝트를 경험했습니다.',
        'project': 'Python·Pandas 기반 데이터 처리와 Streamlit 서비스 구현을 맡아 Haversine 거리 계산과 필터를 구현하고 주요 기능을 직접 테스트했습니다.',
    }
    items = {}
    for row in source['results']:
        section = row['section_profile']['section_type']
        req = ReviewInput.model_validate({'experience': row['experience'],
            'section_profile': row['section_profile'], 'sentence_plan': row['sentence_plan'],
            'approved_intents': row['intent_claims']})
        facts = [Evidence.model_validate(e) for e in row['debug_trace']['evidence_claims']]
        plan = row['plan']
        draft = WriterOutput(experience_id=req.experience.experience_id,
            operation='replace_field', original_quote=req.experience.current_text,
            sentences=[RevisionSentence(text=mutations[section],
                evidence_ids=[e.evidence_id for e in facts], intent_ids=[i.id for i in req.approved_intents],
                semantic_unit_ids=[u.id for u in req.section_profile.original_semantic_units])])
        items[section] = (req, draft, facts, plan['core_evidence_ids'], [], plan['preserved_evidence_ids'])
    output = Path(__file__).parent / 'runs' / ('counterexamples_' + args.label + '.json')
    if output.exists():
        raise SystemExit('Choose a new label')
    verdicts = engine._batch('verify', items)
    checks = {section: bool(verdict.unsupported_claims if section == 'project' else verdict.section_meaning_loss)
              for section, verdict in verdicts.items()}
    output.write_text(json.dumps({'model': source['model'], 'mutations': mutations,
        'checks': checks, 'verdicts': {s: v.model_dump() for s, v in verdicts.items()},
        'usage': engine.usage.model_dump()}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'checks': checks, 'report': str(output)}), flush=True)
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
