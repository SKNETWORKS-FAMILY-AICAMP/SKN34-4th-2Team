import { beforeEach, describe, expect, it, vi } from 'vitest';

import { changedRevisionSpans } from '../reviewDiff';
import type { Json } from '../reviewApi';

const api = vi.hoisted(() => ({
  context: vi.fn(),
  createTailored: vi.fn(),
  tailored: vi.fn(),
  saveSession: vi.fn(),
  promote: vi.fn(),
  review: vi.fn(),
  apply: vi.fn(),
  undo: vi.fn(),
}));

vi.mock('../reviewApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../reviewApi')>()),
  reviewApi: api,
}));

const { ReviewSession } = await import('../reviewSession');

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

function makeSession(extra: Partial<ConstructorParameters<typeof ReviewSession>[0]> = {}) {
  const closed: (string | undefined)[] = [];
  const session = new ReviewSession({
    resumeId: 'r1',
    jobId: 'JOB-1',
    jobCompany: '㈜회사',
    jobTitle: 'AI 개발자',
    tailoredResumeId: '',
    initialReviewSession: {},
    generalReview: false,
    onChanged: () => {},
    onClose: (result) => closed.push(result),
    confirmComplete: async () => true,
    onStatus: () => {},
    onFocusPreview: () => {},
    onRefocusAnswer: () => {},
    ...extra,
  });
  const detach = session.attach();
  return { session, closed, detach };
}

const sentence = (i: number, editType: string, extra: Json = {}): Json => ({
  field_path: `projects[${i}].description`,
  original_quote: `원문 ${i}`,
  suggested_revision: `고친 문장 ${i}`,
  edit_type: editType,
  reason: `이유 ${i}`,
  ...extra,
});

const firstReview: Json & { questions: Json[] } = {
  review_id: 'rev-1',
  input_hash: 'h1',
  summary: '공고와 비교했습니다. 프로젝트 근거가 있습니다. 수치는 없습니다. 네 번째 문장.',
  job_source: { company: '㈜회사', title: 'AI 개발자', snapshot_hash: 'job-h' },
  sentence_reviews: [sentence(0, 'clarity'), sentence(1, 'tone'), sentence(2, 'content'), sentence(3, 'content', { original_quote: '[회사명] 지원' })],
  questions: [
    { question_id: 'q1', field_path: 'projects[0].description', topic: 'result', question: '성과가 있나요?', stage: 3 },
    { question_id: 'q2', field_path: 'projects[1].description', topic: 'action', question: '무엇을 했나요?', stage: 3 },
  ],
  requirement_map: [{ id: 'req-1', group: 'must', label: 'Python', status: 'met' }],
  star_checks: [{ field_path: 'projects[0].description', present: ['action'] }],
};

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.createTailored.mockResolvedValue({ tailored_resume_id: 'tailored_1', content: { basicInfo: { name: '학생' } }, review_session: {} });
  api.context.mockResolvedValue({ content: { basicInfo: { name: '학생' } }, input_hash: 'h1', job_source: { snapshot_hash: 'job-h' } });
  api.saveSession.mockResolvedValue({ saved: true });
  api.review.mockResolvedValue(firstReview);
});

describe('B 답변 복구', () => {
  it('미검토 보완 상태는 세션 복원에도 남고 질문 없음으로 전체 검토 완료를 선언하지 않는다',()=>{
    const {session,detach}=makeSession({tailoredResumeId:'tailored_1'});
    const result={...firstReview,questions:[],sentence_reviews:[],telemetry:{answer_edit_supported:true,
      information_review:{state:'pending',unreviewed_experiences:1,open_opportunities:0,requirements:[{state:'not_reviewed',reason:'no_model_review_recorded'}]}}};
    session.result=result;
    (session as unknown as {appendReview(r:Json,o:{isFirstReview:boolean;isGapAudit:boolean}):void}).appendReview(result,{isFirstReview:false,isGapAudit:true});
    expect(session.messages.some(m=>m.type==='assistant' && m.text.includes('모든 보완 검토의 완료'))).toBe(true);
    expect(session.messages.some(m=>m.type==='assistant' && m.text.includes('추가로 확인할 중요한 항목이 없습니다'))).toBe(false);
    const saved=(session as unknown as {sessionState():Json}).sessionState();
    const {session:restored,detach:detachRestored}=makeSession({tailoredResumeId:'tailored_1',initialReviewSession:saved});
    expect(restored.informationReviewPending).toBe(true);
    expect((saved.result as Json)._information_review).not.toHaveProperty('decisions');
    detach();detachRestored();
  });
  it('새 경험 유무 질문은 긍정 답변을 소유 항목 없이 보류 저장할 수 있다',async ()=>{
    const {session,detach}=makeSession();
    const q={question_id:'presence',question_contract:'evidence-need-v2',information_aspect:'experience_presence',
      field_path:'__requirement_owner__',question:'관련 경험이 있나요?',owner_scope:'unassigned',owner_options:[]};
    session.result={...firstReview,telemetry:{answer_edit_supported:true}};session.answer='캐싱을 구현했습니다.';
    api.review.mockResolvedValue({...firstReview,questions:[],sentence_reviews:[],confirmed_answers:[],
      telemetry:{answer_edit_supported:true,execution:{state:'verified'},information_review:{state:'pending'}}});
    await session.submitAnswer(q);
    expect(api.review.mock.calls[0][1].answers[0]).toMatchObject({field_path:'__requirement_owner__',answer:'캐싱을 구현했습니다.'});
    expect(api.review.mock.calls[0][1].answers[0]).not.toHaveProperty('experience_id');
    detach();
  });
  it('최신 전체 Experience 요약으로 다른 항목 실패를 유지하고 후속 성공·삭제·무효화는 반영한다',()=>{
    const {session,detach}=makeSession();
    const outcome=(id:string,status:string)=>({experience_id:id,field_path:id,status});
    session.result={review_id:'answer-lms',sentence_reviews:[{field_path:'lms',validation_status:'READY'}],
      telemetry:{experience_outcomes:[outcome('growth','REJECTED'),outcome('lms','READY')]}};
    expect(session.hasUnresolvedReviewFailure).toBe(true);
    const saved=(session as unknown as {sessionState():Json}).sessionState();
    const {session:restored,detach:detachRestored}=makeSession({tailoredResumeId:'tailored_1',initialReviewSession:saved});
    expect(restored.hasUnresolvedReviewFailure).toBe(true);
    session.result={review_id:'growth-success',telemetry:{experience_outcomes:[outcome('growth','READY'),outcome('lms','READY')]}};
    expect(session.hasUnresolvedReviewFailure).toBe(false);
    session.result={telemetry:{experience_outcomes:[outcome('lms','READY')],v2_results:[
      {experience:{experience_id:'deleted'},validation:{status:'REJECTED'}}]}};
    expect(session.hasUnresolvedReviewFailure).toBe(false); // authoritative summary, not archive
    session.result={telemetry:{experience_outcomes:[outcome('growth','NEEDS_EVIDENCE')]}};
    expect(session.hasUnresolvedReviewFailure).toBe(false);
    session.result={telemetry:{v2_results:[{experience:{experience_id:'growth'},validation:{status:'REJECTED'}},
      {experience:{experience_id:'lms'},validation:{status:'READY'}}]},sentence_reviews:[{validation_status:'READY'}]};
    expect(session.hasUnresolvedReviewFailure).toBe(true); // compatibility with existing B responses
    detach();detachRestored();
  });
  it('같은 실패 안내도 서로 다른 답변에는 각각 표시하고 동일 응답 재처리는 중복하지 않는다',()=>{
    const {session,detach}=makeSession();
    const append=session as unknown as {appendReview(review:Json,opts:{isFirstReview:boolean;answeredFieldPath:string;answeredQuestionId:string}):void};
    const failed=(id:string,index:number)=>({...firstReview,review_id:id,questions:[],sentence_reviews:[
      sentence(index,'content',{suggested_revision:null,validation_status:'REJECTED',validation_issues:['analysis_contract_invalid']})]});
    const options=(index:number)=>({isFirstReview:false,answeredFieldPath:`projects[${index}].description`,answeredQuestionId:`q${index}`});
    append.appendReview(failed('kkbox-answer',0),options(0));
    append.appendReview(failed('lms-answer',2),options(2));
    append.appendReview(failed('lms-answer',2),options(2));
    const warnings=()=>session.messages.filter(m=>m.type==='assistant' && m.text.includes('경험 근거의 참조'));
    expect(warnings()).toHaveLength(2);
    const saved=(session as unknown as {sessionState():Json}).sessionState();
    saved.result={review_id:'lms-answer'};
    const {session:restored,detach:detachRestored}=makeSession({tailoredResumeId:'tailored_1',initialReviewSession:saved});
    (restored as unknown as typeof append).appendReview(failed('lms-answer',2),options(2));
    expect(restored.messages.filter(m=>m.type==='assistant' && m.text.includes('경험 근거의 참조'))).toHaveLength(2);
    detach();detachRestored();
  });
  it('별도 audit 수정안을 직전 답변 반영으로 안내하지 않고 실패 audit를 성공 완료로 안내하지 않는다',()=>{
    const {session,detach}=makeSession();
    const append=session as unknown as {appendReview(review:Json,opts:{isFirstReview:boolean;isGapAudit:boolean}):void};
    append.appendReview({...firstReview,questions:[],sentence_reviews:[sentence(2,'content',{validation_status:'READY'})]},
      {isFirstReview:false,isGapAudit:true});
    expect(session.messages.some(m=>m.type==='assistant' && m.text.includes('별도의 자동 수정안'))).toBe(true);
    expect(session.messages.some(m=>m.type==='assistant' && m.text.includes('방금 답한 항목'))).toBe(false);
    session.messages=[];
    const failed={...firstReview,questions:[],sentence_reviews:[sentence(0,'content',{
      suggested_revision:null,validation_status:'REJECTED',validation_issues:['analysis_contract_invalid']})]};
    session.result=failed;
    append.appendReview(failed,{isFirstReview:false,isGapAudit:true});
    append.appendReview(failed,{isFirstReview:false,isGapAudit:true});
    expect(session.hasUnresolvedReviewFailure).toBe(true);
    expect(session.messages.filter(m=>m.type==='assistant' && m.text.includes('근거 연결'))).toHaveLength(1);
    expect(session.messages.some(m=>m.type==='assistant' && m.text.includes('누락 점검까지 완료'))).toBe(false);
    detach();
  });
  it('B legacy 질문 답변은 로컬에서 멈추고 완료로 기록하지 않는다', async () => {
    const {session,detach}=makeSession();session.result={...firstReview,telemetry:{answer_edit_supported:true}};
    session.answer='새 답변';const q=(firstReview.questions as Json[])[0];
    await session.submitAnswer(q);session.submitNoneAnswer(q);
    expect(api.review).not.toHaveBeenCalled();expect(session.answer).toBe('새 답변');
    expect(session.error).toContain('이전 계약');detach();
  });
  it('같은 질문 문구라도 실제 공개 대상이 다른 정보요구를 유지한다', async () => {
    const {session,detach}=makeSession();const body='확인한 내용이 있다면 알려주세요.';
    api.review.mockResolvedValue({...firstReview,sentence_reviews:[],questions:[
      {question_id:'n1',information_need_id:'need:first',information_request_fingerprint:'source-need:first',experience_id:'p1',field_path:'projects[0].description',target_slot:'outcome',question:body,
        target_contexts:[{type:'applicant_source',quote:'모델을 비교했습니다.',anchors:['모델']}]},
      {question_id:'n2',information_need_id:'need:second',information_request_fingerprint:'source-need:second',experience_id:'p1',field_path:'projects[0].description',target_slot:'outcome',question:body,
        target_contexts:[{type:'applicant_source',quote:'거리 계산 기능을 구현했습니다.',anchors:['거리 계산']}]},
      {question_id:'renamed',information_need_id:'need:renamed',information_request_fingerprint:'source-need:first',experience_id:'p1',field_path:'projects[0].description',target_slot:'outcome',question:body,
        target_contexts:[{type:'applicant_source',quote:'모델을 비교했습니다.',anchors:['모델']}]}]});
    await session.review();
    expect(session.view().remainingQuestionCount).toBe(2);detach();
  });
  it('과거 답변 복구 중 연속 적용을 역순 취소하고 세션 복원 후에도 이어간다', async () => {
    const held = {...firstReview,review_id:'repaired',input_hash:'h4',sentence_reviews:[],questions:[],
      telemetry:{execution:{state:'verified'},answer_recovery:{requires_document_undo:true}}};
    const card = (id: string, hash: string, index: number): Json => ({...sentence(index,'content'),
      _review_id:id,_index:index,_operation_id:id,_application_input_hash:hash,_applied:true,_undo_available:false});
    const a=card('a','h2',0), b=card('b','h3',0), sibling=card('b','h3',1), c=card('c','h4',2);
    const {session,detach}=makeSession({tailoredResumeId:'tailored_1',initialReviewSession:{version:1,result:held,
      messages:[a,b,sibling,c].map(payload=>({type:'suggestion',payload}))}});
    const cards=()=>session.messages.filter(m=>m.type==='suggestion').map(m=>m.payload);
    expect(cards().map(p=>p._undo_available)).toEqual([false,false,false,true]);
    await session.undoSuggestion(cards()[0]);
    expect(api.undo).not.toHaveBeenCalled(); // A stale card cannot skip snapshots.
    api.undo.mockResolvedValueOnce({input_hash:'h3'});
    api.review.mockResolvedValueOnce({...held,input_hash:'h3'});
    await session.undoSuggestion(cards()[3]);
    expect(cards().map(p=>p._undo_available)).toEqual([false,true,true,false]);
    expect(session.awaitingDocumentUndo).toBe(true);
    const saved=api.saveSession.mock.calls.at(-1)![2] as Json;
    detach();
    const {session:restored,detach:detachRestored}=makeSession({tailoredResumeId:'tailored_1',initialReviewSession:saved});
    const restoredCards=()=>restored.messages.filter(m=>m.type==='suggestion').map(m=>m.payload);
    expect(restoredCards().map(p=>p._undo_available)).toEqual([false,true,true,false]);
    api.undo.mockResolvedValueOnce({input_hash:'h2'});
    api.review.mockResolvedValueOnce({...held,input_hash:'h2'});
    await restored.undoSuggestion(restoredCards()[1]);
    expect(restoredCards().map(p=>p._undo_available)).toEqual([true,false,false,false]);
    expect(restoredCards()[2]._undone).toBe(true); // All cards in operation B retire together.
    api.undo.mockResolvedValueOnce({input_hash:'h1'});
    api.review.mockResolvedValueOnce({...held,input_hash:'h1',telemetry:{execution:{state:'verified'},answer_recovery:{requires_document_undo:false}}});
    await restored.undoSuggestion(restoredCards()[0]);
    expect(restored.awaitingDocumentUndo).toBe(false);
    expect(api.undo.mock.calls.map(c=>c[1].application_id)).toEqual(['c','b','a']);
    expect(api.undo.mock.calls.map(c=>c[1].expected_input_hash)).toEqual(['h4','h3','h2']);
    expect(api.apply).not.toHaveBeenCalled();
    detachRestored();
  });
  it('구버전 engine 표시만으로 답변 수정 기능을 열지 않는다', () => {
    const {session,detach}=makeSession();session.result={...firstReview,telemetry:{engine:'v2-local-ui-2'},
      confirmed_answers:[{question_id:'q1',answer:'기존 답변'}]};
    expect(session.answerEditSupported).toBe(false);expect(session.editableAnswers).toEqual([]);detach();
  });
  it('서버 변경 확인이 없으면 답변과 완료 상태를 로컬에서 바꾸지 않는다', async () => {
    const {session,detach}=makeSession();const previous={...firstReview,telemetry:{answer_edit_supported:true},
      confirmed_answers:[{question_id:'q1',question:'성과가 있나요?',answer:'기존 답변'}]};session.result=previous;
    api.review.mockResolvedValue(firstReview);
    await session.changeAnswer('q1',null);
    expect(session.result).toBe(previous);expect(session.editableAnswers[0].answer).toBe('기존 답변');
    expect(session.error).toContain('확인되지 않았습니다');detach();
  });
  it('질문 복사는 네트워크 호출 전 거절하고 초안은 유지한다', async () => {
    const {session,detach} = makeSession(); session.result = firstReview;
    session.answer = String((firstReview.questions as Json[])[0].question);
    const draft = session.answer;
    await session.submitAnswer((firstReview.questions as Json[])[0]);
    expect(api.review).not.toHaveBeenCalled(); expect(session.answer).toBe(draft);
    expect(session.error).toContain('질문을 그대로');
    detach();
  });
  it('취소를 서버에 저장하고 복원된 세션에도 새 답변 상태를 유지한다', async () => {
    const {session,detach} = makeSession(); session.tailoredResumeId = 'tailored_1';
    session.result = {...firstReview, telemetry:{engine:'v2-local-ui-2',answer_edit_supported:true},
      confirmed_answers:[{question_id:'q1',question:'성과가 있나요?',answer:'오입력',field_path:'projects[0].description'}]};
    api.review.mockResolvedValue({...firstReview, review_id:'repaired',sentence_reviews:[],confirmed_answers:[],
      questions:[(firstReview.questions as Json[])[0]],telemetry:{engine:'v2-local-ui-2',answer_edit_supported:true,execution:{state:'verified'},answer_recovery:{question_id:'q1',operation:'retract',requires_document_undo:false}}});
    await session.changeAnswer('q1',null);
    expect(api.review.mock.calls[0][1].answer_changes).toEqual([{question_id:'q1',operation:'retract',expected_answer:'오입력'}]);
    expect(session.editableAnswers).toEqual([]);
    const state = api.saveSession.mock.calls.at(-1)![2] as Json;
    const {session:restored,detach:detachRestored} = makeSession({tailoredResumeId:'tailored_1',initialReviewSession:state});
    expect(restored.answerEditSupported).toBe(true); expect(restored.editableAnswers).toEqual([]);
    detach();detachRestored();
  });
  it('적용 문장이 남으면 수정 저장만 하고 자동 작성하지 않는다', async () => {
    const {session,detach} = makeSession();session.result={...firstReview,telemetry:{engine:'v2-local-ui-2',answer_edit_supported:true},
      confirmed_answers:[{question_id:'q1',question:'성과가 있나요?',answer:'이전 답변',field_path:'projects[0].description'}]};
    api.review.mockResolvedValue({...firstReview,review_id:'repair',sentence_reviews:[],questions:[],
      confirmed_answers:[{question_id:'q1',question:'성과가 있나요?',answer:'정정 답변',field_path:'projects[0].description'}],
      telemetry:{engine:'v2-local-ui-2',answer_edit_supported:true,execution:{state:'verified'},answer_recovery:{question_id:'q1',operation:'replace',requires_document_undo:true}}});
    await session.changeAnswer('q1','정정 답변');
    expect(api.review).toHaveBeenCalledTimes(1);expect(session.awaitingDocumentUndo).toBe(true);
    expect(session.messages.some(m => m.type==='assistant' && m.text.includes('그대로 남아'))).toBe(true);
    detach();
  });
});

describe('공고 맞춤 첨삭 흐름 — job_resume_review_dialog.dart', () => {
  it('소유자 미확정 요건 답변은 선택 전 API로 보내지 않고 선택한 서버 옵션으로 보낸다', async () => {
    const question = { question_id: 'requirement-q', field_path: '__requirement_owner__', requirement_id: 'req-1',
      question: '해당 경험이 있나요?', owner_scope: 'unassigned',
      owner_options: [{ experience_id: 'projects:p2', field_path: 'projects[1].description', experience_title: '두 번째 프로젝트' }] };
    api.review.mockResolvedValueOnce({ ...firstReview, sentence_reviews: [], questions: [question] });
    const { session } = makeSession(); await session.review();
    session.setAnswer('캐싱을 직접 구현했습니다.');
    await session.submitAnswer(session.view().activeQuestion!);
    expect(api.review).toHaveBeenCalledTimes(1);
    expect(session.answer).toContain('캐싱');
    session.selectAnswerOwner(question, 'projects:p2');
    api.review.mockResolvedValueOnce({ ...firstReview, sentence_reviews: [], questions: [] });
    await session.submitAnswer(session.view().activeQuestion!);
    expect(api.review.mock.calls[1][1].answers).toEqual([expect.objectContaining({ question_id: 'requirement-q',
      experience_id: 'projects:p2', field_path: 'projects[1].description' })]);
    session.attach()();
  });

  it('요건 없음 저장 실패는 칩을 낙관적으로 absent로 바꾸지 않는다', async () => {
    api.review.mockResolvedValueOnce({ ...firstReview, sentence_reviews: [],
      questions: [{ ...firstReview.questions[0], requirement_id: 'req-1', owner_scope: 'unassigned', field_path: '__requirement_owner__' }],
      requirement_map: [{ id: 'req-1', group: 'must', label: 'Python', status: 'unconfirmed', assessment_state: 'complete', source_hash: 'h1' }] });
    const { session } = makeSession(); await session.review();
    api.review.mockRejectedValueOnce(new Error('server unavailable'));
    session.submitNoneAnswer(session.view().activeQuestion!);
    expect(session.requirementRows[0].status).toBe('unconfirmed');
    await flush(); await flush();
    expect(session.requirementRows[0].status).toBe('unconfirmed');
    expect(session.error).toContain('저장하지 못했습니다');
    session.attach()();
  });

  it('요건 빈 응답은 이전 칩을 제거하고 저장 세션의 판정은 확인 전 대기로 둔다', async () => {
    api.review.mockResolvedValueOnce({ ...firstReview, sentence_reviews: [] });
    const { session } = makeSession(); await session.review();
    api.review.mockResolvedValueOnce({ ...firstReview, requirement_map: [], sentence_reviews: [], questions: [] });
    session.setAnswer('추가 사실입니다.'); await session.submitAnswer(session.view().activeQuestion!);
    expect(session.requirementRows).toEqual([]);
    const restored = makeSession({ tailoredResumeId: 'tailored_1', initialReviewSession: {
      version: 1, resume_id: 'r1', job_id: 'JOB-1', result: { review_id: 'rev', input_hash: 'h1' },
      requirement_map: [{ id: 'req-1', group: 'must', label: 'Python', status: 'met', assessment_state: 'complete',
        source_hash: 'h1', snapshot_hash: 'job-h', evidence_quotes: ['Python 사용'] }],
    } });
    expect(restored.session.requirementRows[0]).toMatchObject({ status: 'unconfirmed', assessmentState: 'pending', evidenceQuotes: [] });
    session.attach()(); restored.session.attach()();
  });
  it('STAR 누락 응답은 이전 원문 진단을 유지하지 않는다', async () => {
    api.review.mockResolvedValueOnce({ ...firstReview, sentence_reviews: [] });
    const { session } = makeSession();
    await session.review();
    expect(Object.keys(session.starChecks)).toHaveLength(1);
    api.review.mockResolvedValueOnce({ ...firstReview, star_checks: undefined, questions: [] });
    session.setAnswer('직접 확인했습니다.');
    await session.submitAnswer(session.view().activeQuestion!);
    expect(session.starChecks).toEqual({});
  });

  it('STAR 세션 복원은 원문 확인 전 판정 대기로 표시한다', () => {
    const { session } = makeSession({ tailoredResumeId: 'tailored_1', initialReviewSession: {
      version: 1, resume_id: 'r1', job_id: 'JOB-1', result: { review_id: 'rev-1', input_hash: 'h1' },
      star_checks: [{ field_path: 'projects[0].description', present: ['result'],
        diagnostic_status: 'complete', source_hash: 'h1', quotes: { result: '이전 결과' } }],
    } });
    expect(session.starChecks['projects[0].description']).toMatchObject({ diagnosticStatus: 'pending', present: [], quotes: {} });
  });

  it('수정안 적용 후 원문 STAR는 갱신 대기이고 질문 흐름은 유지된다', async () => {
    api.review.mockResolvedValueOnce({ ...firstReview, sentence_reviews: [sentence(0, 'content')],
      star_checks: [{ field_path: 'projects[0].description', present: ['action'],
        diagnostic_status: 'complete', source_hash: 'h1' }] });
    const { session } = makeSession();
    await session.review();
    api.apply.mockResolvedValue({ input_hash: 'h2', operation_id: 'op' });
    api.context.mockResolvedValue({ content: {}, input_hash: 'h2' });
    await session.applySuggestion([0]);
    expect(session.starChecks['projects[0].description']).toMatchObject({ diagnosticStatus: 'pending', present: [] });
    expect(session.view().activeQuestion?.question_id).toBe('q1');
    expect(api.review).toHaveBeenCalledTimes(1);
  });
  it('B 단계 응답은 표시하지 않고 같은 요청으로 검증 완료까지 이어간다', async () => {
    const pending = { review_id: 'canonical', telemetry: { execution: { state: 'processing', stage: 'write' } }, sentence_reviews: [], questions: [] };
    api.review.mockResolvedValueOnce(pending)
      .mockResolvedValueOnce({ ...pending, telemetry: { execution: { state: 'verification_pending', stage: 'verify' } } })
      .mockResolvedValueOnce({ ...firstReview, review_id: 'canonical', telemetry: { execution: { state: 'verified' } } });
    const { session } = makeSession();
    await session.review();
    expect(api.review).toHaveBeenCalledTimes(3);
    expect(api.review.mock.calls.slice(1).every(c => c[1].request_id === 'canonical')).toBe(true);
    expect(session.result?.review_id).toBe('canonical');
    expect(session.sessionCompleted).toBe(false); // verified != user has handled revisions
  });

  it('B 검증 timeout은 완료가 아니며 저장된 동일 요청을 재개한다', async () => {
    api.review.mockResolvedValueOnce({ review_id: 'canonical', sentence_reviews: [], questions: [],
      telemetry: { execution: { state: 'verification_pending', stage: 'verify', retryable_error: 'verification_unavailable' } } });
    const { session } = makeSession();
    await session.review();
    expect(session.result).toBeNull();
    expect(session.sessionCompleted).toBe(false);
    expect(session.error).toContain('검증이 완료되지 않았습니다');
    expect(api.saveSession).not.toHaveBeenCalled();
    api.review.mockResolvedValueOnce({ ...firstReview, review_id: 'canonical', telemetry: { execution: { state: 'verified' } } });
    session.retryProcessing();
    await flush(); await flush();
    expect(api.review.mock.calls.at(-1)?.[1].request_id).toBe('canonical');
    expect(session.error).toBeNull();
    expect(session.result?.review_id).toBe('canonical');
  });
  it.each(['apply', 'skip'])('답변 index 0 이후 audit index 0은 별개이며 %s 후 queue와 마지막 질문을 완료한다', async (action) => {
    api.review.mockResolvedValueOnce({ ...firstReview, sentence_reviews: [], questions: [firstReview.questions[0]] });
    const { session } = makeSession();
    await session.review();
    api.review.mockResolvedValueOnce({ ...firstReview, review_id: 'rev-answer',
      sentence_reviews: [sentence(0, 'content', { validation_status: 'READY' })], questions: [] });
    session.setAnswer('직접 구현했습니다.');
    await session.submitAnswer(session.view().activeQuestion!);
    api.apply.mockResolvedValue({ content: {}, input_hash: 'h2' });
    await session.applySuggestion([0], 'rev-answer');
    const oldCard = session.messages.find(m => m.type === 'suggestion')!;
    expect(oldCard.type === 'suggestion' && session.isSuggestionApplied(oldCard.payload)).toBe(true);
    api.review.mockResolvedValueOnce({ ...firstReview, review_id: 'rev-audit',
      sentence_reviews: Array.from({ length: 7 }, (_, i) => sentence(i, 'content', { validation_status: 'READY' })),
      questions: [{ question_id: 'q-final', field_path: 'projects[0].description', topic: 'other', question: '마지막 확인?' }] });
    session.afterRender();
    await flush(); await flush();
    const newCard = session.messages.at(-1)!;
    expect(newCard).toMatchObject({ type: 'suggestion', payload: { _index: 0, _review_id: 'rev-audit' } });
    expect(newCard.type === 'suggestion' && session.isSuggestionApplied(newCard.payload)).toBe(false);
    // Stale callbacks cannot act on the new review's index 0.
    await session.applySuggestion([0], 'rev-answer');
    session.skipSuggestion([0], 'rev-answer');
    expect(api.apply).toHaveBeenCalledTimes(1);
    if (action === 'apply') await session.applySuggestion([0], 'rev-audit');
    else session.skipSuggestion([0], 'rev-audit');
    expect(session.messages.at(-1)).toMatchObject({ payload: { _index: 1, _review_id: 'rev-audit' } });
    for (let i = 1; i < 7; i++) session.skipSuggestion([i], 'rev-audit');
    expect(session.view().activeQuestion).toMatchObject({ question_id: 'q-final' });
    expect(session.sessionCompleted).toBe(false);
    const saved = api.saveSession.mock.calls.at(-1)![2] as Json;
    const restored = makeSession({ tailoredResumeId: 'tailored_1', initialReviewSession: saved }).session;
    expect(restored.messages.filter(m => m.type === 'suggestion' && restored.isSuggestionApplied(m.payload))).toHaveLength(action === 'apply' ? 2 : 1);
    api.review.mockResolvedValueOnce({ ...firstReview, review_id: 'rev-final', sentence_reviews: [], questions: [] });
    session.setAnswer('확인했습니다.');
    await session.submitAnswer(session.view().activeQuestion!);
    expect(session.sessionCompleted).toBe(true);
    expect(session.view().reviewCompleted).toBe(true);
  });

  it('B 초기 content READY 후보를 일괄 표시하고 원래 응답 index로 선택 적용한다', async () => {
    api.review.mockResolvedValueOnce({ ...firstReview, sentence_reviews: [
      sentence(0, 'content', { validation_status: 'READY' }),
      sentence(1, 'clarity', { validation_status: 'REJECTED' }),
      sentence(2, 'content', { validation_status: 'READY' }),
    ] });
    const { session } = makeSession();
    await session.review();
    const bundle = session.messages.find((m) => m.type === 'identity');
    expect(bundle).toMatchObject({ payload: { _kind: 'polish', _indices: [0, 2] } });
    expect(session.messages.filter((m) => m.type === 'suggestion')).toHaveLength(0);
    expect(JSON.stringify(session.messages)).not.toContain('고친 문장 1');
    api.apply.mockResolvedValue({ content: {}, input_hash: 'h2' });
    await session.applySuggestion([2]);
    expect(api.apply).toHaveBeenCalledTimes(1);
    expect(api.apply.mock.calls[0][1]).toMatchObject({ selected_indices: [2] });
  });

  it('B 답변 후 READY 수정안은 초기 묶음이 아니라 해당 수정안으로 표시한다', async () => {
    api.review.mockResolvedValueOnce({ ...firstReview, sentence_reviews: [] });
    const { session } = makeSession();
    await session.review();
    api.review.mockResolvedValueOnce({ ...firstReview, sentence_reviews: [
      sentence(0, 'content', { validation_status: 'READY' }),
    ], questions: [] });
    session.setAnswer('API를 직접 구현했습니다.');
    await session.submitAnswer(session.view().activeQuestion!);
    expect(session.messages.filter((m) => m.type === 'suggestion')).toHaveLength(1);
    expect(session.messages.filter((m) => m.type === 'identity')).toHaveLength(0);
  });

  it.each([
    ['REJECTED', '검증을 통과한 수정안을 만들지 못해', []],
    ['UNCHANGED', '현재 문장을 바꿀 필요가 없어', []],
    ['NEEDS_EVIDENCE', '수정안에 필요한 정보를 조금 더', []],
    ['REJECTED', '답변과 원문은 보존했지만', ['analysis_contract_invalid']],
  ])('동일한 본문도 소유 ID로 답변하고 %s 결과를 구분한다', async (outcome, notice, issues) => {
    const questions = ['KKBOX', '자동차 정비소', 'AI LMS'].map((title, i) => ({
      question_id: `question-${i}`, experience_id: `projects:p${i}`, experience_title: title,
      field_path: `projects[${i}].description`, target_slot: 'actions', topic: 'other', stage: 3,
      question: '이 프로젝트에서 본인이 직접 수행한 작업은 무엇인가요?',
    }));
    api.review.mockResolvedValueOnce({ ...firstReview, sentence_reviews: [], questions });
    const { session } = makeSession();
    await session.review();
    expect(session.view().remainingQuestionCount).toBe(3);
    expect(session.view().activeQuestion).toMatchObject({ experience_id: 'projects:p0' });
    api.review.mockResolvedValueOnce({ ...firstReview, review_id: 'rev-2',
      sentence_reviews: [sentence(0, 'content', { suggested_revision: null, validation_status: outcome, validation_issues: issues })],
      questions: questions.slice(1) });
    session.setAnswer('직접 API를 구현했습니다.');
    await session.submitAnswer(session.view().activeQuestion!);
    expect(api.review.mock.calls[1][1]).toMatchObject({ answers: [{
      question_id: 'question-0', experience_id: 'projects:p0', field_path: 'projects[0].description',
      answer: '직접 API를 구현했습니다.',
    }] });
    expect(session.view().activeQuestion).toMatchObject({ experience_id: 'projects:p1' });
    expect(JSON.stringify(session.messages)).toContain(notice);
    expect(JSON.stringify(session.messages)).not.toContain('확인했어요. 다음으로 넘어갈게요.');
    expect(session.messages.filter((m) => m.type === 'suggestion')).toHaveLength(0);
  });
  it('B의 동일 field/topic에서 서로 다른 gap 질문을 모두 유지한다', async () => {
    const questions = ['1111111111111111', '2222222222222222', '3333333333333333'].map((key, i) => ({
      question_id: `request:v2gap:${key}`, field_path: 'projects[0].description',
      topic: 'other', question: `gap ${i}`, stage: 3,
    }));
    api.review.mockResolvedValue({ ...firstReview, sentence_reviews: [], questions });
    const { session } = makeSession();
    await session.review();
    expect(session.view().remainingQuestionCount).toBe(3);
    expect(session.view().activeQuestion).toMatchObject({ question_id: questions[0].question_id });
  });

  it('첫 첨삭: 사본을 뜨고, 공고 hash 를 실어 부르고, 요약 · 문장 다듬기 묶음부터 보여 준다', async () => {
    const { session } = makeSession();
    await session.review();

    expect(api.createTailored).toHaveBeenCalledWith('r1', 'JOB-1');
    const request = api.review.mock.calls[0][1] as Json;
    expect(request).toMatchObject({
      review_mode: 'job',
      tailored_resume_id: 'tailored_1',
      selected_job_id: 'JOB-1',
      expected_input_hash: 'h1',
      expected_job_hash: 'job-h',
    });
    // 요약은 세 문장까지 글머리표로
    expect(session.messages[0]).toEqual({
      type: 'assistant',
      text: '검토 요약\n\n• 공고와 비교했습니다.\n\n• 프로젝트 근거가 있습니다.\n\n• 수치는 없습니다.',
    });
    // 표현만 고친 두 개는 한 카드로, 질문은 수정안을 정한 뒤로 미룬다
    expect(session.messages[1]).toMatchObject({ type: 'identity', payload: { _kind: 'polish', _indices: [0, 1] } });
    expect(session.messages).toHaveLength(2);
    expect(session.pendingQuestion).toMatchObject({ question_id: 'q1' });
    expect(session.view().currentStage).toBe(1);
    expect(api.saveSession).toHaveBeenCalled();
  });

  it('건너뛰면 다음 수정안, 회사명 · 직무명 확인, 그다음 질문 순서로 나온다', async () => {
    const { session } = makeSession();
    await session.review();

    session.skipSuggestion([0, 1]);
    expect(session.messages.at(-1)).toMatchObject({ type: 'suggestion', payload: { _index: 2 } });
    session.skipSuggestion([2]);
    expect(session.messages.at(-1)).toMatchObject({
      type: 'identity',
      payload: { _indices: [3], _company: '㈜회사', _title: 'AI 개발자' },
    });
    session.skipSuggestion([3]);
    expect(session.messages.at(-1)).toMatchObject({ type: 'question', payload: { question_id: 'q1' } });
    expect(session.view().activeQuestion).toMatchObject({ question_id: 'q1' });
    expect(session.view().remainingQuestionCount).toBe(2);
  });

  it('반영하면 표시가 바뀌고 되돌리기가 생기며, 되돌리면 다시 풀린다', async () => {
    const { session } = makeSession();
    await session.review();
    api.apply.mockResolvedValue({ operation_id: 'op-1', input_hash: 'h2' });
    api.undo.mockResolvedValue({ input_hash: 'h1' });

    await session.applySuggestion([0, 1]);
    expect(api.apply.mock.calls[0][1]).toMatchObject({
      review_id: 'rev-1',
      expected_input_hash: 'h1',
      selected_indices: [0, 1],
      tailored_resume_id: 'tailored_1',
    });
    const bundle = session.messages[1];
    expect(bundle.type === 'identity' && bundle.payload).toMatchObject({ _applied: true, _undo_available: true });
    expect(session.result?.input_hash).toBe('h2');
    expect(session.changed).toBe(true);

    await session.undoSuggestion((bundle as { payload: Json }).payload);
    expect(api.undo.mock.calls[0][1]).toMatchObject({ application_id: 'op-1', expected_input_hash: 'h2' });
    expect(bundle.type === 'identity' && bundle.payload).toMatchObject({ _applied: false, _undone: true });
  });

  it('「없음」은 기다리지 않고 다음 질문을 띄우고, 기록은 뒤에서 보낸다', async () => {
    const { session } = makeSession();
    api.review.mockResolvedValueOnce({ ...firstReview, sentence_reviews: [] });
    await session.review();
    expect(session.view().activeQuestion).toMatchObject({ question_id: 'q1' });

    api.review.mockResolvedValueOnce({
      ...firstReview,
      review_id: 'rev-2',
      sentence_reviews: [],
      questions: [{ question_id: 'q2b', field_path: 'projects[1].description', topic: 'action', question: '무엇을 했나요?', stage: 3 }],
      telemetry: { model_skipped: 'none_answer' },
    });
    session.submitNoneAnswer(session.view().activeQuestion!);
    // 바로 다음 질문
    expect(session.messages.slice(-3).map((m) => m.type)).toEqual(['user', 'assistant', 'question']);
    await flush();
    await flush();
    const noneCall = api.review.mock.calls[1][1] as Json;
    expect(noneCall).toMatchObject({ previous_review_id: 'rev-1', answers: [{ question_id: 'q1', answer: '없음' }] });
    // 서버가 새로 매긴 질문 번호를 떠 있는 질문이 받는다
    expect(session.view().activeQuestion).toMatchObject({ question_id: 'q2b' });
  });

  it('질문을 다 마치면 누락 점검을 한 번 하고 완료 안내를 띄운다', async () => {
    const { session } = makeSession();
    api.review.mockResolvedValueOnce({ ...firstReview, sentence_reviews: [], questions: [] });
    api.review.mockResolvedValueOnce({ ...firstReview, review_id: 'rev-gap', sentence_reviews: [], questions: [] });
    await session.review();
    session.afterRender();
    await flush();
    await flush();
    const gap = api.review.mock.calls[1][1] as Json;
    expect(gap).toMatchObject({ review_phase: 'gap_audit', previous_review_id: 'rev-1' });
    expect(session.messages.at(-1)).toEqual({
      type: 'assistant',
      text: '누락 점검까지 완료했습니다. 추가로 확인할 중요한 항목이 없습니다.',
    });
    expect(session.view().reviewCompleted).toBe(true);
    expect(session.sessionCompleted).toBe(true);
  });

  it('첨삭 완료는 대화를 저장하고 사본을 편집기로 옮겨 그 id 로 닫는다', async () => {
    const { session, closed } = makeSession();
    api.promote.mockResolvedValue('matched_1');
    await session.review();
    await session.completeReview();
    expect(api.promote).toHaveBeenCalledWith('r1', 'tailored_1');
    expect(closed).toEqual(['matched_1']);
    const saved = api.saveSession.mock.calls.at(-1)![2] as Json;
    expect(saved).toMatchObject({ version: 1, job_id: 'JOB-1', manually_completed: true, completed: true });
  });

  it('저장된 대화로 다시 열면 이어 간다 — 다른 공고의 대화는 버린다', () => {
    const saved: Json = {
      version: 1,
      resume_id: 'r1',
      job_id: 'JOB-1',
      result: { review_id: 'rev-1', input_hash: 'h1' },
      messages: [{ type: 'assistant', text: '검토 요약' }],
      question_queue: [],
      pending_question: null,
    };
    const { session } = makeSession({ tailoredResumeId: 'tailored_1', initialReviewSession: saved });
    expect(session.messages).toEqual([{ type: 'assistant', text: '검토 요약' }]);
    const other = makeSession({ tailoredResumeId: 'tailored_1', initialReviewSession: { ...saved, job_id: 'JOB-2' } });
    expect(other.session.messages).toEqual([]);
  });

  it('일반 첨삭은 사본을 만들지 않고 대화도 저장하지 않는다', async () => {
    const { session } = makeSession({ generalReview: true });
    await session.review();
    expect(api.createTailored).not.toHaveBeenCalled();
    expect(api.review.mock.calls[0][1]).toMatchObject({ review_mode: 'general' });
    expect(api.review.mock.calls[0][1]).not.toHaveProperty('selected_job_id');
    expect(api.saveSession).not.toHaveBeenCalled();
  });
});

describe('수정안에서 바뀐 글자만 굵게', () => {
  it('앞뒤가 같으면 가운데 바뀐 부분만', () => {
    expect(changedRevisionSpans('데이터를 분석했습니다', '데이터를 정제해 분석했습니다')).toEqual([
      { text: '데이터를 ', changed: false },
      { text: '정제해 ', changed: true },
      { text: '분석했습니다', changed: false },
    ]);
  });
  it('원문이 비면 전부 새 글자, 같으면 그대로', () => {
    expect(changedRevisionSpans('', '새 문장')).toEqual([{ text: '새 문장', changed: true }]);
    expect(changedRevisionSpans('같음', '같음')).toEqual([{ text: '같음', changed: false }]);
  });
});
