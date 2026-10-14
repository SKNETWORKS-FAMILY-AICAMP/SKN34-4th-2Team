"""Readiness -> prose -> separate fact/quality gates -> ONE conditional rewrite."""
import re
from difflib import SequenceMatcher
from app.application_planning.engine import validate_plan, INTENT_KEYS
from app.resume_review_v2.validation import _numbers, _technologies, _normalized, PROCEDURE_PATTERN
from .models import WriteRequest, ReadinessResult, WriterOutput, SemanticResult, ValidationResult, AnswerResult

DUPLICATE_RATIO = .86
MIN_DUPLICATE_LENGTH = 40
MAX_PROCEDURE_CONNECTORS = 3


class VerifierContractError(ValueError):
    """A broken verifier contract isn't a reason to rewrite valid Writer prose."""


def assignment(request, qid):
    return next(a for a in request.plan.assignments if a.question_id == qid)


def materials(request, qid):
    return [m for m in request.materials if m.question_id == qid]


def check_sources(request):
    seen = set()
    qids = {q.question_id for q in request.questions}
    facts = {f.evidence_id for e in request.planning_input.experiences for f in e.evidence}
    for m in request.materials:
        identity=(m.question_id,m.material_id)
        if identity in seen or m.material_id in facts or m.question_id not in qids:
            raise ValueError('duplicate/unknown material identity')
        seen.add(identity)
        if m.requirement_source is not None:
            from .requirement_context import resolve_requirement
            resolve_requirement(request.planning_input.target_context,m,request.planning_input.application_id)
            continue
        if m.source_type == 'applicant_intent':
            if m.key not in INTENT_KEYS or m.source_path or m.answer_index is None:
                raise ValueError('mixed intent/context source')
            if not 0 <= m.answer_index < len(request.planning_input.answers):
                raise ValueError('unknown answer source')
            a = request.planning_input.answers[m.answer_index]
            if (a.source_type not in {'user_supplement', 'user_draft'} or not a.topic_resolved
                or a.target_experience_id or a.confirmation_key != m.key
                or a.question_id != m.question_id or m.source_quote not in a.content):
                raise ValueError('unconfirmed/cross-question intent source')
        else:
            if m.answer_index is not None or not m.source_path:
                raise ValueError('mixed/missing target source')
            value = request.planning_input.target_context
            for key in m.source_path:
                if not isinstance(value, dict) or key not in value:
                    raise ValueError('unknown target snapshot source')
                value = value[key]
            if not isinstance(value, str) or m.source_quote not in value:
                raise ValueError('target quote not in source')


def readiness(request: WriteRequest, qid: str) -> ReadinessResult:
    """No client/DB/implicit replan. Structural blockers take precedence over gaps."""
    try:
        if request.current_input_hash != request.plan_input_hash:
            raise ValueError('stale plan: replan required')
        raw = {q.question_id:q for q in request.questions}
        analyzed = {q.question_id:q for q in request.planning_input.questions}
        if len(raw)!=len(request.questions) or set(raw)!=set(analyzed) or qid not in raw:
            raise ValueError('question contract mismatch')
        for key, question in analyzed.items():
            if question.constraints != raw[key].constraints or any(a.source_quote not in raw[key].raw_text for a in question.asks_for):
                raise ValueError('question analysis/source mismatch')
        seen=set()
        for experience in request.planning_input.experiences:
            for fact in experience.evidence:
                if fact.experience_id!=experience.experience_id or fact.evidence_id in seen:
                    raise ValueError('duplicate/cross-Experience source fact')
                seen.add(fact.evidence_id)
        validated=validate_plan(request.planning_input, request.plan)
        check_sources(request)
        row = next(a for a in validated.plan.assignments if a.question_id==qid)
        if not row.requirement_coverage:
            raise ValueError('historical plan lacks coverage: replan required')
        if raw[qid].constraints.character_limit and raw[qid].constraints.count_unit == 'unknown':
            raise ValueError('explicit limit has unknown counting policy')
    except (ValueError, StopIteration, KeyError) as exc:
        return ReadinessResult(question_id=qid, status='BLOCKED', issues=[str(exc)])
    missing = [g.model_dump() for g in row.missing_information if g.importance in {'high','medium'}]
    for c in row.requirement_coverage:
        if c.blocking_missing_information or c.status == 'missing':
            if not any(g['key']==c.requirement for g in missing):
                missing.append(dict(key=c.requirement,reason=c.blocking_missing_information or c.reason))
    asks = {a.key for a in analyzed[qid].asks_for if a.required}
    available = materials(request,qid)
    for key in asks & INTENT_KEYS:
        if not any(m.source_type=='applicant_intent' and m.key==key for m in available) and not any(
            g['key']==key and g.get('category')=='applicant_intent' for g in missing):
            missing.append(dict(key=key,category='applicant_intent',reason='confirmed normalized intent required'))
    if 'company_motivation' in asks and not any(m.source_type=='target_context' for m in available) and not any(
        g.get('category')=='target_context' and g['key']=='company_motivation' for g in missing):
        missing.append(dict(key='company_motivation',category='target_context',reason='company source context required'))
    if 'result' in asks and not row.result_evidence_ids and not any(g['key']=='result' for g in missing):
        missing.append(dict(key='result',category='experience_evidence',reason='actual result required'))
    if asks-INTENT_KEYS and not row.core_evidence_ids:
        missing.append(dict(key='core',category='experience_evidence',reason='core applicant contribution required'))
    return ReadinessResult(question_id=qid,status='NEEDS_INPUT' if missing else 'READY',missing_information=missing)


def writer_input(request, qid):
    """ONLY Writer payload: no whole resume, raw Q&A, or unselected facts."""
    row=assignment(request,qid)
    facts={f.evidence_id:f for e in request.planning_input.experiences for f in e.evidence}
    def selected(ids): return [facts[i].model_dump() for i in ids]
    question=next(q for q in request.questions if q.question_id==qid)
    analysis=next(q for q in request.planning_input.questions if q.question_id==qid)
    return dict(question=question.model_dump(),story_focus=row.story_focus,
        requirements=[ask.model_dump() for ask in analysis.asks_for],experience_scope=row.primary_experience_ids,
        core=selected(row.core_evidence_ids),supporting=selected(row.supporting_evidence_ids),result=selected(row.result_evidence_ids),
        context=[dict(source_id=m.material_id,source_type=m.source_type,key=m.key,text=m.normalized_text,
            **({'requirement_source':m.requirement_source.model_dump(mode='json')} if m.requirement_source else {})) for m in materials(request,qid)])


def approved_sources(request,qid):
    row=assignment(request,qid)
    ids=set(row.core_evidence_ids+row.supporting_evidence_ids+row.result_evidence_ids)
    sources={('evidence',f.evidence_id):f.normalized_fact for e in request.planning_input.experiences for f in e.evidence if f.evidence_id in ids}
    sources.update({(m.source_type,m.material_id):m.source_quote if m.requirement_source else m.normalized_text for m in materials(request,qid)})
    return sources


def deterministic_validation(request,qid,output,previous_answers=()):
    result=ValidationResult()
    if output.question_id!=qid: result.factual_issues.append('output question mismatch')
    sources=approved_sources(request,qid)
    used=set()
    for index,s in enumerate(output.sentences):
        refs=[(r.source_type,r.source_id) for r in s.support_refs]
        if not s.text.strip() or '\n' in s.text: result.quality_issues.append(f'sentence {index}: empty/multiline sentence')
        if len(refs)!=len(set(refs)) or any(ref not in sources for ref in refs):
            result.factual_issues.append(f'sentence {index}: unapproved support reference')
        if set(s.claim_types)!={kind for kind,_ in refs}:
            result.factual_issues.append(f'sentence {index}: missing/mixed claim provenance')
        supported=' '.join(sources.get(ref,'') for ref in refs)
        if _numbers(s.text)-_numbers(supported): result.factual_issues.append(f'sentence {index}: unsupported number')
        if _technologies(s.text)-_technologies(supported): result.factual_issues.append(f'sentence {index}: unsupported technology')
        used.update(sid for kind,sid in refs if kind=='evidence')
        if len(PROCEDURE_PATTERN.findall(s.text))>=MAX_PROCEDURE_CONNECTORS:
            result.quality_issues.append(f'sentence {index}: procedure overload')
    row=assignment(request,qid)
    unused=set(row.core_evidence_ids)-used
    if unused: result.quality_issues.append('core contribution unused')
    if any(a.key=='result' and a.required for q in request.planning_input.questions if q.question_id==qid for a in q.asks_for) and not used.intersection(row.result_evidence_ids):
        result.quality_issues.append('required result not expressed')
    facts={f.evidence_id:f for e in request.planning_input.experiences for f in e.evidence}
    if any(facts[i].fact_type in {'technology','implementation','technical_decision'} for i in unused):
        result.quality_issues.append('critical technical signal loss')
    c=next(q.constraints for q in request.questions if q.question_id==qid)
    text=output.final_text
    countable=re.sub(r'\s','',text) if c.include_spaces is False else text
    count=len(countable.encode('utf-8')) if c.count_unit=='bytes' else len(countable)
    if c.character_limit and count>c.character_limit:
        result.quality_issues.append(f'explicit length limit exceeded: {count}/{c.character_limit}')
    if c.character_limit and c.include_spaces is None:
        result.warnings.append('whitespace policy unspecified; conservatively counted all whitespace')
    for previous in previous_answers:
        if previous.question_id==qid: continue
        old,new=_normalized(previous.final_text),_normalized(text)
        if min(len(old),len(new))>=MIN_DUPLICATE_LENGTH and SequenceMatcher(None,old,new).ratio()>=DUPLICATE_RATIO:
            result.quality_issues.append(f'cross-question answer duplication: {previous.question_id}')
        elif any(min(len(_normalized(x.text)),len(_normalized(y.text)))>=MIN_DUPLICATE_LENGTH and
            SequenceMatcher(None,_normalized(x.text),_normalized(y.text)).ratio()>=DUPLICATE_RATIO
            for x in previous.sentences for y in output.sentences):
            result.warnings.append(f'cross-question repeated sentence candidate: {previous.question_id}')
    return result


def merge_semantic(request,qid,validation,semantic):
    if semantic.question_id!=qid:
        validation.factual_issues.append('semantic output question mismatch')
        return validation
    row=assignment(request,qid)
    expressed=set(semantic.expressed_core_evidence_ids)
    if expressed-set(row.core_evidence_ids): validation.factual_issues.append('semantic verifier referenced unapproved core')
    if set(row.core_evidence_ids)-expressed: validation.quality_issues.append('core meaning/technical signal lost')
    required={a.key for q in request.planning_input.questions if q.question_id==qid for a in q.asks_for if a.required}
    if required-set(semantic.covered_requirements): validation.quality_issues.append('required question content missing')
    if not semantic.story_focus_preserved: validation.quality_issues.append('story focus lost')
    validation.factual_issues.extend(semantic.factual_issues)
    validation.quality_issues.extend(semantic.quality_issues)
    return validation


def run_answer(request: WriteRequest,qid,client,previous_answers=()):
    gate=readiness(request,qid)
    result=AnswerResult(question_id=qid,status=gate.status,readiness=gate)
    if gate.status!='READY': return result
    payload=writer_input(request,qid)
    rewrite=None
    for attempt in range(2):
        try:
            candidate=WriterOutput.model_validate(client.write(payload,rewrite=rewrite))
            checked=deterministic_validation(request,qid,candidate,previous_answers)
            semantic=None
            if not checked.factual_issues:
                audit=dict(writer_input=payload,source_materials=[m.model_dump() for m in materials(request,qid)],candidate=candidate.model_dump(),
                    other_answers=[dict(question_id=p.question_id,text=p.final_text) for p in previous_answers if p.question_id!=qid])
                semantic=SemanticResult.model_validate(client.verify(audit))
                if semantic.question_id!=qid or set(semantic.expressed_core_evidence_ids)-set(assignment(request,qid).core_evidence_ids):
                    raise VerifierContractError('Verifier returned invalid question/core IDs')
                checked=merge_semantic(request,qid,checked,semantic)
            result.attempts.append(dict(candidate=candidate.model_dump(),validation=checked.model_dump(),semantic=semantic.model_dump() if semantic else None))
            result.candidate,result.validation=candidate,checked
            result.rewrite_count=attempt
            if checked.passed:
                result.status='READY'
                return result
            rewrite=dict(previous_candidate=candidate.model_dump(),factual_issues=checked.factual_issues,quality_issues=checked.quality_issues,
                other_answers=[dict(question_id=p.question_id,text=p.final_text) for p in previous_answers if p.question_id!=qid])
        except Exception as exc:
            # No automatic paid retry on transport/schema failure.
            result.status='BLOCKED'
            result.error=type(exc).__name__
            result.rewrite_count=attempt
            return result
    result.status='BLOCKED'
    return result
