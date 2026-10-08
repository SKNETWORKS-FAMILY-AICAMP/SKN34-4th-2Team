"""Shared v2 runtime using the existing PostgreSQL review/apply contract."""
import re
import time
from contextlib import contextmanager
from app.firebase_gateway import FirebaseGateway
from app.models import FirestoreResumeReviewResponse, SentenceReview, ReviewQuestion, ConfirmationAnswer
from app.review_workflow import ReviewConflict, ReviewInputError, digest, item_references
from app.resume_review import extract_review_fields
from app.resume_review_v2.batch import BatchReviewEngine, StageBoundary
from app.resume_review_v2.models import (Experience, ReviewInput, Evidence, JobRequirement, Usage,
    EvidenceFacet, SourceDocument, ProjectSlot, ApplicantIntentClaim, SemanticUnit)
from app.resume_review_v2.policy import POLICY_VERSION, MAX_PROGRESSIVE_QUESTIONS


def public_gap_question(q, request_id, path, title, owner_options=(), requirement_context=''):
    """Pure mapping shared by live delivery and offline presentation inspection."""
    from app.resume_review_v2.requirement_matching import UNASSIGNED_PATH
    from app.resume_review_v2.question_planning import public_question_reason
    return ReviewQuestion(question_id=f'{request_id}:v2gap:{digest(q.dedupe_key)[:16]}',
        question_contract=q.contract,information_need_id=q.dedupe_key,
        target_contexts=q.target_contexts,information_request_fingerprint=q.information_fingerprint,
        information_aspect=q.request_aspect,
        experience_id=None if q.owner_scope=='unassigned' else q.experience_id,
        experience_title='' if q.owner_scope=='unassigned' else title,
        target_slot=q.target_slot.value,evidence_basis=q.evidence_basis,
        field_path=UNASSIGNED_PATH if q.owner_scope=='unassigned' else path,
        owner_scope=q.owner_scope,owner_options=list(owner_options) if q.owner_scope=='unassigned' else [],
        requirement_id=q.requirement_id,requirement_context_hash=requirement_context if q.requirement_id else '',
        topic='other',question=q.question,reason=public_question_reason(),priority=1 if q.priority=='HIGH' else 2)


def answer_question_context(answer):
    # Historical UI reference IDs are not the current Analyze namespace. Keep
    # the asked information and literal target, never send old ID objects as facts.
    contexts=[]
    for context in answer.question_target_contexts:
        quote=context.get('quote')
        if quote:contexts.append(('공고 원문' if context.get('type')=='posting_source' else '질문 대상 원문')+': '+quote)
    return '\n'.join([answer.question,*contexts])


def experience_outcomes(records, refs, fields, source_for=None):
    """Small public latest-state projection, not historical messages/debug data."""
    outcomes=[]
    for record in records:
        exp=record.get('experience',{});owner=exp.get('experience_id');path=exp.get('field_path')
        if not owner or refs.get(path)!=owner:continue
        status=record.get('validation',{}).get('status')
        if record.get('answer_state_invalidated') or exp.get('current_text')!=fields.get(path):
            status='NEEDS_EVIDENCE'
        elif source_for and record.get('audit_source_hash'):
            from app.resume_review_v2.audit_resume import source_signature
            title,sources=source_for(path,owner)
            current=ReviewInput(experience=Experience.model_validate(exp).model_copy(update={'title':title}),resume_sources=sources)
            if source_signature(current)!=record['audit_source_hash']:status='NEEDS_EVIDENCE'
        outcomes.append(dict(experience_id=owner,field_path=path,status=status))
    return outcomes


def historical_source_proof(review_input,record,db,args,tail,previous,source,requirement_context,settings,cache):
    from app.resume_review_v2.audit_resume import applied_provenance
    receipt=(record or {}).get('source_provenance') or (record or {}).get('verified_apply')
    guard=(record or {}).get('answer_edit_guard')
    if not receipt or guard and review_input.experience.current_text!=guard.get('safe_before_text'):return None,None
    op_id=receipt.get('operation_id')
    if op_id not in cache:cache[op_id]=db.get_verified_application(*args,op_id,tail)
    operation=cache[op_id]
    roots=applied_provenance(review_input,record,previous,source,requirement_context,
        settings.openai_model,settings.openai_reasoning_effort,operation)
    return roots,operation


class PostgresReviewGateway(FirebaseGateway):
    supports_stage_checkpoints = True
    def __init__(self, settings):
        self._settings = settings
        self._app = None  # Django authenticates proxy requests; direct token routes initialize lazily.

    def verify_id_token(self, id_token):
        from app.firebase_gateway import FirebaseAuthenticationError
        if not self._settings.firebase_project_id:
            raise FirebaseAuthenticationError("Direct token authentication is not configured")
        if self._app is None:
            self._app = self._initialize_app(self._settings)
        return super().verify_id_token(id_token)

    def latest_review_response(self, cohort_id, resume_id, uid, tailored_resume_id=None):
        prefix = self._resume_legacy(resume_id, tailored_resume_id) + '/'
        with self._pg() as conn:
            ident = self._cohort_user(conn, cohort_id, uid)
            row = conn.execute('SELECT response FROM resume_ai_reviews WHERE user_id=%s AND left(legacy_id,length(%s))=%s AND response IS NOT NULL ORDER BY id DESC LIMIT 1',
                (ident['user_pk'],prefix,prefix)).fetchone()
        return row[0] if row else None

    def apply_or_undo(self, uid, request, undo=False):
        # The existing per-resume advisory lock also serializes answer recovery
        # against apply/undo: a stale candidate cannot slip between the answer
        # version check and the document transaction.
        with self.review_execution(request.cohort_id,request.resume_id,uid,request.tailored_resume_id):
            return self._apply_with_answer_state(uid,request,undo)

    def _apply_with_answer_state(self, uid, request, undo=False):
        if not undo:
            latest = self.latest_review_response(request.cohort_id,request.resume_id,uid,request.tailored_resume_id) or {}
            source = self.get_ai_review(request.cohort_id,request.resume_id,uid,request.review_id,request.tailored_resume_id)
            changed = {e['field_path'] for e in latest.get('telemetry',{}).get('answer_changes',[])}
            for index in request.selected_indices:
                edits = source.get('sentence_reviews',[])
                if 0 <= index < len(edits) and edits[index].get('field_path') in changed:
                    path = edits[index]['field_path']
                    old = [a for a in source.get('confirmed_answers',[]) if a['field_path']==path]
                    new = [a for a in latest.get('confirmed_answers',[]) if a['field_path']==path]
                    if old != new:raise ReviewConflict('answer_state_changed')
        return super().apply_or_undo(uid,request,undo=undo)

    def answer_was_applied(self, cohort_id,resume_id,uid,question_id,path,tailored_resume_id=None):
        prefix = self._resume_legacy(resume_id,tailored_resume_id) + '/'
        with self._pg() as conn:
            ident = self._cohort_user(conn,cohort_id,uid)
            # Applications store the request ID, while reviews use a scoped
            # legacy path. Keep both sides in the same resume/user namespace.
            rows = conn.execute('SELECT r.response,a.payload FROM resume_ai_applications a JOIN resume_ai_reviews r ON r.legacy_id=%s || a.source_id AND r.user_id=a.user_id AND r.resume_id=a.resume_id WHERE a.user_id=%s AND a.kind=%s AND a.undone_by IS NULL AND left(a.legacy_id,length(%s))=%s',
                (prefix,ident['user_pk'],'apply',prefix,prefix)).fetchall()
        for response,payload in rows:
            if any(a.get('question_id')==question_id and a['field_path']==path for a in (response or {}).get('confirmed_answers',[])):
                edits = (response or {}).get('sentence_reviews',[])
                if any(0 <= i < len(edits) and edits[i].get('field_path')==path for i in (payload or {}).get('selected_indices',[])):
                    return True
        return False

    def get_verified_application(self, cohort_id, resume_id, uid, operation_id, tailored_resume_id=None):
        """Read an existing owned apply event; never creates/repairs data."""
        legacy = f'{self._resume_legacy(resume_id,tailored_resume_id)}/{operation_id}'
        with self._pg() as conn:
            ident = self._cohort_user(conn,cohort_id,uid)
            row = conn.execute('SELECT kind, undone_by, source_id, before, after_hash, payload FROM resume_ai_applications WHERE legacy_id=%s AND user_id=%s',
                (legacy,ident['user_pk'])).fetchone()
        if not row:
            return None
        event = dict(zip(('kind','undone_by','source_id','before','after_hash','payload'),row))
        payload = event['payload'] or {}
        if (payload.get('cohort_id') != cohort_id or payload.get('resume_id') != resume_id
                or payload.get('tailored_resume_id') != tailored_resume_id):
            return None
        return event

    @contextmanager
    def review_execution(self, cohort_id, resume_id, uid, tailored_resume_id=None):
        # Session advisory lock is released by PostgreSQL on process death. No
        # lease expiry can allow an old live worker and a new worker concurrently.
        lock_id = int(digest([cohort_id, resume_id, uid, tailored_resume_id])[:15], 16)
        with self._pg() as conn:
            self._cohort_user(conn, cohort_id, uid)
            if not conn.execute('SELECT pg_try_advisory_lock(%s)', (lock_id,)).fetchone()[0]:
                raise ReviewConflict('review_stage_busy')
            try:
                yield
            finally:
                conn.execute('SELECT pg_advisory_unlock(%s)', (lock_id,))

    def claim_review(self, cohort_id, resume_id, uid, request_id, fingerprint, tailored_resume_id=None):
        prefix = self._resume_legacy(resume_id, tailored_resume_id) + '/'
        legacy = prefix + request_id
        with self._pg() as conn:
            ident = self._cohort_user(conn, cohort_id, uid)
            rows = conn.execute('''SELECT legacy_id, fingerprint, response, telemetry FROM resume_ai_reviews
                WHERE user_id=%s AND (legacy_id=%s OR (left(legacy_id,length(%s))=%s AND fingerprint=%s))
                ORDER BY (legacy_id=%s) DESC, id DESC LIMIT 1''',
                (ident['user_pk'], legacy, prefix, prefix, fingerprint, legacy)).fetchall()
            if rows:
                canonical, saved_fingerprint, response, telemetry = rows[0]
                if saved_fingerprint != fingerprint:
                    raise ReviewConflict('request_id_reused_with_different_input')
                if response:
                    return {'response': response, 'request_id': canonical[len(prefix):]}
                conn.execute("UPDATE resume_ai_reviews SET status='processing' WHERE legacy_id=%s AND user_id=%s",
                    (canonical, ident['user_pk']))
                conn.commit()
                return {'checkpoint': (telemetry or {}).get('stage_checkpoint', {}),
                    'telemetry': telemetry or {}, 'request_id': canonical[len(prefix):]}
        return super().claim_review(cohort_id, resume_id, uid, request_id, fingerprint, tailored_resume_id)

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
    # Explicit absence retains the existing slot backstop. Unknown/forgotten
    # information closes the issued need via answered keys/history, not an
    # entire facet (which may contain other independently valuable questions).
    return bool(re.fullmatch(r'\s*(?:없음|없다|없어요|없습니다)[.!?]*\s*', answer))


class ResumeReviewV2Service:
    supports_answer_changes = True
    allow_requirement_extraction = True

    def __init__(self, settings, gateway, engine=None):
        self.settings, self.db = settings, gateway
        self.engine = engine

    def review(self, id_token, request):
        return self.review_as(self.db.verify_id_token(id_token), request)

    def load_requirements(self, job):
        from app.job_requirements import build_requirement_extractor, load_or_extract_requirements
        rows = load_or_extract_requirements(self.db, None, job["text"], job["source"])
        if not rows and self.allow_requirement_extraction:
            rows = load_or_extract_requirements(self.db, build_requirement_extractor(self.settings, timeout=45), job["text"], job["source"])
        return rows

    def review_as(self, uid, request):
        if getattr(self.db, 'supports_stage_checkpoints', False) is True:
            with self.db.review_execution(request.cohort_id, request.resume_id, uid, request.tailored_resume_id):
                return self._review_as(uid, request)
        return self._review_as(uid, request)

    def _review_as(self, uid, request):
        request_started = time.monotonic()
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
        from app.resume_review_v2.requirement_matching import UNASSIGNED_PATH, context_hash, aggregate, answer_disposition
        answer_links = []
        # Issued question identity, not client field_path, owns answer routing.
        if request.answers:
            known = {q['question_id']: q for q in previous.get('questions', [])}
            current_refs = item_references(content, fields)
            seen, routed = set(), []
            for answer in request.answers:
                q = known.get(answer.question_id)
                if not q or answer.question_id in seen:
                    raise ReviewInputError('unknown, duplicate or mismatched question')
                if q.get('question_contract') != 'evidence-need-v2':
                    raise ReviewConflict('question_contract_changed')
                from app.resume_review_v2.answer_recovery import repeats_question
                if repeats_question(q['question'],answer.answer):
                    raise ReviewInputError('answer_repeats_question')
                if q.get('owner_scope') == 'unassigned':
                    choice = next((o for o in q.get('owner_options', []) if o['experience_id'] == answer.experience_id
                                   and o['field_path'] == answer.field_path), None)
                    if answer.experience_id is not None:
                        if (choice is None or choice['experience_id'].startswith('legacy:')
                                or current_refs.get(choice['field_path']) != choice['experience_id']):
                            raise ReviewInputError('unissued or stale requirement owner selection')
                        identity = choice['experience_id']
                        if ':owner:' in q['question_id']:
                            pending = next((a for a in reversed(previous.get('telemetry', {}).get('requirement_answers', []))
                                if a.get('requirement_id') == q.get('requirement_id') and a.get('experience_id') is None
                                and a.get('disposition') == 'provided' and a.get('context_hash') == q.get('requirement_context_hash')), None)
                            if pending:
                                answer = answer.model_copy(update={'answer':pending['answer'] + '\n' + answer.answer})
                    else:
                        if answer.field_path != UNASSIGNED_PATH:
                            raise ReviewInputError('unassigned answer must not target an experience')
                        identity = None
                    if previous.get('input_hash') != content_hash:
                        raise ReviewConflict('resume_version_changed')
                    seen.add(answer.question_id)
                    routed.append(answer.model_copy(update={'experience_id':identity,'question':q['question'],
                        'question_target_contexts':q.get('target_contexts',[]),
                        'information_need_id':q.get('information_need_id'),'information_request_fingerprint':q.get('information_request_fingerprint'),
                        'information_aspect':q.get('information_aspect')}))
                    answer_links.append((q, routed[-1]))
                    continue
                if answer.field_path != q['field_path']:
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
                routed.append(answer.model_copy(update={'experience_id': identity, 'question': q['question'],
                    'question_target_contexts':q.get('target_contexts',[]),
                    'information_need_id':q.get('information_need_id'),'information_request_fingerprint':q.get('information_request_fingerprint'),
                    'information_aspect':q.get('information_aspect')}))
                answer_links.append((q, routed[-1]))
            request = request.model_copy(update={'answers': routed})
        source, requirements = {}, []
        if request.selected_job_id:
            from app.matching_handoff import load_selected_job
            job = load_selected_job(self.settings.matching_job_store_path, request.selected_job_id)
            source = job['source']
            if request.expected_job_hash and request.expected_job_hash != source['snapshot_hash']:
                raise ReviewConflict('selected_job_changed')
            requirements = self.load_requirements(job)
        elif request.review_mode == 'job':
            raise ReviewInputError('selected_job_required')
        requirement_context = context_hash(source, requirements)
        application_cache={}
        def source_proof(review_input,record):
            return historical_source_proof(review_input,record,db,args,tail,previous,source,requirement_context,self.settings,application_cache)
        def provenance_for(review_input,record):return source_proof(review_input,record)[0]
        requirement_answers = [a for a in previous.get('telemetry', {}).get('requirement_answers', [])
                               if a.get('context_hash') == requirement_context]
        for q, answer in answer_links:
            rid = q.get('requirement_id')
            if not rid:
                continue
            if (rid not in {r.id for r in requirements} or q.get('requirement_context_hash') != requirement_context):
                raise ReviewConflict('requirement_question_context_changed')
            requirement_answers.append(dict(requirement_id=rid, experience_id=answer.experience_id,
                disposition=answer_disposition(answer.answer),answer=answer.answer, question_data=q,
                context_hash=requirement_context))
        from app.resume_review_v2.audit_resume import PIPELINE_VERSION
        fingerprint = digest([uid, request.model_dump(exclude={'request_id'}), content_hash, source,
            [r.model_dump(mode='json') for r in requirements],
            'v2-local-ui-2', POLICY_VERSION, PIPELINE_VERSION, self.settings.openai_model, self.settings.openai_reasoning_effort])
        claimed = db.claim_review(*args, request.request_id, fingerprint, tail)
        if claimed.get('response'):
            response = FirestoreResumeReviewResponse.model_validate(claimed['response'])
            response.telemetry['answer_edit_supported'] = True
            response.telemetry['experience_outcomes']=experience_outcomes(
                response.telemetry.get('v2_results',[]),item_references(content,fields),fields,
                lambda path,owner:experience_sources(content,path,owner))
            from app.resume_review_v2.star_diagnostics import original_star_checks
            response.star_checks = original_star_checks(response.telemetry.get('v2_results', []),
                fields, content_hash, lambda path, identity: experience_sources(content, path, identity),
                item_references(content, fields))
            response.requirement_map = [r.model_dump(mode='json') for r in aggregate(requirements,
                response.telemetry.get('v2_results', []), fields, content_hash, source,
                lambda path, identity: experience_sources(content, path, identity), item_references(content, fields),
                response.telemetry.get('requirement_answers', []),provenance_for=provenance_for)]
            from app.resume_review_v2.question_planning import information_status
            from app.job_requirements import RequirementStatusRow
            response.telemetry['information_review']=information_status(response.telemetry.get('v2_results',[]),
                [RequirementStatusRow.model_validate(r) for r in response.requirement_map],
                response.telemetry.get('question_delivery',[]),response.confirmed_answers,
                response.telemetry.get('requirement_answers',[]),requirement_context)
            return response
        if claimed.get('request_id'):
            request = request.model_copy(update={'request_id': claimed['request_id']})
        if request.answer_changes:
            if request.answers or not request.previous_review_id:
                raise ReviewInputError('invalid_answer_change')
            latest = db.latest_review_response(*args,tail) or {}
            if latest.get('review_id') != request.previous_review_id:
                raise ReviewConflict('answer_state_changed')
            change = request.answer_changes[0]
            origin = db.get_ai_review(*args,change.question_id.split(':')[0],tail) or {}
            issued = next((q for q in origin.get('questions',[]) if q.get('question_id')==change.question_id),None)
            if issued is None:
                issued = next((e.get('question_data') for e in previous.get('telemetry',{}).get('answer_changes',[])
                    if e.get('question_id')==change.question_id),None)
            if issued:
                issued = dict(issued)
                owning = next((r for r in origin.get('telemetry',{}).get('v2_results',[])
                    if r['experience']['experience_id']==issued.get('experience_id')),None)
                if owning:
                    issued['_answer_source_text'] = owning['experience']['current_text']
                    issued['_answer_dedupe_key'] = issued.get('information_need_id')
                    issued['_answer_information_fingerprint'] = issued.get('information_request_fingerprint')
                answer = next((a for a in previous.get('confirmed_answers',[]) if a.get('question_id')==change.question_id),{})
                issued['_answer_was_applied'] = db.answer_was_applied(*args,change.question_id,answer.get('field_path'),tail) is True
            from app.resume_review_v2.answer_recovery import repair_answer
            repaired = repair_answer(previous,change,issued,fields,item_references(content,fields))
            repaired['questions'] = [q for q in repaired.get('questions',[]) if q.get('question_contract')=='evidence-need-v2']
            for q in repaired.get('questions',[]):
                if q.get('question_id','').startswith('__owner_after_edit__:'):
                    q['question_id']=f'{request.request_id}:owner:{digest(q.get("requirement_id"))[:16]}'
            repaired.update(review_id=request.request_id,input_hash=content_hash,input_fields=fields)
            repaired['telemetry'].update(calls=0,input_tokens=0,output_tokens=0,latency_ms=0,attempted_calls=0,stages=[],
                execution={'state':'verified','stage':'answer_state_repaired'},answer_edit_supported=True)
            repaired['telemetry']['experience_outcomes']=experience_outcomes(
                repaired['telemetry'].get('v2_results',[]),item_references(content,fields),fields,
                lambda path,owner:experience_sources(content,path,owner))
            repaired['requirement_map'] = [r.model_dump(mode='json') for r in aggregate(requirements,
                repaired['telemetry']['v2_results'],fields,content_hash,source,
                lambda path,identity:experience_sources(content,path,identity),item_references(content,fields),
                repaired['telemetry'].get('requirement_answers',[]),provenance_for=provenance_for)]
            from app.resume_review_v2.question_planning import information_status
            from app.job_requirements import RequirementStatusRow
            repaired['telemetry']['information_review']=information_status(repaired['telemetry'].get('v2_results',[]),
                [RequirementStatusRow.model_validate(r) for r in repaired['requirement_map']],[],
                [ConfirmationAnswer.model_validate(a) for a in repaired.get('confirmed_answers',[])],
                repaired['telemetry'].get('requirement_answers',[]),requirement_context)
            response = FirestoreResumeReviewResponse.model_validate(repaired)
            db.complete_review(*args,request.request_id,response.model_dump(mode='json'),tail)
            return response
        staged = getattr(db, 'supports_stage_checkpoints', False) is True
        telemetry = {'engine': 'v2-local-ui-2', 'model': self.settings.openai_model, 'policy_version': POLICY_VERSION,
                     'answer_edit_supported':True,
                     'pipeline_version': PIPELINE_VERSION, 'reasoning_effort': self.settings.openai_reasoning_effort,
                     'requirement_answers':requirement_answers}
        telemetry['answer_changes'] = previous.get('telemetry',{}).get('answer_changes',[])
        if previous.get('telemetry',{}).get('answer_recovery'):
            telemetry['answer_recovery'] = dict(previous['telemetry']['answer_recovery'])
        engine = None
        try:
            def progress(state):
                telemetry.update(state)
                db.review_progress(*args, request.request_id, telemetry, tail)
            engine = self.engine or BatchReviewEngine(self.settings.openai_model, self.settings.openai_reasoning_effort,
                                                      budget_seconds=max(0, 165 - (time.monotonic() - request_started)),
                                                      on_progress=progress, stage_limited=staged)
            if isinstance(engine, BatchReviewEngine) and staged:
                engine.stage_limited = True
                engine.on_progress = progress
            answers = [ConfirmationAnswer.model_validate(a) for a in previous.get('confirmed_answers', [])]
            answers.extend(request.answers)
            chosen = targets(fields)
            refs = item_references(content, fields)
            chosen = {refs[value[0]]: value for value in chosen.values()}
            all_chosen = chosen.copy()
            owned_answers = [a for a in request.answers if a.experience_id is not None]
            if owned_answers:
                paths = {a.field_path for a in owned_answers}
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
                        issued = next((issued for issued,linked in answer_links if linked.question_id==a.question_id),{})
                        if issued.get('information_need_id') == q['dedupe_key']:
                            answered_keys.append(q['dedupe_key'])
                            if q.get('information_fingerprint'):answered_keys.append(q['information_fingerprint'])
                            if unavailable_answer(a.answer) and not q.get('requirement_id'):
                                unavailable.add(q['target_slot'])
                title, sources = experience_sources(content, path, identity)
                inputs.append(ReviewInput(
                    experience=Experience(experience_id=identity, kind=kind, title=title,
                        current_text=text, field_path=path, content_hash=content_hash, existing_evidence=evidence),
                    question='\n'.join(answer_question_context(a) for a in history), answer='\n'.join(a.answer for a in history),
                    answer_source_id=f'{request.request_id}:{path}' if history else '',
                    question_history=[answer_question_context(a) for a in history],
                    resume_sources=sources,
                    previous_facets=[EvidenceFacet.model_validate(f) for f in (old or {}).get('evidence_facets', [])],
                    existing_intents=[ApplicantIntentClaim.model_validate(c) for c in (old or {}).get('intent_claims', [])],
                    previous_semantic_units=[SemanticUnit.model_validate(u) for u in
                        ((old or {}).get('section_profile') or {}).get('original_semantic_units', [])],
                    prior_information_needs=[dict(information_need_id=q['dedupe_key'],target_slot=q.get('target_slot'),
                        request_aspect=q.get('request_aspect'),requirement_id=q.get('requirement_id'),
                        owner_scope=q.get('owner_scope'),question=q.get('question'),why_needed=q.get('why_needed'),
                        linked_answers=[a.answer for a in history if a.information_need_id==q['dedupe_key']
                            and a.experience_id==identity and a.field_path==path])
                        for q in (old or {}).get('gap_questions',[]) if not q.get('requirement_id') or
                            (old or {}).get('requirement_context_hash')==requirement_context],
                    unavailable_slots=[ProjectSlot(slot) for slot in unavailable],
                    previous_question_keys=list(dict.fromkeys(answered_keys)),
                    job_requirements=[JobRequirement(requirement_id=r.id, text=r.label, posting_quote=r.posting_quote) for r in requirements],
                ))
            from app.resume_review_v2.audit_resume import input_signature, source_signature, reusable_record, sources_changed, applied_record, applied_provenance
            prior_rows=aggregate(requirements,old_records,fields,content_hash,source,
                lambda path,owner:experience_sources(content,path,owner),refs,requirement_answers,provenance_for=provenance_for)
            delegate=min((r.experience.experience_id for r in inputs),default=None)
            for review_input in inputs:
                review_input.requirement_review_context=dict(resume_scope_delegate=review_input.experience.experience_id==delegate,
                    globally_supported=[r.id for r in prior_rows if r.status=='met'],
                    requirement_answers=[dict(requirement_id=a['requirement_id'],experience_id=a.get('experience_id'),disposition=a['disposition'],
                        information_aspect=(a.get('question_data') or {}).get('information_aspect')) for a in requirement_answers])
                if review_input.experience.experience_id==delegate:
                    review_input.requirement_review_context.update(
                        requirement_states=[dict(id=r.id,status=r.status,assessment=r.assessment_state,kind=r.kind,
                            evidence_refs=[dict(experience_id=f.get('experience_id'),scope=f.get('assertion_scope')) for f in r.evidence_refs]) for r in prior_rows],
                        resume_documents=[dict(experience_id=owner,field_path=value[0],title=experience_sources(content,value[0],owner)[0],text=value[1])
                            for owner,value in all_chosen.items()])
            resume_records = {}
            applied_reused = set()
            can_resume = isinstance(engine, BatchReviewEngine) and (request.review_phase == 'gap_audit' or staged or bool(request.answers))
            for index, review_input in enumerate(inputs):
                identity = review_input.experience.experience_id
                old = next((r for r in old_records if r['experience']['experience_id'] == identity), None)
                receipt = (old or {}).get('source_provenance') or (old or {}).get('verified_apply')
                guard = (old or {}).get('answer_edit_guard')
                if guard and review_input.experience.current_text != guard.get('safe_before_text'):
                    from copy import deepcopy
                    guarded = deepcopy(old)
                    guarded['experience'] = review_input.experience.model_dump(mode='json')
                    resume_records[identity] = guarded
                    continue  # Retained applied prose is not newly approved evidence.
                roots,operation=source_proof(review_input,old)
                if roots is not None:
                    review_input=review_input.model_copy(update={'historical_resume_sources':roots})
                    inputs[index]=review_input
                applied = applied_record(review_input,old,previous,source,requirement_context,
                    self.settings.openai_model,self.settings.openai_reasoning_effort,operation) if can_resume else None
                if applied is not None:
                    resume_records[identity] = applied
                    applied_reused.add(identity)
                elif can_resume and reusable_record(review_input, old, previous, source,
                                   self.settings.openai_model, self.settings.openai_reasoning_effort):
                    resume_records[identity] = old
                elif roots is None and (sources_changed(review_input, old) or receipt):
                    # Rebuild changed source material from current text and
                    # complete owning answer history, not unchecked old quotes.
                    clean = review_input.model_copy(deep=True)
                    independently_sourced = []
                    if (old or {}).get('answer_edit_guard'):
                        available = {s.source_id:s.text for s in clean.resume_sources}
                        available[identity] = clean.experience.current_text
                        independently_sourced = [e for e in clean.experience.existing_evidence
                            if e.assertion_state.value in {'resume_stated','user_asserted'} and e.experience_id==identity
                            and ((e.source_type=='resume_text' and e.evidence_quote in available.get(e.source_id,''))
                                 or (e.source_type=='user_answer' and e.evidence_quote in clean.answer))]
                    clean.experience.existing_evidence = [e for e in clean.experience.existing_evidence
                        if e.assertion_state.value in {'superseded', 'retracted', 'contradicted'}] + independently_sourced
                    old_intents = clean.existing_intents
                    clean.previous_facets, clean.existing_intents, clean.previous_semantic_units = [], [], []
                    if (old or {}).get('answer_edit_guard'):
                        clean.existing_intents = [c for c in old_intents if c.state.value not in {'resume_stated','user_asserted'}
                            or (c.source_type=='resume_text' and c.evidence_quote in available.get(c.source_id,''))
                            or (c.source_type=='user_answer' and c.evidence_quote in clean.answer)]
                    inputs[index] = clean
            if can_resume:
                results = engine.run_many(inputs, resume_records=resume_records,
                    **({'checkpoint': claimed.get('checkpoint', {})} if staged else {}))
                verifying = sum(any(i.get('code') == 'verification_unavailable'
                    for i in r['validation'].get('factual_issues', [])) for r in resume_records.values())
                telemetry['audit_resume'] = dict(reused_experiences=len(resume_records),
                    completed_reused=len(resume_records) - verifying, verification_resumed=verifying,
                    reprocessed_experiences=len(inputs) - len(resume_records))
            else:
                results = engine.run_many(inputs)
            if staged and any(any(i.code == 'verification_unavailable' for i in r.validation.all_issues) for r in results):
                return self._processing_response(db, args, request, source, content_hash, telemetry, engine,
                    retryable_error='verification_unavailable')
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
                old = next((r for r in old_records if r['experience']['experience_id'] == identity), None)
                if (old and old.get('requirement_context_hash') == requirement_context
                        and (review_input.historical_resume_sources or not sources_changed(review_input, old))
                        and record.get('requirement_matches') is not None):
                    from app.resume_review_v2.requirement_matching import reconcile_matches
                    from app.resume_review_v2.models import RequirementEvidenceMatch
                    combined,continuity_notes=reconcile_matches(review_input,
                        [RequirementEvidenceMatch.model_validate(m) for m in old.get('requirement_matches') or []],
                        [RequirementEvidenceMatch.model_validate(m) for m in record['requirement_matches']],
                        [Evidence.model_validate(f) for f in old.get('evidence_state',[])],state)
                    record['requirement_matches']=[m.model_dump(mode='json') for m in combined]
                    record['requirement_warnings']=list(dict.fromkeys([*record.get('requirement_warnings',[]),*continuity_notes]))
                if any(i.code == 'analysis_contract_invalid' for i in result.validation.all_issues):
                    # Never combine a new/empty Evidence snapshot with an old
                    # derived profile. Answers and reference diagnostics survive;
                    # the failed analysis is not an approved writing snapshot.
                    record.update(intent_claims=[], section_profile=None, sentence_plan=None,
                        evidence_facets=[], project_profile=None)
                    old = next((r for r in old_records if r['experience']['experience_id'] == identity), None)
                    # A failed new turn may retain a coherent *prior* snapshot
                    # only when the owning sources and its entire Evidence state
                    # are unchanged. It never becomes a successful new analysis.
                    if (old and not sources_changed(review_input, old)
                            and record['evidence_state'] == old.get('evidence_state')):
                        for key in ('intent_claims', 'section_profile', 'sentence_plan',
                                    'evidence_facets', 'project_profile'):
                            record[key] = old.get(key)
                # Unanswered questions remain eligible after recomputation; only
                # answered identities are suppressed across turns.
                record['answered_question_keys'] = review_input.previous_question_keys
                record['audit_source_hash'] = source_signature(review_input)
                record['audit_input_hash'] = input_signature(review_input, source,
                    self.settings.openai_model, self.settings.openai_reasoning_effort, record)
                if identity in applied_reused:
                    record['verified_apply'] = resume_records[identity]['verified_apply']
                elif review_input.historical_resume_sources:
                    record['source_provenance'] = (old or {}).get('source_provenance') or (old or {}).get('verified_apply')
                if identity not in resume_records:
                    record['requirement_context_hash'] = requirement_context
                else:
                    record['requirement_context_hash'] = resume_records[identity].get('requirement_context_hash', '')
                records.append(record)
                for key in ('calls', 'input_tokens', 'output_tokens', 'latency_ms'):
                    setattr(usage, key, getattr(usage, key) + getattr(result.usage, key))
                candidate = result.candidate
                ready = candidate is not None and result.validation.status == 'READY'
                unchanged = result.validation.status == 'UNCHANGED'
                question = result.proposed_question
                sentences.append(SentenceReview(field_path=path, original_quote=text,
                    reason='검증된 수정안이 정확히 적용되어 완료된 작성 상태를 재사용했습니다.' if identity in applied_reused else
                        '원문보다 명확한 개선이 없어 원문을 유지했습니다.' if unchanged else result.plan.reason or result.plan.objective,
                    suggested_revision=candidate.suggested_text if ready else None,
                    validation_status=('NEEDS_EVIDENCE' if candidate is None and result.validation.status == 'READY'
                        else result.validation.status),
                    status='improved' if ready else 'unchanged' if unchanged else 'needs_confirmation' if (
                        question or candidate is None and result.validation.status in {'READY', 'NEEDS_EVIDENCE'}) else 'unchanged',
                    confirmation_question=question.question if question else None,
                    evidence_quotes=[e.evidence_quote for e in result.selected_evidence],
                    validation_issues=[i.code for i in result.validation.all_issues]))
            refreshed = {r['experience']['experience_id'] for r in records}
            records.extend(r for r in old_records if r['experience']['experience_id'] not in refreshed)
            # Unselected, still-valid needs survive a fresh owning analysis. This
            # is discovery state, never a reason to reuse its former candidate.
            for record in records:
                old=next((r for r in old_records if r['experience']['experience_id']==record['experience']['experience_id']),{})
                current=(record.get('debug_trace') or {}).get('question_selection',{})
                prior=(old.get('debug_trace') or {}).get('question_selection',{})
                if record['experience']['experience_id'] in resume_records:
                    continue  # No fresh Analyze decision: reuse the validated review as-is.
                if record['experience']['experience_id'] in refreshed and (old.get('audit_source_hash')==record.get('audit_source_hash')
                        or record.get('source_provenance') or record.get('verified_apply')):
                    from app.resume_review_v2.question_planning import reconcile_deferred_needs
                    reconcile_deferred_needs(record,old,requirement_context)
            for record in records:
                old = next((r for r in old_records if r['experience']['experience_id']==record['experience']['experience_id']),{})
                if record['experience']['experience_id'] in resume_records and old.get('answer_edit_guard'):
                    record['answer_edit_guard'] = old['answer_edit_guard']
                    record['answer_state_invalidated'] = True
            # At most three questions for the whole Resume, not three per project.
            # Untouched experiences keep their pending gaps when one field is answered.
            from app.resume_review_v2.models import GapQuestion
            from app.resume_review_v2.question_planning import approved_question, public_question_reason
            requirement_rows = aggregate(requirements, records, fields, content_hash, source,
                lambda path, identity: experience_sources(content, path, identity), item_references(content, fields), requirement_answers,
                provenance_for=provenance_for)
            row_by_id = {r.id:r for r in requirement_rows}
            requirement_by_id = {r.id:r for r in requirements}
            owner_options = [dict(experience_id=identity, field_path=value[0],
                experience_title=experience_sources(content, value[0], identity)[0]) for identity,value in all_chosen.items()
                if (value[2] in {'project','employment','activity'} or value[0]=='selfIntroduction.intro.body') and not identity.startswith('legacy:')]
            question_delivery = []
            for record in records:
                identity = record['experience']['experience_id']
                if identity not in all_chosen:
                    continue
                path = all_chosen[identity][0]
                display_title, _ = experience_sources(content, path, identity)
                answered_keys = set(record.get('answered_question_keys', []))
                state = {e['evidence_id']: Evidence.model_validate(e) for e in
                         record.get('evidence_state', record.get('extracted_evidence', []))}
                display_request = next((r for r in inputs if r.experience.experience_id==identity),None)
                if display_request is None:
                    title,doc_sources=experience_sources(content,path,identity)
                    history=[a.answer for a in answers if a.experience_id==identity]
                    display_request=ReviewInput(experience=Experience(experience_id=identity,kind=all_chosen[identity][2],
                        title=title,current_text=fields[path],field_path=path,content_hash=content_hash),
                        resume_sources=doc_sources,answer='\n'.join(history),answer_source_id='display-history' if history else '')
                roots,_=source_proof(display_request,record)
                if roots is not None:display_request=display_request.model_copy(update={'historical_resume_sources':roots})
                for raw in record.get('gap_questions', []):
                    # Upgrade old stored B questions only from their owning record.
                    q = GapQuestion.model_validate({
                        'experience_id': identity, 'experience_title': record['experience']['title'], **raw})
                    delivery = dict(experience_id=identity, dedupe_key=q.dedupe_key,
                        requirement_id=q.requirement_id, state='eligible', reason=None)
                    question_delivery.append(delivery)
                    if q.experience_id != identity:
                        raise ReviewInputError('question experience does not match record')
                    if q.dedupe_key in answered_keys or any(a.information_need_id==q.dedupe_key or
                            a.information_request_fingerprint==q.information_fingerprint for a in answers):
                        delivery.update(state='server_filtered', reason='already_answered')
                        continue
                    # Legacy slot-fill questions have never been evaluated for
                    # marginal editing value. Do not replay them as approved.
                    if not q.dedupe_key.startswith(identity + ':value:') or not approved_question(q,state,requirements,display_request):
                        delivery.update(state='server_filtered', reason='legacy_or_unapproved_question')
                        continue
                    if q.requirement_id:
                        row = row_by_id.get(q.requirement_id)
                        if (row is None or row.kind == 'eligibility' or row.status in {'met','absent'}
                                or record.get('requirement_context_hash') != requirement_context
                                ):
                            delivery.update(state='server_filtered', reason='requirement_context_or_state')
                            continue
                        if q.owner_scope == 'unassigned' and not q.requirement_anchor and (row.status == 'partial'
                                and any(ref.get('assertion_scope') != 'mentioned' for ref in row.evidence_refs)):
                            delivery.update(state='server_filtered', reason='owner_unavailable_or_already_grounded')
                            continue
                        if row.status == 'partial' and q.gap_type != 'clarification' and any(
                                ref.get('assertion_scope') != 'mentioned' for ref in row.evidence_refs):
                            delivery.update(state='server_filtered', reason='partial_requires_clarification')
                            continue
                        if q.owner_scope == 'unassigned' and any(a['requirement_id'] == q.requirement_id and a.get('experience_id') is None
                               and a['disposition'] in {'absent','unknown','provided'} for a in requirement_answers):
                            delivery.update(state='server_filtered', reason='unassigned_answer_already_collected')
                            continue
                        if q.request_aspect=='experience_presence' and any(a['requirement_id']==q.requirement_id and
                                a['disposition'] in {'provided','unknown'} for a in requirement_answers):
                            delivery.update(state='server_filtered',reason='presence_already_answered');continue
                    questions.append(public_gap_question(q,request.request_id,path,display_title,owner_options,requirement_context))
                    delivery['question_id'] = questions[-1].question_id
            # Owner-less provided answers remain collected but are never injected.
            # Reuse the issued question as an ownership clarification, not a new LLM task.
            latest_unassigned = {}
            for a in requirement_answers:
                if a.get('experience_id') is None: latest_unassigned[a['requirement_id']] = a
                else: latest_unassigned.pop(a['requirement_id'], None)
            for rid, a in latest_unassigned.items():
                if a['disposition'] == 'provided' and row_by_id[rid].status != 'met' and owner_options:
                    q = ReviewQuestion.model_validate(a['question_data'])
                    q.question_id = f'{request.request_id}:owner:{digest(rid)[:16]}'
                    q.information_need_id = f'ownership:{requirement_context}:{rid}'
                    q.information_request_fingerprint = q.information_need_id
                    q.question = '앞서 답한 경험이 속한 항목을 선택하고 해당 수행 내용을 확인해 주세요.'
                    q.information_aspect='owner_selection'
                    q.owner_options = owner_options
                    questions.append(q)
            ranked = sorted(questions, key=lambda q: (q.priority,
                0 if q.requirement_id and requirement_by_id[q.requirement_id].group == 'must' else 1))
            questions, seen_requirements, seen_owners = [], set(),set()
            for q in ranked:
                if q.experience_id is not None and q.experience_id in seen_owners:
                    for delivery in question_delivery:
                        if delivery.get('question_id')==q.question_id:delivery.update(state='server_filtered',reason='owner_question_cap')
                    continue
                if q.requirement_id and q.requirement_id in seen_requirements:
                    for delivery in question_delivery:
                        if delivery.get('question_id') == q.question_id:
                            delivery.update(state='server_filtered', reason='requirement_dedupe')
                    continue
                questions.append(q)
                if q.experience_id is not None:seen_owners.add(q.experience_id)
                if q.requirement_id: seen_requirements.add(q.requirement_id)
                if len(questions) >= MAX_PROGRESSIVE_QUESTIONS: break
            delivered_ids = {q.question_id for q in questions}
            for delivery in question_delivery:
                if delivery['state'] == 'eligible':
                    delivery.update(state='displayed' if delivery.get('question_id') in delivered_ids else 'server_filtered',
                        reason=None if delivery.get('question_id') in delivered_ids else 'question_cap')
            telemetry['question_delivery'] = question_delivery
            from app.resume_review_v2.question_planning import information_status
            telemetry['information_review']=information_status([r for r in records if r['experience']['experience_id'] in all_chosen],
                requirement_rows,question_delivery,answers,requirement_answers,requirement_context,owner_options)
            telemetry.update(usage.model_dump(), v2_results=records)
            if telemetry.get('answer_recovery'):
                telemetry['answer_recovery']['requires_document_undo'] = any(
                    r.get('answer_edit_guard') for r in records)
            telemetry['applied_reused_experiences'] = len(applied_reused)
            telemetry['experience_outcomes']=experience_outcomes(records,refs,fields,
                lambda path,owner:experience_sources(content,path,owner))
            telemetry['stages'] = engine.stages if isinstance(engine, BatchReviewEngine) else []
            telemetry['attempted_calls'] = engine.attempted_calls if isinstance(engine, BatchReviewEngine) else usage.calls
            summary = '경험 근거와 문장 흐름을 검토했습니다.'
            telemetry.pop('stage_checkpoint', None)
            kept = sum(r['validation']['status'] == 'UNCHANGED' for r in records if r['experience']['experience_id'] in chosen
                       and r['experience']['experience_id'] not in applied_reused)
            if applied_reused:
                summary += f' 검증·적용 완료된 {len(applied_reused)}개 항목은 재작성 없이 이어갑니다.'
            if kept:
                summary += f' 원문보다 명확한 개선이 없는 {kept}개 항목은 원문을 유지했습니다.'
            response = FirestoreResumeReviewResponse(summary=summary,
                section_reviews=[], sentence_reviews=sentences, questions=questions,
                confirmation_questions=[q.question for q in questions], review_id=request.request_id,
                cohort_id=request.cohort_id, resume_id=request.resume_id, tailored_resume_id=tail,
                input_fields=fields, input_hash=content_hash, item_refs=item_references(content, fields),
                excluded_fields=excluded, confirmed_answers=answers, job_source=source, telemetry=telemetry,
                requirement_map=[r.model_dump(mode='json') for r in requirement_rows])
            from app.resume_review_v2.star_diagnostics import original_star_checks
            response.star_checks = original_star_checks(records, fields, content_hash,
                lambda path, identity: experience_sources(content, path, identity), item_references(content, fields))
            # Re-read before publishing: a concurrent external edit cannot make
            # this old source snapshot an apply-ready response.
            current = db.get_owned_tailored_resume(*args[:2], tail, uid) if tail else db.get_owned_resume(*args)
            if digest(current.get('content') or {}) != content_hash:
                raise ReviewConflict('resume_version_changed')
            telemetry['execution'] = {'state': 'verified', 'stage': 'complete'}
            response.telemetry = telemetry
            db.complete_review(*args, request.request_id, response.model_dump(mode='json'), tail)
            return response
        except StageBoundary:
            return self._processing_response(db, args, request, source, content_hash, telemetry, engine)
        except Exception as exc:
            telemetry['error_type'] = type(exc).__name__
            if isinstance(engine, BatchReviewEngine):
                telemetry.update(engine.usage.model_dump(), stages=engine.stages,
                                 attempted_calls=engine.attempted_calls)
            db.fail_review(*args, request.request_id, telemetry, tail)
            raise

    def _processing_response(self, db, args, request, source, content_hash, telemetry, engine, retryable_error=None):
        checkpoint = engine.checkpoint
        states = checkpoint.get('states', {})
        waiting_verify = any(s.get('needs_verify') and not s.get('needs_write') for s in states.values())
        telemetry.update(engine.usage.model_dump(), stages=engine.stages, attempted_calls=engine.attempted_calls,
            stage_checkpoint=checkpoint, execution={'state': 'verification_pending' if waiting_verify else 'processing',
            'stage': 'verify' if waiting_verify else 'write', 'retryable_error': retryable_error})
        db.review_progress(*args, request.request_id, telemetry, request.tailored_resume_id)
        # Never expose incomplete draft text or questions before initial validation.
        return FirestoreResumeReviewResponse(summary='검증을 이어서 진행하고 있습니다.', section_reviews=[],
            sentence_reviews=[], questions=[], confirmation_questions=[], input_fields={}, excluded_fields=[],
            review_id=request.request_id, input_hash=content_hash, cohort_id=request.cohort_id,
            resume_id=request.resume_id, tailored_resume_id=request.tailored_resume_id,
            job_source=source, telemetry={k:v for k,v in telemetry.items() if k != 'stage_checkpoint'})
