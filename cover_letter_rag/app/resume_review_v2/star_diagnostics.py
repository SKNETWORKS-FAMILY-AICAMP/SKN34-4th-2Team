"""Read-only original-text diagnostics; never a planning/writing/validation gate.

Reuse typed analysis and exact original quotes, not facet-to-STAR slot conversion.
This conservative projection cannot claim exhaustive STAR absence or success.
"""
import re
from app.models import StarCheck, StarJudgementOut
from app.star_checks import STAR_TARGET, ground_star_judgements
from .models import Evidence, Experience, ReviewInput
from .audit_resume import source_signature
from .project_planning import active_facts
from .writing_policy import target_section


def original_star_checks(records, fields, content_hash, source_for, item_refs=None):
    checks = []
    for record in records:
        experience = Experience.model_validate(record['experience'])
        path = experience.field_path
        if path not in fields:
            continue
        metadata = dict(field_path=path, experience_id=experience.experience_id,
                        source_hash=content_hash)
        if (not STAR_TARGET.fullmatch(path)
                or target_section(experience) in {'motivation', 'future_plan', 'other'}):
            checks.append(StarCheck(**metadata, diagnostic_status='not_applicable'))
            continue
        title, sources = source_for(path, experience.experience_id)
        current = ReviewInput(experience=experience.model_copy(update={
            'current_text': fields[path], 'title': title, 'content_hash': content_hash}), resume_sources=sources)
        signature = record.get('audit_source_hash')
        valid_source = (signature == source_signature(current) if signature else
                        experience.content_hash == content_hash and experience.current_text == fields[path])
        if item_refs is not None and item_refs.get(path) != experience.experience_id:
            valid_source = False
        failed = any(issue.get('code') == 'analysis_contract_invalid'
            for issues in record.get('validation', {}).values() if isinstance(issues, list)
            for issue in issues if isinstance(issue, dict))
        if not valid_source or failed or record.get('section_profile') is None:
            checks.append(StarCheck(**metadata, diagnostic_status='pending'))
            continue
        state = {e.evidence_id:e for e in map(Evidence.model_validate, record.get('evidence_state', []))
                 if e.experience_id == experience.experience_id}
        active = active_facts(state)
        # Meaning labels help interpret approved facts. Job/intent sources never count.
        roles = {}
        for unit in record['section_profile'].get('original_semantic_units', []):
            for ref in unit.get('source_refs', []):
                if ref.get('type') == 'applicant_evidence' and ref.get('id') in active:
                    roles.setdefault(ref['id'], set()).add(unit.get('semantic_role'))
        quotes = {}
        for eid, fact in active.items():
            quote = fact.evidence_quote.strip()
            # Answers, auxiliary technology inventories, and another experience
            # are not evidence of what this current prose explicitly says.
            if (fact.source_type != 'resume_text' or fact.source_id != experience.experience_id
                    or not quote or quote not in fields[path]):
                continue
            meanings = roles.get(eid, set())
            kind = fact.fact_type.value
            if kind == 'context' and meanings & {'purpose', 'observation'}:
                if re.search(r'문제|불편|어려|지연|실패|필요|한계|원인|때문|수동|불균형', quote):
                    quotes.setdefault('situation', quote)
                if re.search(r'목표|위해|목적|만들|구축|개발', quote):
                    quotes.setdefault('task', quote)
            if kind == 'role' and 'role' in meanings:
                quotes.setdefault('task', quote)
            if kind in {'action', 'implementation', 'technical_decision'} and meanings & {'action', 'decision'}:
                quotes.setdefault('action', quote)
            # Performing a test is an action, not its outcome. Verification can
            # support Result only when an observed outcome is explicit in prose.
            observed = bool(re.search(r'(?:정상|일치|오류가 없|문제가 없|실패|증가|감소|변화|성공|차이).*(?:확인|나타|측정|관찰)', quote))
            activity_only = bool(re.fullmatch(r'.*(?:테스트|검증)(?:를|을)?\s*(?:수행|진행|실시)?(?:했|하였)습니다[.!]?', quote))
            if ((kind == 'result' and 'outcome' in meanings and not activity_only)
                    or kind == 'verification' and 'validation' in meanings and observed):
                quotes.setdefault('result', quote)
        judgement = StarJudgementOut(field_path=path,
            **{element + '_quote':quote for element,quote in quotes.items()},
            result_kind='verification' if 'result' in quotes else None)
        grounded, _ = ground_star_judgements([judgement], {path:fields[path]}, [], judged_paths=[path])
        check = grounded[0]
        checks.append(check.model_copy(update={'diagnostic_status':'complete',
            'source_hash':content_hash, 'experience_id':experience.experience_id, 'reason':''}))
    return checks
