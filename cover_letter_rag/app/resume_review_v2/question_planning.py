"""Model selects a need; server renders conditional, non-assertive public prose."""
from .project_planning import active_facts
from .models import AssertionState, GapQuestion, QuestionNeed, QuestionTarget
import re

QUESTION_CONTRACT = 'evidence-need-v2'
QUESTIONS = {
    'overview':'이 경험에서 실제로 진행한 내용이 있다면 주요 내용을 알려주세요.',
    'purpose_or_problem':'이 경험에서 해결하거나 분석하려던 문제가 있었다면 어떤 문제였나요?',
    'problem_observation':'문제나 차이를 직접 확인한 적이 있다면 무엇을 보고 파악했나요?',
    'personal_role':'이 경험에서 본인이 맡았거나 직접 수행한 일이 있다면 그 범위를 알려주세요.',
    'actions':'이 경험에서 직접 수행한 작업이 있다면 중요한 작업과 방법을 알려주세요.',
    'technologies':'이 경험에서 실제로 사용한 기술이나 방법이 있다면 무엇에 활용했나요?',
    'technical_decisions':'선택하거나 판단한 내용이 있다면 어떤 대안과 근거를 고려했나요?',
    'validation_method':'동작이나 결과를 직접 확인한 적이 있다면 어떤 방식으로 확인했나요? 수행한 점검과 확인된 결과를 구분해 알려주세요.',
    'outcome':'확인한 결과나 변화가 있다면 대상·조건·범위와 함께 알려주세요. 없거나 기억나지 않으면 그렇게 알려주셔도 됩니다.',
    'insight_or_learning':'이 경험에서 알게 된 점이 있다면 어떤 근거로 이해했나요?',
    'scale_or_constraints':'진행 범위나 제약 조건이 있었다면 기억나는 범위에서 알려주세요.',
}
FOCUS_QUESTIONS = {
    'comparison_basis':'비교하거나 선택한 경험이 있다면 어떤 기준과 결과로 판단했나요? 구체적인 수치를 기억하지 못하면 정성적인 내용도 괜찮습니다.',
    'model_evaluation':'모델을 평가한 경험이 있다면 어떤 기준·방법을 사용했고 어떤 결과를 확인했나요? 기억나는 범위에서 알려주세요.',
    'analysis_validation':'분석이나 기능을 실제로 점검한 적이 있다면 사용한 사례·방법과 확인한 결과·한계를 구분해 알려주세요.',
    'observation_basis':'문제나 차이를 관찰한 적이 있다면 어떤 자료나 상황에서 확인했나요?',
}


ASPECT_QUESTIONS = {
    'experience_presence':'이 공고 요건과 관련해 직접 해본 경험이 있나요? 있다면 기억나는 일을 알려주세요. 없다면 없다고, 기억이 불확실하면 그렇게 답해도 됩니다.',
    'technology_application':'이 요건과 관련해 실제로 사용한 경험이 있다면 어떤 일에 어떻게 활용했나요? 기술명을 알고 있거나 적어 둔 것과 실제 사용한 경험은 나눠 알려주세요.',
    'selection_and_basis':'이 대상과 관련해 실제로 선택하거나 판단한 내용이 있다면 무엇을 어떤 기준으로 선택했나요? 비교 결과와 선택을 구분해 알려주세요.',
    'selection_result':'비교 후 실제로 선택하거나 판단한 내용이 있다면 무엇이었나요? 아직 결정하지 않았다면 그렇게 알려주세요.',
    'decision_basis':'판단 근거를 더 설명할 수 있다면, 어떤 기준이나 비교 내용을 중요하게 보셨나요? 기억나는 차이와 고려한 점을 알려주세요. 정확한 점수를 기억하지 못하면 정성적인 설명도 괜찮습니다.',
    'comparison_result':'이 대상에 대해 실제로 비교한 결과가 있다면 어떤 차이를 확인했나요? 측정 대상·조건·범위와 함께 알려주세요.',
    'relationship_interpretation':'이 대상의 관계나 방향성을 해석한 내용이 있다면 어떤 관계를 관찰했고 무엇을 근거로 해석했나요? 아직 확인하지 못했다면 그렇게 알려주세요.',
    'verification_method':'이 대상이 실제로 동작하는지 점검한 적이 있다면 어떤 사례·방법을 사용했나요? 구현한 점검 기능과 실제 수행한 시험을 구분해 알려주세요.',
    'verification_result_and_limits':'이 대상을 실제로 점검한 결과가 있다면 확인한 변화와 아직 남은 문제·한계를 구분해 알려주세요. 시험 수행만으로 성공을 단정하지 않아도 됩니다.',
    'implementation_scope':'이 대상에서 직접 구현한 내용이 있다면 어떤 부분을 어떻게 구현했나요?',
    'role_scope':'이 대상에서 실제로 맡거나 수행한 범위가 있다면 본인과 다른 참여자의 범위를 구분해 알려주세요.',
    'purpose':'이 대상과 관련해 해결하거나 분석하려던 문제가 있었다면 어떤 문제였나요?',
}

def render_question_text(need):
    return ASPECT_QUESTIONS.get(need.request_aspect) or FOCUS_QUESTIONS.get(need.focus, QUESTIONS[need.target_slot.value])


def _source_context(quote, source):
    if source.count(quote)!=1:return None
    start=source.index(quote);end=start+len(quote)
    left,right=_sentence_bounds(start,end,source)
    return source[left:right].strip()


def _sentence_bounds(start,end,source):
    # Expand a fragment to its complete source sentence(s), including any
    # negation/condition in that sentence. Decimal points are not boundaries.
    boundaries=[0]+[m.end() for m in re.finditer(r'[.!?](?=\s|$)|\n+',source)]+[len(source)]
    left=max(b for b in boundaries if b<=start)
    right=min(b for b in boundaries if b>=end)
    return left,right


def _overlapping_sources(quote, source, facts):
    start=source.index(quote);end=start+len(quote)
    # References may cover only part of the same sentence. Overlapping inactive
    # assertions cannot be made safe merely by deleting their IDs.
    return {f.evidence_id for f in facts if f.evidence_quote and any(
        m.start()<end and m.end()>start for m in re.finditer(re.escape(f.evidence_quote),source))}


def _display_context(source, facts, active):
    # Auxiliary context is not the target's approval basis. Hide source sentences
    # intersecting inactive assertions instead of redisplaying withdrawn facts.
    spans=[]
    for f in facts:
        if f.evidence_id not in active and f.evidence_quote:
            for m in re.finditer(re.escape(f.evidence_quote),source):
                spans.append(_sentence_bounds(m.start(),m.end(),source))
    merged=[]
    for left,right in sorted(spans):
        if merged and left<=merged[-1][1]:merged[-1]=(merged[-1][0],max(right,merged[-1][1]))
        else:merged.append((left,right))
    for left,right in reversed(merged):
        source=source[:left]+'[비활성 근거가 있는 부분은 표시하지 않습니다.]'+source[right:]
    return source.strip()


def render_question(need, evidence, requirements=(), request=None):
    """One public presentation from approved source identity, never fact paraphrase.

    Target-sentence approval and auxiliary source display are separate. A term
    anchor never authorizes a factual claim or another source's assertions.
    """
    active=active_facts(evidence);contexts=[]
    targets=need.targets or [QuestionTarget(evidence_id=eid) for eid in need.evidence_basis]
    for target in targets:
        if target.evidence_id not in need.evidence_basis or target.evidence_id not in active:
            return None,'unapproved_question_target'
        f=active[target.evidence_id]
        if target.anchor is not None and (not target.anchor.strip() or target.anchor not in f.evidence_quote):
            return None,'question_target_anchor_absent'
        quote=f.evidence_quote
        source=quote
        if request is not None:
            sources=request.factual_resume_sources()
            source=sources.get(f.source_id) if f.source_type=='resume_text' else request.answer
            if source is None:return None,'question_target_source_unavailable'
            quote=_source_context(f.evidence_quote,source)
            if quote is None:return None,'ambiguous_or_absent_target_source'
        same_source=[other for other in evidence.values() if other.source_type==f.source_type and other.source_id==f.source_id]
        related=_overlapping_sources(quote,source,same_source)
        if not related <= set(active):return None,'unsafe_target_quote_scope'
        surrounding=_display_context(source,same_source,active)
        context=dict(type='applicant_source',evidence_ids=sorted(related),target_evidence_id=f.evidence_id,
            source_type=f.source_type,source_id=f.source_id,quote=quote,anchor=target.anchor,
            selected_source_quotes=[f.evidence_quote])
        if surrounding!=quote:context['context_quote']=surrounding
        group=next((c for c in contexts if c.get('source_type')==f.source_type and c.get('source_id')==f.source_id and c.get('quote')==quote),None)
        if group is None:
            context['anchors']=[target.anchor] if target.anchor else []
            context['target_evidence_ids']=[f.evidence_id];contexts.append(context)
        else:
            group['target_evidence_ids']=sorted(set(group['target_evidence_ids']+[f.evidence_id]))
            group['anchors']=sorted(set(group['anchors']+([target.anchor] if target.anchor else [])))
            group['selected_source_quotes']=sorted(set(group['selected_source_quotes']+[f.evidence_quote]))
    if need.requirement_id:
        posting=next((r for r in requirements if getattr(r,'requirement_id',getattr(r,'id',None))==need.requirement_id),None)
        if posting is None or not posting.posting_quote.strip():return None,'question_posting_source_unavailable'
        if need.requirement_anchor and need.requirement_anchor not in posting.posting_quote:return None,'question_requirement_anchor_absent'
        contexts.append(dict(type='posting_source',requirement_id=need.requirement_id,quote=posting.posting_quote,
            **({'anchors':[need.requirement_anchor]} if need.requirement_anchor else {})))
    if not contexts:
        contexts.append(dict(type='missing_information',label='소유 경험 미확정' if need.owner_scope=='unassigned' else '경험의 추가 정보 · 원문 근거 미확인'))
    request=render_question_text(need)
    from app.review_workflow import digest
    source_keys=sorted({(c['type'],c.get('source_type',''),c.get('source_id',''),
        # With an anchor, changing extraction quote boundaries within the same
        # source sentence does not create a new information need. Without one,
        # selected spans remain visible targets, not semantic equivalence proof.
        tuple([c.get('quote','')] if c.get('anchors') else c.get('selected_source_quotes',[c.get('quote','')])),
        tuple(c.get('anchors',[]))) for c in contexts})
    fingerprint='source-need:'+digest([need.experience_id if need.owner_scope!='unassigned' else None,
        source_keys,need.request_aspect or [need.target_slot.value,need.focus],need.requirement_id])
    return dict(question=request,target_contexts=contexts,information_fingerprint=fingerprint),None


def public_question_reason():
    # Never expose model why_needed or a source paraphrase as applicant fact.
    return '이 경험을 구체적으로 설명하는 데 도움이 될 추가 정보를 확인합니다.'


def question_approval_issue(question, evidence, diagnostics=None, requirements=(), request=None):
    if not isinstance(question, GapQuestion) and any(k in question.__dict__ for k in ('question','presuppositions','experience_title')):
        return 'legacy_question_payload'
    if question.contract != QUESTION_CONTRACT:
        return 'legacy_question_contract'
    if not question.why_needed.strip() or not question.dedupe_key.strip():
        return 'missing_question_fields'
    if any(f.experience_id != question.experience_id for f in evidence.values()):
        return 'evidence_owner_mismatch'
    active = active_facts(evidence)
    if any(eid not in active for eid in question.evidence_basis):
        return 'inactive_or_unknown_evidence_basis'
    if any(active[eid].source_type not in {'resume_text','user_answer'} or not active[eid].evidence_quote.strip()
           for eid in question.evidence_basis):
        return 'unsupported_question_source'
    if question.gap_type == 'clarification' and not question.evidence_basis:
        return 'clarification_without_evidence'
    presentation,issue=render_question(question,evidence,requirements,request)
    if issue:return issue
    if isinstance(question,GapQuestion) and (question.presuppositions or question.question!=presentation['question']
            or question.target_contexts!=presentation['target_contexts']
            or question.information_fingerprint!=presentation['information_fingerprint']):return 'noncanonical_question_body'
    if diagnostics is not None:
        diagnostics.update(body_origin='server_source_target_presentation',source_explanation='quoted_context_not_verified_claim',
            public_target_contexts=presentation['target_contexts'],request_aspect=question.request_aspect)
    return None


def approved_question(question, evidence, requirements=(), request=None):
    return question_approval_issue(question, evidence,requirements=requirements,request=request) is None


def select_question(request, candidate, evidence, diagnostics=None):
    def reject(reason):
        if diagnostics is not None:
            diagnostics.update(state='model_not_proposed' if candidate is None else 'server_filtered',reason=reason)
        return []
    if diagnostics is not None:
        diagnostics.update(candidate=candidate.model_dump(mode='json') if candidate else None,
            experience_id=request.experience.experience_id)
    if candidate is None:return reject('no_candidate_returned')
    if candidate.experience_id != request.experience.experience_id:return reject('question_owner_mismatch')
    if candidate.requirement_id and candidate.requirement_id not in {r.requirement_id for r in request.job_requirements}:
        return reject('unknown_requirement')
    if candidate.owner_scope == 'unassigned' and (not candidate.requirement_id or candidate.evidence_basis):
        return reject('invalid_unassigned_owner')
    issue=question_approval_issue(candidate,evidence,diagnostics,request.job_requirements,request)
    if issue:return reject(issue)
    if not candidate.requirement_id and candidate.target_slot in request.unavailable_slots:return reject('unavailable_slot')
    prefix=request.experience.experience_id+':value:'
    key=candidate.dedupe_key if candidate.dedupe_key.startswith(prefix) else prefix+candidate.dedupe_key
    # Templates can repeat for distinct needs. Semantic repetition/value stays
    # with Analyze; exact need keys remain server-owned answer history.
    presentation,_=render_question(candidate,evidence,request.job_requirements,request)
    if key in request.previous_question_keys:return reject('exact_repeat')
    if presentation['information_fingerprint'] in request.previous_question_keys:return reject('same_target_information_request')
    need=QuestionNeed.model_validate(candidate.model_dump(exclude={'question','presuppositions','experience_title','target_contexts','information_fingerprint'}))
    presentation,_=render_question(need,evidence,request.job_requirements,request)
    question=GapQuestion(**need.model_dump(),**presentation,experience_title=request.experience.title)
    question.dedupe_key=key
    if diagnostics is not None:
        diagnostics.update(state='selected',reason=None,selected_dedupe_key=key,public_question=question.question)
    return [question]


def _linked_uncertain_unavailability(request, evidence, row, approved_ids):
    """An unavailable answer closes its own need, not an applicant claim.

    The answer-to-need link is issued by the server. A model-provided ID alone,
    or an uncertain quote from another answer/Experience, cannot close a need.
    """
    if row.state != 'unavailable' or not row.information_need_id or not row.evidence_ids:
        return False
    linked = [need for need in request.prior_information_needs
        if need.get('information_need_id') == row.information_need_id
        and need.get('owner_scope') == 'experience'
        and need.get('target_slot') == (row.target_slot.value if row.target_slot else None)
        and need.get('request_aspect') == row.request_aspect
        and need.get('requirement_id') == row.requirement_id]
    if len(linked) != 1 or len(linked[0].get('linked_answers') or []) != 1:
        return False
    need = linked[0]
    answer = need['linked_answers'][0]
    if (not answer or answer not in request.answer or not request.answer_source_id
            or not need.get('question') or not any(need['question'] in q for q in request.question_history)):
        return False
    for evidence_id in row.evidence_ids:
        if evidence_id in approved_ids:
            continue
        fact = evidence.get(evidence_id)
        if (fact is None or fact.assertion_state != AssertionState.UNCERTAIN
                or fact.experience_id != request.experience.experience_id
                or fact.source_type != 'user_answer' or fact.source_id != request.answer_source_id
                or fact.evidence_quote not in answer):
            return False
    return True


def review_information(request, extraction, evidence, gaps):
    """Discovery is stored separately from display. Slot hints never auto-ask."""
    review=extraction.question_review
    diagnostics={};questions=[];items=[]
    candidates=[]
    if extraction.question is not None:candidates.append(('proposed',extraction.question))
    if review is not None:
        for row in review.items:
            if row.need is not None:
                candidates.append((row.state,row.need));continue
            known=set(active_facts(evidence))|{i.id for i in request.approved_intents}
            legitimate=(not row.requirement_id or row.requirement_id in {r.requirement_id for r in request.job_requirements}) and (
                set(row.evidence_ids)<=known or _linked_uncertain_unavailability(request,evidence,row,known))
            state=row.state if legitimate and row.reason.strip() else 'not_reviewed'
            basis=list(row.evidence_ids)
            if state in {'sufficient','answered'} and not basis:
                # A section-wide review of future plans may rest on validated
                # ApplicantIntent rather than past-tense Evidence. This does
                # not approve an ungrounded requirement or a specific gap.
                from .writing_policy import target_section
                if (state=='sufficient' and target_section(request.experience)=='future_plan'
                        and row.target_slot is None and row.requirement_id is None
                        and row.information_need_id is None):
                    basis=sorted(i.id for i in request.approved_intents)
                if not basis:state='not_reviewed'
            items.append(dict(state=state,target_slot=row.target_slot.value if row.target_slot else None,
                requirement_id=row.requirement_id,reason=row.reason if legitimate else 'unapproved_review_basis',
                evidence_ids=basis,origin='model',information_need_id=row.information_need_id,
                request_aspect=row.request_aspect))
    seen=set();seen_needs=[]
    for disposition,need in candidates:
        local={}
        # New reviews stop the exact information need through answered keys;
        # an old facet-level unknown is not a blanket ban on independent needs.
        precise=request.model_copy(update={'unavailable_slots':[]}) if review is not None else request
        selected=select_question(precise,need,evidence,local)
        if selected:
            q=selected[0];key=q.information_fingerprint
            if key in seen:continue
            if any(_same_information_need(q.model_dump(mode='json'),other) for other in seen_needs):
                diagnostics.setdefault('coalesced_duplicate_needs',[]).append(dict(
                    information_need_id=q.dedupe_key,information_fingerprint=key))
                continue
            seen.add(key)
            seen_needs.append(q.model_dump(mode='json'))
            if disposition not in {'proposed','deferred'}:
                items.append(dict(state='not_reviewed',reason='candidate_without_proposal_state',need=need.model_dump(mode='json')));continue
            questions.append(q)
            items.append(dict(state=disposition,reason=need.why_needed,need=q.model_dump(mode='json'),key=key,
                requirement_id=q.requirement_id,target_slot=q.target_slot.value,origin='model'))
        else:
            items.append(dict(state='answered' if local.get('reason') in {'exact_repeat','same_target_information_request'} else 'blocked',
                reason=local.get('reason'),need=need.model_dump(mode='json'),requirement_id=need.requirement_id,
                target_slot=need.target_slot.value,origin='server'))
        if not diagnostics:diagnostics=local
    if not candidates:select_question(request,None,evidence,diagnostics)
    diagnostics.update(review_state=review.experience_state if review is not None and (review.reason.strip() or review.items) else 'not_recorded',
        review_reason=review.reason if review is not None else None,opportunities=items,
        gap_review_hints=[dict(target_slot=g.target_slot.value,priority=g.priority,
            state='reviewed' if any(i.get('target_slot')==g.target_slot.value and i['state']!='not_reviewed' for i in items) else 'not_reviewed') for g in gaps])
    return questions,diagnostics


def _same_information_need(left, right):
    """Source spans can vary; owner, scope and requested information cannot."""
    fields=('dedupe_key','experience_id','owner_scope','target_slot','request_aspect',
            'requirement_id','requirement_anchor','question')
    if not all(left.get(field)==right.get(field) for field in fields):
        return False
    def owning_sources(row):
        return {(c.get('source_type'),c.get('source_id')) for c in row.get('target_contexts',[])
            if c.get('type')=='applicant_source' and c.get('source_id')}
    a,b=owning_sources(left),owning_sources(right)
    # A different source span/anchor in the same owning field is one need;
    # unrelated source fields with the same generic template remain ambiguous.
    return not (a and b) or bool(a & b)


def _unique_information_needs(questions):
    unique=[]
    for question in questions:
        if not any(_same_information_need(question, other) for other in unique):
            unique.append(question)
    return unique


def _unique_opportunities(items):
    unique=[];needs=[]
    for item in items:
        need=item.get('need') or {}
        if need and any(_same_information_need(need,other) for other in needs):
            continue
        unique.append(item)
        if need:needs.append(need)
    return unique


def reconcile_deferred_needs(record, old, target_context):
    """Source-approved new decisions supersede only identified prior needs.

    A scope-only legacy review can address one unambiguous need, never an entire
    facet. Job/profile epochs gate both candidates and their review decisions.
    """
    from copy import deepcopy
    review=record.setdefault('debug_trace',{}).setdefault('question_selection',{})
    same_target=old.get('requirement_context_hash')==target_context
    prior=[q for q in old.get('gap_questions',[]) if not q.get('requirement_id') or same_target]
    current=_unique_information_needs([q for q in record.get('gap_questions',[])
        if not q.get('requirement_id') or record.get('requirement_context_hash')==target_context])
    items=review.setdefault('opportunities',[]);closed=set();closed_needs=[]
    for item in items:
        if item.get('state') not in {'sufficient','low_value','answered','unavailable'}:continue
        identity=item.get('information_need_id')
        candidates=[q for q in prior if (identity in {q.get('dedupe_key'),q.get('information_fingerprint')} if identity else
            (item.get('target_slot') is not None or item.get('requirement_id') is not None) and
            (item.get('target_slot') is None or item['target_slot']==q.get('target_slot')) and
            item.get('requirement_id')==q.get('requirement_id') and
            (item.get('request_aspect') is None or item['request_aspect']==q.get('request_aspect')))]
        groups=_unique_information_needs(candidates)
        if len(groups)!=1 or any(not _same_information_need(groups[0],q) for q in candidates):
            if identity or candidates:item.update(state='not_reviewed',reason='ambiguous_or_unknown_information_need')
            continue
        q=groups[0];key=q['dedupe_key']
        closed.update((candidate.get('information_fingerprint') or candidate['dedupe_key']) for candidate in candidates)
        closed_needs.append(q)
        item.update(information_need_id=q['dedupe_key'],key=key,need=deepcopy(q),
            target_slot=q.get('target_slot'),requirement_id=q.get('requirement_id'))
    current=[q for q in current if (q.get('information_fingerprint') or q['dedupe_key']) not in closed
        and not any(_same_information_need(q,closed_need) for closed_need in closed_needs)]
    seen={q.get('information_fingerprint') or q['dedupe_key'] for q in current}
    current.extend(deepcopy(q) for q in prior if (q.get('information_fingerprint') or q['dedupe_key']) not in seen|closed)
    record['gap_questions']=_unique_information_needs(current)
    seen_items={i.get('key') for i in items if i.get('key')}
    known_needs=[i.get('need') for i in items if i.get('need')]
    for item in (old.get('debug_trace') or {}).get('question_selection',{}).get('opportunities',[]):
        need=item.get('need') or {};key=item.get('key') or need.get('information_fingerprint')
        if item.get('requirement_id') and not same_target:continue
        if key and key not in seen_items|closed and not any(_same_information_need(need,other) for other in known_needs):
            items.append(deepcopy(item));seen_items.add(key)
            if need:known_needs.append(need)


def information_status(records,requirements,delivery,answers,ledger,context,owner_options=()):
    """Read-only lifecycle projection; collected information is not writing success."""
    answered={key:a for a in answers for key in (a.information_need_id,a.information_request_fingerprint) if key}
    statuses={r['experience']['experience_id']:r.get('validation',{}).get('status') for r in records}
    decisions=[];unreviewed=0
    by_delivery={d.get('dedupe_key'):d for d in delivery}
    for record in records:
        owner=record['experience']['experience_id']
        review=(record.get('debug_trace') or {}).get('question_selection',{})
        if review.get('review_state')!='reviewed':unreviewed+=1
        for item in _unique_opportunities(review.get('opportunities',[])):
            row=dict(item,experience_id=owner)
            if row.get('requirement_id') and record.get('requirement_context_hash')!=context:
                row.update(state='not_reviewed',reason='target_context_changed');decisions.append(row);continue
            need=row.get('need') or {};key=row.get('key') or need.get('information_fingerprint')
            need_key=need.get('dedupe_key','');prefix=owner+':value:'
            completed=answered.get(key) or answered.get(need_key) or answered.get(prefix+need_key)
            assigned_to_owner=completed is not None and completed.experience_id in {None,owner}
            issued_unassigned_answer=completed is not None and need.get('owner_scope')=='unassigned' and any(
                entry.get('context_hash')==context and entry.get('requirement_id')==need.get('requirement_id')
                and entry.get('experience_id')==completed.experience_id and entry.get('answer')==completed.answer
                and (entry.get('question_data') or {}).get('owner_scope')=='unassigned'
                and (entry.get('question_data') or {}).get('information_need_id')==need_key
                and (entry.get('question_data') or {}).get('question_id')==completed.question_id
                for entry in ledger)
            if completed and (assigned_to_owner or issued_unassigned_answer):
                from .requirement_matching import answer_disposition
                disposition=answer_disposition(completed.answer)
                row.update(state='unavailable' if disposition in {'absent','unknown'} else 'awaiting_owner' if completed.experience_id is None else 'answered',
                    reason=disposition,writing_status=statuses.get(completed.experience_id),
                    answer_scope='experience' if completed.experience_id else 'applicant')
            elif need.get('dedupe_key') in by_delivery:
                sent=by_delivery[need['dedupe_key']]
                row.update(state='selected' if sent['state']=='displayed' else 'deferred' if sent.get('reason') in {
                    'question_cap','owner_question_cap','requirement_dedupe'} else 'blocked',reason=sent.get('reason') or row.get('reason'))
            decisions.append(row)
    latest={}
    for a in ledger:
        if a.get('context_hash')==context:
            if a.get('experience_id') is not None and a['disposition']=='provided':latest.pop((a['requirement_id'],None),None)
            latest[(a['requirement_id'],a.get('experience_id'))]=a
    requirement_reviews=[]
    for requirement in requirements:
        related=[d for d in decisions if d.get('requirement_id')==requirement.id]
        held=latest.get((requirement.id,None))
        if requirement.kind=='eligibility':state,reason='excluded','eligibility_not_prose'
        elif requirement.status=='met':state,reason='supported','grounded_resume_evidence'
        elif requirement.status=='absent':state,reason='unavailable','global_explicit_absence'
        elif held and held['disposition']=='provided':state,reason='awaiting_owner','answer_not_yet_bound' if owner_options else 'no_existing_owner_item'
        elif held and held['disposition']=='unknown':state,reason='unavailable','global_unknown_not_absence'
        elif related:
            chosen=next((d for d in related if d['state']=='selected'),related[0]);state,reason=chosen['state'],chosen.get('reason')
            if state=='unavailable' and (chosen.get('answer_scope')=='experience' or (chosen.get('need') or {}).get('owner_scope')=='experience'):
                state,reason='not_reviewed','experience_scoped_answer_not_global_absence'
        elif requirement.status=='partial':
            state,reason='partially_supported','grounded_partial_evidence'
        elif requirement.assessment_state=='complete':
            state,reason='unconfirmed','assessed_without_direct_evidence'
        else:state,reason='not_reviewed','assessment_pending'
        requirement_reviews.append(dict(requirement_id=requirement.id,state=state,reason=reason,assessment=requirement.assessment_state))
    unresolved=sum(d['state'] in {'proposed','deferred','selected','blocked','not_reviewed'} for d in decisions)
    waiting=sum(r['assessment']!='complete' or r['state'] in {'blocked','awaiting_owner','deferred','proposed','selected'}
        for r in requirement_reviews)
    return dict(state='pending' if unresolved or waiting or unreviewed else 'resolved',
        unreviewed_experiences=unreviewed,open_opportunities=unresolved,requirements=requirement_reviews,
        decisions=decisions)
