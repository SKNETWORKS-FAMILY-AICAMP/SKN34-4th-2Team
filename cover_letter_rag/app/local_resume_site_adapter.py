"""Local-only UI contract adapter. v2 generates text; v1 storage/apply stays compatible."""
import os
import re
from app.firebase_gateway import FirebaseGateway
from app.models import FirestoreResumeReviewResponse, SentenceReview, ReviewQuestion, ConfirmationAnswer
from app.review_workflow import ReviewConflict, ReviewInputError, digest, item_references
from app.resume_review import extract_review_fields
from app.resume_review_v2.batch import BatchReviewEngine
from app.resume_review_v2.models import (Experience, ReviewInput, Evidence, JobRequirement, Usage,
    EvidenceFacet, SourceDocument, ProjectSlot, ApplicantIntentClaim, SemanticUnit)
from app.resume_review_v2.policy import POLICY_VERSION, MAX_PROGRESSIVE_QUESTIONS


def require_local():
    if os.environ.get('RESUME_REVIEW_ENGINE') != 'v2-local' or os.environ.get('DB_HOST') not in ('127.0.0.1', 'localhost'):
        raise RuntimeError('Local B refuses non-loopback DB / non-v2 configuration')


class LocalGateway(FirebaseGateway):
    def __init__(self, settings):
        require_local()
        self._settings = settings
        self._app = None  # Local JWT proxy requires no Firebase network initialization.

    def _pg(self):
        require_local()
        return super()._pg()

    def review_progress(self, cohort_id, resume_id, uid, request_id, telemetry, tailored_resume_id=None):
        from psycopg.types.json import Jsonb
        legacy = f'{self._resume_legacy(resume_id, tailored_resume_id)}/{request_id}'
        with self._pg() as conn:
            ident = self._cohort_user(conn, cohort_id, uid)
            conn.execute("UPDATE resume_ai_reviews SET telemetry=%s WHERE legacy_id=%s AND user_id=%s AND status='processing'",
                         (Jsonb(telemetry), legacy, ident['user_pk']))
            conn.commit()


def targets(fields):
    """Use experience identity, selecting its narrative field as the apply locator."""
    grouped = {}
    for path, text in fields.items():
        if not text.strip():
            continue
        match = re.match(r'^(projects|experience|trainingExperience|otherActivities)\[(\d+)\]\.(description|text)$', path)
        if match:
            identity = path.rsplit('.', 1)[0]
            grouped[identity] = (path, text, 'project' if match[1] == 'projects' else 'employment' if match[1] == 'experience' else 'activity')
        elif path.startswith('selfIntroduction.') and path.endswith('.body'):
            grouped[path.rsplit('.', 1)[0]] = (path, text, 'other')
        elif path in ('coreCompetencies', 'coreCompetencies.text'):
            grouped[path] = (path, text, 'other')
    return grouped


def experience_sources(content, path, identity):
    """Only the same experience's title/role/technology fields, never other projects."""
    match = re.match(r'^(projects|experience|trainingExperience|otherActivities)\[(\d+)\]', path)
    if not match:
        section = {'motivation': '지원동기', 'aspiration': '입사 후 포부',
                   'strengthsWeaknesses': '장단점', 'growth': '성장과정',
                   'challenge': '도전 경험', 'intro': '자기소개'}
        key = path.split('.')[1] if path.startswith('selfIntroduction.') else ''
        return section.get(key, identity), []
    items = content.get(match[1], [])
    item = items[int(match[2])] if int(match[2]) < len(items) else {}
    if not isinstance(item, dict):
        return identity, []
    sources = []
    for key in ('name', 'title', 'role', 'techStack', 'technologies'):
        value = item.get(key)
        if isinstance(value, list):
            value = ', '.join(v for v in value if isinstance(v, str))
        if isinstance(value, str) and value.strip():
            sources.append(SourceDocument(source_id=f'{identity}:{key}', text=value))
    # Training uses `course` in the regular Resume schema, not name/title.
    # Display context only: retain the stable Experience identity and evidence.
    return (item.get('name') or item.get('title') or
            (item.get('course') if match[1] == 'trainingExperience' else '') or identity), sources


def unavailable_answer(answer):
    return bool(re.fullmatch(r'\s*(?:없음|없다|없어요|없습니다|모름|모른다|모르겠어요|모르겠습니다|기억나지 않습니다)[.!?]*\s*', answer))


class LocalReviewService:
    def __init__(self, settings, gateway, engine=None):
        require_local()
        self.settings, self.db = settings, gateway
        self.engine = engine

    def review_as(self, uid, request):
        require_local()
        db = self.db
        args = (request.cohort_id, request.resume_id, uid)
        tail = request.tailored_resume_id
        resume = db.get_owned_tailored_resume(request.cohort_id, request.resume_id, tail, uid) if tail else db.get_owned_resume(*args)
        content = resume.get('content') or {}
        fields, excluded = extract_review_fields(content)
        content_hash = digest(content)
        if request.expected_input_hash and request.expected_input_hash != content_hash:
            raise ReviewConflict('resume_version_changed')
        previous = db.get_ai_review(*args, request.previous_review_id, tail) if request.previous_review_id else {}
        previous = previous or {}
        # Issued question identity, not client field_path, owns answer routing.
        if request.answers:
            known = {q['question_id']: q for q in previous.get('questions', [])}
            current_refs = item_references(content, fields)
            seen, routed = set(), []
            for answer in request.answers:
                q = known.get(answer.question_id)
                if not q or answer.question_id in seen or answer.field_path != q['field_path']:
                    raise ReviewInputError('unknown, duplicate or mismatched question')
                identity = q.get('experience_id') or previous.get('item_refs', {}).get(q['field_path'])
                if not identity or identity.startswith('legacy:'):
                    raise ReviewInputError('question experience identity required')
                if current_refs.get(q['field_path']) != identity:
                    raise ReviewConflict('resume_item_changed')
                if previous.get('input_hash') != content_hash:
                    raise ReviewConflict('resume_version_changed')
                if answer.experience_id is not None and answer.experience_id != identity:
                    raise ReviewInputError('answer experience does not match question')
                seen.add(answer.question_id)
                routed.append(answer.model_copy(update={'experience_id': identity, 'question': q['question']}))
            request = request.model_copy(update={'answers': routed})
        source, requirements = {}, []
        if request.selected_job_id:
            from app.matching_handoff import load_selected_job
            from app.job_requirements import load_or_extract_requirements
            job = load_selected_job(self.settings.matching_job_store_path, request.selected_job_id)
            source = job['source']
            if request.expected_job_hash and request.expected_job_hash != source['snapshot_hash']:
                raise ReviewConflict('selected_job_changed')
            requirements = load_or_extract_requirements(db, None, job['text'], source)
        elif request.review_mode == 'job':
            raise ReviewInputError('selected_job_required_for_local_B')
        fingerprint = digest([uid, request.model_dump(), content_hash, source, 'v2-local-ui-2', POLICY_VERSION])
        claimed = db.claim_review(*args, request.request_id, fingerprint, tail)
        if claimed.get('response'):
            return FirestoreResumeReviewResponse.model_validate(claimed['response'])
        telemetry = {'engine': 'v2-local-ui-2', 'model': self.settings.openai_model, 'policy_version': POLICY_VERSION,
                     'reasoning_effort': self.settings.openai_reasoning_effort}
        engine = None
        try:
            def progress(state):
                telemetry.update(state)
                db.review_progress(*args, request.request_id, telemetry, tail)
            engine = self.engine or BatchReviewEngine(self.settings.openai_model, self.settings.openai_reasoning_effort,
                                                      on_progress=progress)
            answers = [ConfirmationAnswer.model_validate(a) for a in previous.get('confirmed_answers', [])]
            answers.extend(request.answers)
            chosen = targets(fields)
            refs = item_references(content, fields)
            chosen = {refs[value[0]]: value for value in chosen.values()}
            all_chosen = chosen.copy()
            if request.answers:
                paths = {a.field_path for a in request.answers}
                chosen = {key: value for key, value in chosen.items() if value[0] in paths}
            if not chosen:
                raise ReviewInputError('no_supported_experience_narrative')
            sentences, questions, records = [], [], []
            usage = Usage()
            old_records = previous.get('telemetry', {}).get('v2_results', [])
            inputs = []
            for identity, (path, text, kind) in chosen.items():
                old = next((r for r in old_records if r['experience']['experience_id'] == identity), None)
                evidence = [Evidence.model_validate(e) for e in (old or {}).get('evidence_state', (old or {}).get('extracted_evidence', []))]
                fresh = [a for a in request.answers if a.field_path == path]
                history = [a for a in answers if a.field_path == path and a.experience_id == identity]
                unavailable = set((old or {}).get('unavailable_slots', []))
                answered_keys = list((old or {}).get('answered_question_keys', []))
                for a in fresh:
                    for q in (old or {}).get('gap_questions', []):
                        if q['question'] == a.question:
                            answered_keys.append(q['dedupe_key'])
                            if unavailable_answer(a.answer):
                                unavailable.add(q['target_slot'])
                title, sources = experience_sources(content, path, identity)
                inputs.append(ReviewInput(
                    experience=Experience(experience_id=identity, kind=kind, title=title,
                        current_text=text, field_path=path, content_hash=content_hash, existing_evidence=evidence),
                    question='\n'.join(a.question for a in history), answer='\n'.join(a.answer for a in history),
                    answer_source_id=f'{request.request_id}:{path}' if history else '',
                    question_history=[a.question for a in history],
                    resume_sources=sources,
                    previous_facets=[EvidenceFacet.model_validate(f) for f in (old or {}).get('evidence_facets', [])],
                    existing_intents=[ApplicantIntentClaim.model_validate(c) for c in (old or {}).get('intent_claims', [])],
                    previous_semantic_units=[SemanticUnit.model_validate(u) for u in
                        ((old or {}).get('section_profile') or {}).get('original_semantic_units', [])],
                    unavailable_slots=[ProjectSlot(slot) for slot in unavailable],
                    previous_question_keys=list(dict.fromkeys(answered_keys)),
                    job_requirements=[JobRequirement(requirement_id=r.id, text=r.label, posting_quote=r.posting_quote) for r in requirements],
                ))
            from app.resume_review_v2.audit_resume import input_signature, source_signature, reusable_record, sources_changed
            resume_records = {}
            if request.review_phase == 'gap_audit' and isinstance(engine, BatchReviewEngine):
                for index, review_input in enumerate(inputs):
                    identity = review_input.experience.experience_id
                    old = next((r for r in old_records if r['experience']['experience_id'] == identity), None)
                    if reusable_record(review_input, old, previous, source,
                                       self.settings.openai_model, self.settings.openai_reasoning_effort):
                        resume_records[identity] = old
                    elif sources_changed(review_input, old):
                        # Rebuild changed source material from current text and
                        # complete owning answer history, not unchecked old quotes.
                        clean = review_input.model_copy(deep=True)
                        clean.experience.existing_evidence = []
                        clean.previous_facets, clean.existing_intents, clean.previous_semantic_units = [], [], []
                        inputs[index] = clean
                results = engine.run_many(inputs, resume_records=resume_records)
                verifying = sum(any(i.get('code') == 'verification_unavailable'
                    for i in r['validation'].get('factual_issues', [])) for r in resume_records.values())
                telemetry['audit_resume'] = dict(reused_experiences=len(resume_records),
                    completed_reused=len(resume_records) - verifying, verification_resumed=verifying,
                    reprocessed_experiences=len(inputs) - len(resume_records))
            else:
                results = engine.run_many(inputs)
            for review_input, result in zip(inputs, results, strict=True):
                identity = review_input.experience.experience_id
                path, text, kind = chosen[identity]
                evidence = review_input.experience.existing_evidence
                record = result.model_dump(mode='json')
                # Preserve atomic facts from earlier turns, including supersession.
                from app.resume_review_v2.models import AnalystOutput
                from app.resume_review_v2.validation import validate_analysis
                state, _ = validate_analysis(review_input.model_copy(update={'section_profile': result.section_profile}),
                    AnalystOutput(experience_id=identity, extracted_evidence=result.extracted_evidence,
                        plan=result.plan, question=result.proposed_question))
                record['evidence_state'] = [e.model_dump(mode='json') for e in state.values()]
                if any(i.code == 'analysis_contract_invalid' for i in result.validation.all_issues):
                    # A failed delta is not a replacement snapshot. Retain the
                    # last approved intent/meaning state so a later retry can use it.
                    old = next((r for r in old_records if r['experience']['experience_id'] == identity), {})
                    for key in ('intent_claims', 'section_profile', 'sentence_plan', 'evidence_facets', 'project_profile'):
                        if key in old:
                            record[key] = old[key]
                # Unanswered questions remain eligible after recomputation; only
                # answered identities are suppressed across turns.
                record['answered_question_keys'] = review_input.previous_question_keys
                record['audit_source_hash'] = source_signature(review_input)
                record['audit_input_hash'] = input_signature(review_input, source,
                    self.settings.openai_model, self.settings.openai_reasoning_effort, record)
                records.append(record)
                for key in ('calls', 'input_tokens', 'output_tokens', 'latency_ms'):
                    setattr(usage, key, getattr(usage, key) + getattr(result.usage, key))
                candidate = result.candidate
                ready = candidate is not None and result.validation.status == 'READY'
                unchanged = result.validation.status == 'UNCHANGED'
                question = result.proposed_question
                sentences.append(SentenceReview(field_path=path, original_quote=text,
                    reason='원문보다 명확한 개선이 없어 원문을 유지했습니다.' if unchanged else result.plan.reason or result.plan.objective,
                    suggested_revision=candidate.suggested_text if ready else None,
                    validation_status=('UNCHANGED' if candidate is None and result.proposed_question is None
                        and result.validation.status == 'READY' else result.validation.status),
                    status='improved' if ready else 'unchanged' if unchanged else 'needs_confirmation' if question else 'unchanged',
                    confirmation_question=question.question if question else None,
                    evidence_quotes=[e.evidence_quote for e in result.selected_evidence],
                    validation_issues=[i.code for i in result.validation.all_issues]))
            refreshed = {r['experience']['experience_id'] for r in records}
            records.extend(r for r in old_records if r['experience']['experience_id'] not in refreshed)
            # At most three questions for the whole Resume, not three per project.
            # Untouched experiences keep their pending gaps when one field is answered.
            from app.resume_review_v2.models import GapQuestion
            from app.resume_review_v2.question_planning import approved_question
            for record in records:
                identity = record['experience']['experience_id']
                if identity not in all_chosen:
                    continue
                path = all_chosen[identity][0]
                display_title, _ = experience_sources(content, path, identity)
                answered_keys = set(record.get('answered_question_keys', []))
                state = {e['evidence_id']: Evidence.model_validate(e) for e in
                         record.get('evidence_state', record.get('extracted_evidence', []))}
                for raw in record.get('gap_questions', []):
                    # Upgrade old stored B questions only from their owning record.
                    q = GapQuestion.model_validate({
                        'experience_id': identity, 'experience_title': record['experience']['title'], **raw})
                    if q.experience_id != identity:
                        raise ReviewInputError('question experience does not match record')
                    if q.dedupe_key in answered_keys:
                        continue
                    # Legacy slot-fill questions have never been evaluated for
                    # marginal editing value. Do not replay them as approved.
                    if not q.dedupe_key.startswith(identity + ':value:') or not approved_question(q, state):
                        continue
                    questions.append(ReviewQuestion(question_id=f'{request.request_id}:v2gap:{digest(q.dedupe_key)[:16]}',
                        experience_id=identity, experience_title=display_title,
                        target_slot=q.target_slot.value, evidence_basis=q.evidence_basis,
                        field_path=path, topic='other', question=q.question, reason=q.why_needed,
                        priority=1 if q.priority == 'HIGH' else 2))
            questions = sorted(questions, key=lambda q: q.priority)[:MAX_PROGRESSIVE_QUESTIONS]
            telemetry.update(usage.model_dump(), v2_results=records)
            telemetry['stages'] = engine.stages if isinstance(engine, BatchReviewEngine) else []
            telemetry['attempted_calls'] = engine.attempted_calls if isinstance(engine, BatchReviewEngine) else usage.calls
            from app.job_requirements import RequirementStatusRow
            requirement_rows = [RequirementStatusRow(**r.model_dump(), status='unconfirmed').model_dump() for r in requirements]
            summary = '경험 근거와 문장 흐름을 검토했습니다.'
            kept = sum(r['validation']['status'] == 'UNCHANGED' for r in records if r['experience']['experience_id'] in chosen)
            if kept:
                summary += f' 원문보다 명확한 개선이 없는 {kept}개 항목은 원문을 유지했습니다.'
            response = FirestoreResumeReviewResponse(summary=summary,
                section_reviews=[], sentence_reviews=sentences, questions=questions,
                confirmation_questions=[q.question for q in questions], review_id=request.request_id,
                cohort_id=request.cohort_id, resume_id=request.resume_id, tailored_resume_id=tail,
                input_fields=fields, input_hash=content_hash, item_refs=item_references(content, fields),
                excluded_fields=excluded, confirmed_answers=answers, job_source=source, telemetry=telemetry,
                requirement_map=requirement_rows)
            db.complete_review(*args, request.request_id, response.model_dump(mode='json'), tail)
            return response
        except Exception as exc:
            telemetry['error_type'] = type(exc).__name__
            if isinstance(engine, BatchReviewEngine):
                telemetry.update(engine.usage.model_dump(), stages=engine.stages,
                                 attempted_calls=engine.attempted_calls)
            db.fail_review(*args, request.request_id, telemetry, tail)
            raise
