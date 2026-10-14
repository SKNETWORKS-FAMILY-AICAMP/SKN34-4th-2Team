"""Scoped Analyze references and read-only resume-level aggregation, never a Writer gate."""
import re
from app.review_workflow import digest
from app.job_requirements import RequirementStatusRow
from app.resume_review import _number_facts
from .models import Evidence, Experience, ReviewInput, RequirementEvidenceMatch
from .project_planning import active_facts
from .validation import _technologies, _exact_source_quote
from .audit_resume import source_signature

UNASSIGNED_PATH = '__requirement_owner__'


def context_hash(source, requirements):
    return digest([source, [r.model_dump(mode='json') for r in requirements]])


def ground_matches(request, matches, evidence):
    if matches is None:
        return None, []
    requirements = {r.requirement_id:r for r in request.job_requirements}
    active = active_facts(evidence)
    grounded, warnings, seen = [], [], set()
    sources = request.factual_resume_sources()
    for match in matches:
        rid = match.requirement_id
        if rid not in requirements or rid in seen:
            warnings.append(f'{rid}: invalid requirement reference')
            continue
        seen.add(rid)
        ids = list(dict.fromkeys(match.evidence_ids))
        facts = [active[eid] for eid in ids if eid in active]
        valid = bool(facts) and len(facts) == len(ids)
        for fact in facts:
            source = sources.get(fact.source_id) if fact.source_type == 'resume_text' else request.answer if fact.source_type == 'user_answer' else None
            valid = valid and fact.experience_id == request.experience.experience_id and source is not None and _exact_source_quote(source, fact.evidence_quote) is not None
        if match.status == 'unconfirmed' and not ids:
            grounded.append(match)
            continue
        if not valid:
            warnings.append(f'{rid}: inactive, unknown or out-of-scope Evidence')
            continue
        text = ' '.join(f.evidence_quote for f in facts)
        wanted = _technologies(requirements[rid].text + ' ' + requirements[rid].posting_quote)
        available = _technologies(text)
        if wanted and not wanted & available:
            warnings.append(f'{rid}: different technology is not fulfillment')
            continue
        status = match.status
        inventory = all(f.fact_type.value == 'technology' or f.source_id.endswith(':techStack') for f in facts)
        scope = match.assertion_scope
        if re.search(r'예정|계획|하고 싶|하겠|경험(?:이|은)?\s*없|사용하지 않|해 본 적.*없', text):
            warnings.append(f'{rid}: intention or negation is not performed experience')
            continue
        if re.search(r'팀원|다른 사람', text) and not re.search(r'제가|저는|본인|직접', text):
            status, scope = 'partial', 'context'
        if (scope == 'owned' and not re.search(r'담당|맡|책임|주도|총괄', text)
                or scope == 'result' and not any(f.fact_type.value == 'result' for f in facts)
                or scope == 'proficiency'
                or scope == 'used' and (all(f.source_id.endswith(':techStack') for f in facts)
                    or not re.search(r'사용|활용|구현|개발|분석|적용|연동', text))):
            status = 'partial'
            scope = 'mentioned' if inventory else 'context'
        if (wanted - available or inventory or scope == 'mentioned'
                or _number_facts(requirements[rid].text) - _number_facts(text)):
            status = 'partial'  # Names/listings never certify a complex capability.
        grounded.append(match.model_copy(update={'evidence_ids':ids,'status':status,'assertion_scope':scope}))
    return grounded, warnings


def reconcile_matches(request, previous, current, old_evidence, evidence):
    """Retain unchanged direct grounds, not a sticky fulfillment verdict.

    Empty reassessment is not evidence retraction; semantic disagreement remains
    pending/partial instead of silently restoring a former met verdict.
    """
    prior,warnings=ground_matches(request,previous,evidence)
    if current is None:return None,[]  # unavailable planning is still pending
    output={m.requirement_id:m for m in current};notes=[]
    old={f.evidence_id:f for f in old_evidence};active=active_facts(evidence)
    for match in prior or []:
        latest=output.get(match.requirement_id)
        if match.status=='unconfirmed' or latest is not None and (latest.status!='unconfirmed' or latest.evidence_ids):continue
        ids=match.evidence_ids
        unchanged=bool(ids) and all(eid in old and eid in active and
            old[eid].model_dump(exclude={'normalized_fact','fact_type','created_at','updated_at'})==
            active[eid].model_dump(exclude={'normalized_fact','fact_type','created_at','updated_at'}) for eid in ids)
        if not unchanged or any(w.startswith(match.requirement_id+':') for w in warnings):continue
        output[match.requirement_id]=match.model_copy(update={'status':'partial'})
        notes.append(match.requirement_id+': assessment_changed_with_unchanged_grounds')
    return list(output.values()),notes


def aggregate(requirements, records, fields, content_hash, source, source_for, item_refs, ledger=(), provenance_for=None):
    expected = context_hash(source, requirements)
    rows, states = [], {}
    for record in records:
        exp = Experience.model_validate(record['experience'])
        path = exp.field_path
        if path not in fields or item_refs.get(path) != exp.experience_id:
            continue
        title, sources = source_for(path, exp.experience_id)
        request = ReviewInput(experience=exp.model_copy(update={'title':title,'current_text':fields[path], 'content_hash':content_hash}),
            resume_sources=sources, answer=record.get('answer',''), answer_source_id='saved-answer' if record.get('answer') else '',
            job_requirements=[dict(requirement_id=r.id,text=r.label,posting_quote=r.posting_quote) for r in requirements])
        valid_source = record.get('audit_source_hash') == source_signature(request)
        roots=provenance_for(request,record) if provenance_for else None
        if roots is not None:
            request=request.model_copy(update={'historical_resume_sources':roots})
            valid_source=True  # server operation proof, not a raw quote substring
        if not valid_source or record.get('requirement_context_hash') != expected:
            continue
        facts = {e.evidence_id:e for e in map(Evidence.model_validate, record.get('evidence_state', []))}
        raw = record.get('requirement_matches')
        matches, warnings = ground_matches(request, None if raw is None else [RequirementEvidenceMatch.model_validate(m) for m in raw], facts)
        states[exp.experience_id] = (record, request, facts, matches, warnings)
    latest = {}
    for item in ledger:
        if item.get('context_hash') == expected:
            if item.get('experience_id') is not None and item.get('disposition') == 'provided':
                latest.pop((item['requirement_id'],None),None)
            latest[(item['requirement_id'],item.get('experience_id'))] = item
    for requirement in requirements:
        refs, status, incomplete = [], 'unconfirmed', not records or len(states) < len(records)
        for owner,(record,request,facts,matches,warnings) in states.items():
            issues = [*warnings,*record.get('requirement_warnings', [])]
            if any('invalid requirement reference' in w and w.split(':')[0] not in {r.id for r in requirements} for w in issues):
                incomplete = True
            relevant=[w for w in issues if w.startswith(requirement.id+':')]
            if matches is None or any(not w.endswith('assessment_changed_with_unchanged_grounds') for w in relevant):
                incomplete = True
                continue
            if relevant:incomplete=True
            match = next((m for m in matches if m.requirement_id == requirement.id),None)
            if not match or match.status == 'unconfirmed':
                continue
            if match.status == 'met' or status == 'unconfirmed': status = match.status
            for eid in match.evidence_ids:
                fact = facts[eid]
                refs.append(dict(experience_id=owner,experience_title=request.experience.title,evidence_id=eid,field_path=request.experience.field_path,
                    source_id=fact.source_id,source_type=fact.source_type,quote=fact.evidence_quote,assertion_scope=match.assertion_scope,
                    source_basis='verified_historical_source' if fact.source_type=='resume_text' and any(
                        s.source_id==fact.source_id for s in request.historical_resume_sources) else fact.source_type))
        # A global technology inventory is its own document source, not any project's fact.
        wanted = _technologies(requirement.label + ' ' + requirement.posting_quote)
        for path,text in fields.items():
            if path.startswith('techStack') and wanted & _technologies(text):
                if re.search(r'예정|계획|없|않', text): continue
                refs.append(dict(field_path=path,source_type='resume_text',source_id=path,quote=text,assertion_scope='mentioned'))
                if status == 'unconfirmed': status = 'partial'
        global_answer = latest.get((requirement.id,None))
        if status == 'unconfirmed' and global_answer and global_answer.get('disposition') == 'absent':
            status = 'absent'
        rows.append(RequirementStatusRow(**requirement.model_dump(),status=status,
            assessment_state='pending' if incomplete else 'complete',snapshot_hash=source.get('snapshot_hash',''),source_hash=content_hash,
            evidence_paths=list(dict.fromkeys(r['field_path'] for r in refs)), evidence_quotes=list(dict.fromkeys(r['quote'] for r in refs)),
            evidence_refs=refs, source='answer' if any(r['source_type']=='user_answer' for r in refs) else 'resume' if refs else 'user' if status=='absent' else 'none'))
    return rows


def answer_disposition(text):
    value = re.sub(r'[\s.!?]+','',text)
    if value in {'없음','없다','없습니다','경험없음','경험이없습니다','해본적없습니다'}: return 'absent'
    if value in {'모름','모른다','모르겠습니다','잘모르겠습니다','기억나지않습니다'}: return 'unknown'
    return 'provided'
