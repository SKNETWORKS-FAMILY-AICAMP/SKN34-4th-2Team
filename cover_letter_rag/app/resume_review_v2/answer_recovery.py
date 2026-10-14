"""Pure answer-state repair in existing review JSON. No I/O or model calls."""
from copy import deepcopy
import re
from app.review_workflow import ReviewConflict, ReviewInputError, digest


def repeats_question(question, answer):
    normalize = lambda text: re.sub(r'\W+', '', text).casefold()
    return bool(normalize(question)) and normalize(question) == normalize(answer)


def repair_answer(previous, change, issued, fields, current_refs):
    result = deepcopy(previous)
    answers = result.get('confirmed_answers', [])
    matches = [a for a in answers if a.get('question_id') == change.question_id]
    held = [a for a in result.get('telemetry',{}).get('requirement_answers',[])
        if a.get('experience_id') is None and (a.get('question_data') or {}).get('question_id')==change.question_id]
    if not matches and len(held)==1:
        latest = next(a for a in reversed(result['telemetry']['requirement_answers']) if a['requirement_id']==held[0]['requirement_id'])
        if latest.get('experience_id') is not None or (latest.get('question_data') or {}).get('question_id') != change.question_id:
            raise ReviewConflict('answer_state_changed')
        q = held[0]['question_data']
        matches = [dict(question_id=change.question_id,experience_id=None,field_path=q['field_path'],question=q['question'],answer=held[0]['answer'])]
    if len(matches) != 1 or matches[0]['answer'] != change.expected_answer:
        raise ReviewConflict('answer_state_changed')
    old = matches[0]
    if not issued or issued.get('question_id') != change.question_id or issued.get('question') != old['question']:
        raise ReviewInputError('issued_answer_question_unavailable')
    identity, path = old.get('experience_id'), old['field_path']
    if identity is None and issued.get('owner_scope') == 'unassigned':
        from .requirement_matching import answer_disposition
        replacement = (change.answer or '').strip()
        if change.operation=='replace' and (not replacement or repeats_question(old['question'],replacement)):
            raise ReviewInputError('answer_repeats_question' if replacement else 'answer_required')
        telemetry=result.setdefault('telemetry',{})
        telemetry['requirement_answers']=[a for a in telemetry.get('requirement_answers',[])
            if (a.get('question_data') or {}).get('question_id')!=change.question_id]
        telemetry.setdefault('answer_changes',[]).append(dict(question_id=change.question_id,experience_id=None,
            field_path=path,operation=change.operation,question_data=deepcopy(issued),previous_answer_hash=digest(old['answer'])))
        result['questions']=[q for q in result.get('questions',[]) if q.get('requirement_id')!=issued.get('requirement_id')]
        if change.operation=='retract':
            result['questions'].append({k:v for k,v in issued.items() if not k.startswith('_')})
        else:
            disposition=answer_disposition(replacement)
            telemetry['requirement_answers'].append({**held[0],'answer':replacement,'disposition':disposition})
            if disposition=='provided':
                owner={k:v for k,v in issued.items() if not k.startswith('_')}
                owner['question_id']='__owner_after_edit__:'+str(issued.get('requirement_id'))
                owner['information_need_id']='ownership:'+str(issued.get('requirement_context_hash'))+':'+str(issued.get('requirement_id'))
                owner['information_request_fingerprint']=owner['information_need_id']
                owner['question']='수정한 답변이 속한 경험 항목을 선택해 주세요.'
                result['questions'].append(owner)
        telemetry.pop('stage_checkpoint',None)
        telemetry['answer_recovery']=dict(question_id=change.question_id,experience_id=None,field_path=path,
            operation=change.operation,document_unchanged=True,requires_document_undo=False)
        return result  # Held text never becomes any Experience's Evidence.
    if not identity or identity.startswith('legacy:') or current_refs.get(path) != identity:
        raise ReviewConflict('resume_item_changed')
    replacement = (change.answer or '').strip()
    if change.operation == 'replace' and (not replacement or repeats_question(old['question'], replacement)):
        raise ReviewInputError('answer_repeats_question' if replacement else 'answer_required')
    answers.remove(old)
    if change.operation == 'replace':
        answers.append({**old, 'answer':replacement})
    telemetry = result.setdefault('telemetry', {})
    ledger = telemetry.setdefault('answer_changes', [])
    ledger.append(dict(question_id=change.question_id, experience_id=identity, field_path=path,
        operation=change.operation, previous_answer_hash=digest(old['answer']),
        answer_hash=digest(replacement) if change.operation == 'replace' else None,
        question_data=deepcopy(issued)))
    telemetry.pop('stage_checkpoint', None)
    telemetry['requirement_answers'] = [a for a in telemetry.get('requirement_answers', [])
        if (a.get('question_data') or {}).get('question_id') != change.question_id]
    record = next((r for r in telemetry.get('v2_results', []) if r['experience']['experience_id'] == identity), None)
    if record is None:
        raise ReviewInputError('answer_experience_state_unavailable')
    remaining = '\n'.join(a['answer'] for a in answers if a.get('experience_id') == identity)
    other_answers = '\n'.join(a['answer'] for a in answers
        if a.get('experience_id') == identity and a.get('question_id') != change.question_id)
    # Retract source assertions, not all facts with the same meaning. Distinct
    # original/other-answer assertions stay active; extraction can reuse them.
    withdrawn = set()
    for fact in record.get('evidence_state', []):
        if (fact['source_type'] == 'user_answer'
                and (fact['evidence_quote'] not in remaining
                    or (fact['evidence_quote'] in old['answer']
                        and fact['evidence_quote'] not in other_answers))):
            fact['assertion_state'] = 'retracted'
            withdrawn.add(fact['evidence_id'])
            fact['supersedes_evidence_ids'] = []
            fact['conflicts_with_evidence_ids'] = []
    for fact in record.get('evidence_state', []):
        fact['conflicts_with_evidence_ids'] = [eid for eid in fact.get('conflicts_with_evidence_ids',[]) if eid not in withdrawn]
    for claim in record.get('intent_claims', []):
        if (claim['source_type'] == 'user_answer'
                and (claim['evidence_quote'] not in remaining
                    or (claim['evidence_quote'] in old['answer']
                        and claim['evidence_quote'] not in other_answers))):
            claim['state'] = 'retracted'
            claim['supersedes_intent_ids'] = []
    receipt = record.get('verified_apply')
    source_proof=record.get('source_provenance') or receipt
    candidate = record.get('candidate') or (receipt or {}).get('completed_candidate')
    applied = bool(issued.get('_answer_was_applied') or candidate and
        candidate.get('validation',{}).get('status') == 'READY' and
        candidate.get('suggested_text') != candidate.get('original_quote') and candidate.get('suggested_text') == fields.get(path))
    guard = record.get('answer_edit_guard')
    if applied and not guard:
        guard = dict(safe_before_text=issued.get('_answer_source_text'), field_path=path,
                     question_id=change.question_id)
    record.pop('verified_apply', None)
    record.pop('source_provenance', None)
    safe_text=(guard or {}).get('safe_before_text') if guard else fields.get(path)
    while source_proof and source_proof.get('completed_candidate',{}).get('suggested_text')!=safe_text:
        source_proof=source_proof.get('parent_provenance')
    if source_proof:record['source_provenance']=source_proof
    record['candidate'] = None
    record['validation'] = dict(status='NEEDS_EVIDENCE', factual_issues=[], intent_issues=[],
        section_issues=[], quality_issues=[dict(code='answer_state_changed',detail='답변 근거가 변경되어 재검토가 필요합니다.')])
    record['plan'] = dict(objective='답변 변경 후 재검토', operation='no_change', reason='답변 근거 변경')
    record['extracted_evidence'] = [];record['selected_evidence'] = []
    record['section_profile'] = None;record['sentence_plan'] = None
    record['evidence_facets'] = [];record['project_profile'] = None;record['gap_questions'] = []
    record['requirement_matches'] = None;record['requirement_warnings'] = []
    record['unavailable_slots'] = [slot for slot in record.get('unavailable_slots',[])
        if slot != issued.get('target_slot') or any(re.fullmatch(r'\s*(?:없음|없다|없어요|없습니다)[.!?]*\s*',a['answer'])
            for a in answers if a.get('experience_id')==identity)]
    record['answered_question_keys'] = [k for k in record.get('answered_question_keys', []) if k not in
        {issued.get('_answer_dedupe_key'),issued.get('_answer_information_fingerprint')}]
    if change.operation == 'replace' and issued.get('_answer_dedupe_key'):
        record['answered_question_keys'].append(issued['_answer_dedupe_key'])
        if issued.get('_answer_information_fingerprint'):record['answered_question_keys'].append(issued['_answer_information_fingerprint'])
    if change.operation == 'replace' and issued.get('requirement_id'):
        from .requirement_matching import answer_disposition
        telemetry['requirement_answers'].append(dict(requirement_id=issued['requirement_id'],experience_id=identity,
            disposition=answer_disposition(replacement),answer=replacement,question_data=deepcopy(issued),
            context_hash=issued.get('requirement_context_hash')))
    record['answer'] = remaining
    record['question'] = '\n'.join(a['question'] for a in answers if a.get('experience_id') == identity)
    record['answer_state_invalidated'] = True
    record['audit_input_hash'] = '';record['audit_source_hash'] = ''
    if guard:record['answer_edit_guard'] = guard
    prior_review=(record.get('debug_trace') or {}).get('question_selection',{})
    record['debug_trace'] = dict(answer_recovery={'question_id':change.question_id,'operation':change.operation},
        question_selection={**prior_review,'review_state':'not_reviewed','review_reason':'answer_state_changed'})
    result['questions'] = [q for q in result.get('questions', []) if q.get('experience_id') != identity]
    if change.operation == 'retract':
        result['questions'].append({k:v for k,v in issued.items() if not k.startswith('_')})
    result['sentence_reviews'] = [s for s in result.get('sentence_reviews', []) if s.get('field_path') != path
        and s.get('original_quote') == fields.get(s.get('field_path'))]
    result['star_checks'] = [s for s in result.get('star_checks', []) if s.get('field_path') != path]
    telemetry['answer_recovery'] = dict(question_id=change.question_id,experience_id=identity,field_path=path,
        operation=change.operation,document_unchanged=True,requires_document_undo=bool(guard))
    return result
