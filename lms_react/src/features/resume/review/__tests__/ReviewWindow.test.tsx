import { act, useEffect } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Json } from '../reviewApi';
import { ReviewStarCells, ReviewRequirementStrip, requirementRowsFrom } from '../reviewRequirements';
import sourceQuestions from './questionSourcePublic.json';

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
vi.mock('../../../../data/repository', () => ({ applyBootstrap: vi.fn(() => Promise.resolve()) }));

const { ReviewDockHost, useReviewDock } = await import('../ReviewDock');

// jsdom 에 없는 것들
globalThis.ResizeObserver ??= class {
  observe() {}
  disconnect() {}
  unobserve() {}
} as unknown as typeof ResizeObserver;
Element.prototype.scrollTo ??= function scrollTo() {};
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const review: Json & { sentence_reviews: Json[] } = {
  review_id: 'rev-1',
  input_hash: 'h1',
  summary: '이력서와 공고를 비교했습니다.',
  job_source: { company: '㈜유니포유', title: 'Python AI LLM 개발자', snapshot_hash: 'job-h' },
  sentence_reviews: [
    { field_path: 'projects[0].description', original_quote: '데이터를 분석했습니다', suggested_revision: '데이터를 정제해 분석했습니다', edit_type: 'clarity' },
    { field_path: 'projects[1].description', original_quote: '모델을 만들었습니다', suggested_revision: '분류 모델을 만들었습니다', edit_type: 'tone' },
    { field_path: 'coreCompetencies.text', original_quote: '협업을 잘합니다', suggested_revision: 'Git 으로 협업했습니다', edit_type: 'content', reason: '근거가 있습니다' },
  ],
  questions: [{ question_id: 'q1', field_path: 'projects[0].description', topic: 'result', question: '성과 수치가 있나요?', stage: 3 }],
  requirement_map: [
    { id: 'req-1', group: 'must', label: 'Python', status: 'met', evidence_paths: ['techStack[0].name'] },
    { id: 'req-2', group: 'preferred', label: 'Kafka', status: 'unconfirmed' },
  ],
  star_checks: [],
};

function Opener({ saved }: { saved?: Json } = {}) {
  const { openReview } = useReviewDock();
  useEffect(() => {
    openReview('job-review-r1-JOB-1', {
      resumeId: 'r1',
      generalReview: false,
      jobId: 'JOB-1',
      jobCompany: '㈜유니포유',
      jobTitle: 'Python AI LLM 개발자',
      ...(saved ? { tailoredResumeId: 'tailored_1', initialReviewSession: saved } : {}),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return null;
}

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.context.mockResolvedValue({
    content: {
      basicInfo: { name: '김학생', email: 'student@playdata.co.kr' },
      coreCompetencies: { text: '협업을 잘합니다' },
      techStack: [{ name: 'Python', level: '상' }],
      projects: [{ name: '추천 서비스', role: '백엔드', description: '데이터를 분석했습니다' }],
    },
    input_hash: 'h1',
    job_source: { snapshot_hash: 'job-h' },
  });
  api.createTailored.mockResolvedValue({ tailored_resume_id: 'tailored_1', content: { basicInfo: { name: '김학생' } }, review_session: {} });
  api.saveSession.mockResolvedValue({ saved: true });
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const text = () => document.body.textContent ?? '';
const button = (label: string) =>
  [...document.querySelectorAll('button')].find((b) => b.textContent?.includes(label)) as HTMLButtonElement | undefined;
const settle = () => act(() => new Promise((resolve) => setTimeout(resolve, 0)));

describe('첨삭 창', () => {
  it('부분 실패 완료 안내와 요건 대기를 성공 및 0/N으로 표시하지 않는다',async ()=>{
    const saved={version:1,resume_id:'r1',job_id:'JOB-1',result:{...review,questions:[],
      requirement_map:[{id:'r',group:'must',label:'요건',status:'partial',assessment_state:'pending'}],
      sentence_reviews:[{...review.sentence_reviews[0],validation_status:'READY'}],
      telemetry:{experience_outcomes:[{experience_id:'growth',status:'REJECTED'},{experience_id:'lms',status:'READY'}]}},
      requirement_map:[{id:'r',group:'must',label:'요건',status:'partial',assessment_state:'pending'}],
      messages:[],question_queue:[],suggestion_queue:[],gap_audit_started:true,gap_audit_finished:true};
    act(()=>root.render(<MemoryRouter><ReviewDockHost><Opener saved={saved} /></ReviewDockHost></MemoryRouter>));
    await settle();
    const notice=document.querySelector('.rv-done')!;
    expect(notice.textContent).toContain('일부 항목 재검토 필요');expect(notice.textContent).toContain('필수 대조 대기');
    expect(notice.textContent).not.toContain('0/1');expect(notice.querySelector('strong')?.textContent).not.toBe('첨삭 완료');
  });
  it('질문 흐름이 끝나도 공고 요건 대조 미완료를 첨삭 성공으로 표시하지 않는다',async ()=>{
    const saved={version:1,resume_id:'r1',job_id:'JOB-1',result:{...review,questions:[],sentence_reviews:[],
      requirement_map:[{id:'r',group:'must',label:'요건',posting_quote:'요건',status:'partial',assessment_state:'pending'}],
      telemetry:{information_review:{state:'pending',unreviewed_experiences:0,open_opportunities:0,
        requirements:[{requirement_id:'r',state:'partially_supported',assessment:'pending'}]}}},
      requirement_map:[{id:'r',group:'must',label:'요건',posting_quote:'요건',status:'partial',assessment_state:'pending'}],
      messages:[],question_queue:[],suggestion_queue:[],gap_audit_started:true,gap_audit_finished:true};
    act(()=>root.render(<MemoryRouter><ReviewDockHost><Opener saved={saved} /></ReviewDockHost></MemoryRouter>));
    await settle();
    const notice=document.querySelector('.rv-done')!;
    expect(notice.querySelector('strong')?.textContent).toBe('첨삭 흐름 종료 · 일부 검토 대기');
    expect(notice.textContent).toContain('공고 요건 1개의 근거 대조가 미완료');
    expect(notice.textContent).toContain('자동 재요청 예정이라는 뜻은 아닙니다');
  });
  it.each(sourceQuestions)('저장 review $review_id 공개 질문의 대상·요구 정보를 그대로 표시한다', async row => {
    // Explicit offline conversion, not a replay of old model-produced new fields.
    const q=row.public_payload;
    const saved={version:1,resume_id:'r1',job_id:'JOB-1',result:{...review,sentence_reviews:[],questions:[q]},
      messages:[{type:'question',payload:q}],question_queue:[],suggestion_queue:[]};
    act(()=>root.render(<MemoryRouter><ReviewDockHost><Opener saved={saved} /></ReviewDockHost></MemoryRouter>));
    await settle();
    expect(text()).toContain(q.experience_title);expect(text()).toContain(q.question);
    expect(document.querySelector('.rv-question-box__body')?.textContent).toBe(q.question);
    const quotes=[...document.querySelectorAll('.rv-bubble blockquote')].map(e=>e.textContent);
    expect(quotes).toEqual(q.target_contexts.map(c=>c.quote));
    const marks=[...document.querySelectorAll('.rv-bubble mark')].map(e=>e.textContent);
    for (const context of q.target_contexts) {
      for (const term of context.anchors.length ? context.anchors : context.selected_source_quotes) expect(marks).toContain(term);
    }
  });
  it('anchor 없는 fallback도 대상 원문을 강조해 익명 질문으로 표시하지 않는다', async () => {
    const row=sourceQuestions.find(r=>r.review_id===121)!;
    const q={...row.public_payload,target_contexts:row.no_anchor_fallback_contexts};
    const saved={version:1,resume_id:'r1',job_id:'JOB-1',result:{...review,sentence_reviews:[],questions:[q]},
      messages:[{type:'question',payload:q}],question_queue:[],suggestion_queue:[]};
    act(()=>root.render(<MemoryRouter><ReviewDockHost><Opener saved={saved} /></ReviewDockHost></MemoryRouter>));
    await settle();
    expect(document.querySelector('.rv-bubble mark')?.textContent).toContain('days_to_expire');
    expect(document.querySelector('.rv-bubble blockquote')?.textContent).toContain('XGBoost');
  });
  it('질문 대상은 원문 안에서 한 번 강조하고 부정·조건을 잘라 표시하지 않는다', async () => {
    const question={question_id:'new',field_path:'projects[0].description',experience_title:'분석 경험',
      question:'어떤 방법으로 직접 점검했나요?\n시험 수행만으로 성공을 단정하지 않아도 됩니다.',target_contexts:[{type:'applicant_source',source_type:'resume_text',
        quote:'단일 변수 AUC 0.905를 확인했지만 전체 모델 성능은 아닙니다.',anchors:['AUC 0.905'],
        selected_source_quotes:['AUC 0.905'],context_quote:'앞의 목적 설명. 단일 변수 AUC 0.905를 확인했지만 전체 모델 성능은 아닙니다.'}]};
    const saved={version:1,resume_id:'r1',job_id:'JOB-1',result:{...review,sentence_reviews:[],questions:[question]},
      messages:[{type:'question',payload:question}],question_queue:[],suggestion_queue:[]};
    act(()=>root.render(<MemoryRouter><ReviewDockHost><Opener saved={saved} /></ReviewDockHost></MemoryRouter>));
    await settle();
    const bubble=document.querySelector('.rv-bubble')!;
    expect(bubble.querySelector('blockquote')?.textContent).toBe(question.target_contexts[0].quote);
    expect(bubble.querySelectorAll('mark')).toHaveLength(1);
    expect(bubble.querySelector('mark')?.textContent).toBe('AUC 0.905');
    expect(bubble.querySelector('details')?.hasAttribute('open')).toBe(false);
    const box=bubble.querySelector('.rv-question-box')!;
    expect(box.getAttribute('aria-label')).toBe('답변할 질문');
    expect(box.querySelector('.rv-question-box__body')?.textContent).toBe(question.question);
    expect(bubble.querySelector('details')!.compareDocumentPosition(box) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
    expect(text()).not.toContain('원문에서 선택한 구간');expect(text()).not.toContain('지목한 원문 표현');
  });
  it.each([
    {contexts:[],label:null},
    {contexts:[{type:'applicant_source',source_type:'user_answer',quote:'이전 답변 원문입니다.'}],label:'이전 답변에서 확인할 부분'},
    {contexts:[{type:'posting_source',quote:'공고 원문입니다.'}],label:'공고 요건 · 지원자 경험과 별개'},
  ])('질문 박스가 출처 유무와 종류에 관계없이 전체 질문을 보존한다 ($label)',async ({contexts,label})=>{
    const q={question_id:'source-kind',field_path:'projects[0].description',question:'기억나는 범위에서 알려주세요.',target_contexts:contexts};
    const saved={version:1,resume_id:'r1',job_id:'JOB-1',result:{...review,sentence_reviews:[],questions:[q]},
      messages:[{type:'question',payload:q}],question_queue:[],suggestion_queue:[]};
    act(()=>root.render(<MemoryRouter><ReviewDockHost><Opener saved={saved} /></ReviewDockHost></MemoryRouter>));
    await settle();
    expect(document.querySelector('.rv-question-box__body')?.textContent).toBe(q.question);
    expect(document.querySelector('.rv-question-box__label')?.textContent).toBe('답변할 질문');
    expect([...document.querySelectorAll('.rv-question-source blockquote')].map(e=>e.textContent)).toEqual(contexts.map(c=>c.quote));
    if (label) expect(text()).toContain(label);
  });
  it('B 답변 관리에서 취소를 서버로 보내고 문서 반영 취소와 구분한다', async () => {
    const question=(review.questions as Json[])[0];
    const saved={version:1,resume_id:'r1',job_id:'JOB-1',result:{...review,sentence_reviews:[],questions:[],
      telemetry:{engine:'v2-local-ui-2',answer_edit_supported:true},confirmed_answers:[{...question,answer:'오입력'}]},messages:[],question_queue:[],suggestion_queue:[],
      gap_audit_started:true,gap_audit_finished:true,manually_completed:true};
    api.review.mockResolvedValue({...review,review_id:'repaired',sentence_reviews:[],confirmed_answers:[],
      telemetry:{engine:'v2-local-ui-2',answer_edit_supported:true,execution:{state:'verified'},answer_recovery:{question_id:'q1',operation:'retract',requires_document_undo:false}}});
    const confirm=vi.spyOn(window,'confirm').mockReturnValue(true);
    act(() => root.render(<MemoryRouter><ReviewDockHost><Opener saved={saved} /></ReviewDockHost></MemoryRouter>));
    await settle();
    expect(text()).toContain('답변 수정·취소');expect(text()).toContain('자동 삭제되지');
    await act(async () => button('답변 취소')!.click());
    expect(api.review.mock.calls[0][1].answer_changes).toEqual([expect.objectContaining({question_id:'q1',operation:'retract',expected_answer:'오입력'})]);
    expect(api.undo).not.toHaveBeenCalled();
    confirm.mockRestore();
  });
  it('미판정 요건은 0/N 확정 표시가 아니라 대조 대기로 표시한다', () => {
    const rows = requirementRowsFrom([{ id: 'r1', group: 'must', label: '기술 활용', status: 'unconfirmed', assessment_state: 'pending' }]);
    act(() => root.render(<ReviewRequirementStrip rows={rows} onTapRow={() => {}} />));
    expect(text()).toContain('필수 대조 대기');
    expect(text()).not.toContain('0/1');
    expect(document.querySelector('button[title*="미판정"]')).not.toBeNull();
  });
  it('원문 STAR의 미확인은 부족 체크리스트가 아니며 근거 인용을 제공한다', () => {
    act(() => root.render(<ReviewStarCells check={{ fieldPath: 'projects[0].description', present: ['action'],
      reason: '', diagnosticStatus: 'complete', quotes: { action: 'API를 구현했습니다.' } }} />));
    expect(text()).toContain('현재 원문 STAR');
    expect(text()).toContain('결과 근거 미확인');
    expect(text()).not.toContain('빠짐');
    expect(document.querySelector('[title="API를 구현했습니다."]')).not.toBeNull();
    act(() => root.render(<ReviewStarCells check={{ fieldPath: 'projects[0].description', present: [], reason: '', diagnosticStatus: 'pending' }} />));
    expect(text()).toContain('판정 대기');
    expect(text()).not.toContain('근거 미확인');
    act(() => root.render(<ReviewStarCells check={{ fieldPath: 'selfIntroduction.motivation.body', present: [], reason: '', diagnosticStatus: 'not_applicable' }} />));
    expect(text()).toBe('');
  });
  it('이전 review index 0의 적용 기록은 audit index 0 카드를 적용됨으로 표시하지 않는다', async () => {
    const saved: Json = { version: 1, resume_id: 'r1', job_id: 'JOB-1',
      result: { review_id: 'audit-review', input_hash: 'h1' }, gap_audit_started: true, gap_audit_finished: true,
      applied_suggestion_keys: [JSON.stringify(['answer-review', 0])], applied_indices: [0],
      messages: [
        { type: 'suggestion', payload: { ...review.sentence_reviews[0], _review_id: 'answer-review', _index: 0, _applied: true } },
        { type: 'suggestion', payload: { ...review.sentence_reviews[1], _review_id: 'audit-review', _index: 0 } },
      ], question_queue: [], suggestion_queue: [], pending_question: null };
    act(() => root.render(<MemoryRouter><ReviewDockHost><Opener saved={saved} /></ReviewDockHost></MemoryRouter>));
    await settle();
    expect(document.querySelectorAll('.rv-applied')).toHaveLength(1);
    expect(text()).toContain('분류 모델을 만들었습니다');
    expect(button('이 문장으로 바꾸기')).toBeDefined();
    api.apply.mockResolvedValue({ content: {}, input_hash: 'h2' });
    await act(async () => button('이 문장으로 바꾸기')!.click());
    expect(api.apply.mock.calls[0][1]).toMatchObject({ review_id: 'audit-review', selected_indices: [0] });
    expect(document.querySelectorAll('.rv-applied')).toHaveLength(2);
  });

  it('B 초기 content 수정안을 기존 체크박스 묶음에 동시에 표시한다', async () => {
    api.review.mockResolvedValue({ ...review, sentence_reviews: review.sentence_reviews.map((item: Json, i: number) => ({
      ...item, edit_type: 'content', validation_status: i === 2 ? 'REJECTED' : 'READY',
    })) });
    act(() => root.render(<MemoryRouter><ReviewDockHost><Opener /></ReviewDockHost></MemoryRouter>));
    await settle();
    await act(async () => button('첨삭 시작')!.click());
    await settle();
    expect(text()).toContain('문장 다듬기 2개');
    expect(text()).toContain('데이터를 정제해 분석했습니다');
    expect(text()).toContain('분류 모델을 만들었습니다');
    expect(text()).not.toContain('Git 으로 협업했습니다');
    expect(document.querySelectorAll('input[type="checkbox"]').length).toBe(2);
    expect(api.apply).not.toHaveBeenCalled();
  });
  it.each([false, true])('교육 질문은 과거 내부 ID label도 현재 교육명으로 표시한다 (legacy=%s)', async (legacy) => {
    const question = { question_id: 'training-q', experience_id: 'trainingExperience:tr-one',
      experience_title: legacy ? 'trainingExperience:tr-one' : 'SK Networks Family AI Camp 34th', field_path: 'trainingExperience[0].description',
      topic: 'other', question: '실습에서 확인한 점은 무엇인가요?' };
    api.context.mockResolvedValue({ content: { trainingExperience: [
      { id: 'other', course: '다른 과정' }, { id: 'tr-one', course: 'SK Networks Family AI Camp 34th' },
    ] }, input_hash: 'h1', job_source: { snapshot_hash: 'job-h' } });
    api.tailored.mockResolvedValue({ content: { trainingExperience: [
      { id: 'other', course: '다른 과정' }, { id: 'tr-one', course: 'SK Networks Family AI Camp 34th' },
    ] }, review_session: {} });
    const saved: Json = { version: 1, resume_id: 'r1', job_id: 'JOB-1',
      result: { review_id: 'review-1', input_hash: 'h1', questions: [question] },
      messages: [{ type: 'question', text: '', payload: question }], question_queue: [], pending_question: null };
    act(() => root.render(<MemoryRouter><ReviewDockHost><Opener saved={saved} /></ReviewDockHost></MemoryRouter>));
    await settle();
    expect(document.querySelector('.rv-question-experience')?.textContent).toBe('경험 · SK Networks Family AI Camp 34th');
    expect(text()).not.toContain('trainingExperience:tr-one');
    expect(api.review).not.toHaveBeenCalled();
  });
  it('같은 질문 본문에도 각 프로젝트 label을 대화 카드에 표시한다', async () => {
    const names = ['KKBOX 사용자 이탈 예측', '위치 기반 자동차 정비소 검색', 'AI LMS'];
    const questions = names.map((name, i) => ({
      question_id: `q-${i}`, experience_id: `projects:p${i}`, experience_title: name,
      field_path: `projects[${i}].description`, target_slot: 'actions', topic: 'other',
      question: '이 프로젝트에서 본인이 직접 수행한 작업은 무엇인가요?', evidence_basis: [],
    }));
    const saved: Json = {
      version: 1, resume_id: 'r1', job_id: 'JOB-1',
      result: { review_id: 'review-1', input_hash: 'h1', questions },
      messages: questions.map(payload => ({ type: 'question', text: '', payload })),
      question_queue: [], pending_question: null,
    };
    act(() => root.render(<MemoryRouter><ReviewDockHost><Opener saved={saved} /></ReviewDockHost></MemoryRouter>));
    await settle();
    const labels = [...document.querySelectorAll('.rv-question-experience')].map(el => el.textContent);
    expect(labels).toEqual(names.map(name => `프로젝트 · ${name}`));
    expect(api.review).not.toHaveBeenCalled();
  });
  it('열면 머리줄 · 미리보기 · 첨삭 시작이 보이고, 첨삭하면 요건 줄 · 단계 · 다듬기 카드가 뜬다', async () => {
    let finish!: (value: Json) => void;
    api.review.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    act(() =>
      root.render(
        <MemoryRouter>
          <ReviewDockHost>
            <Opener />
          </ReviewDockHost>
        </MemoryRouter>,
      ),
    );
    await settle();
    expect(text()).toContain('공고 맞춤 이력서 첨삭');
    expect(text()).toContain('㈜유니포유 Python AI LLM 개발자');
    expect(text()).toContain('선택 공고 기준으로 이력서를 확인합니다.');
    expect(text()).toContain('김학생');
    expect(text()).toContain('추천 서비스');

    await act(async () => button('첨삭 시작')!.click());
    await settle();
    // 기다리는 동안: 단계 카드와 내려두기
    expect(text()).toContain('공고 맞춤 첨삭 준비 중');
    expect(text()).toContain('경험·문장 점검');
    expect(button('내려두기')).toBeDefined();

    // 내려두면 아래 막대만 남는다
    await act(async () => button('내려두기')!.click());
    expect(document.querySelector('.rv-layer')?.hasAttribute('hidden')).toBe(true);
    expect(text()).toContain('공고 맞춤 첨삭 중');
    await act(async () => button('펼치기')!.click());

    await act(async () => finish(review));
    await settle();
    expect(text()).toContain('검토 요약');
    expect(text()).toContain('공고 요건 대조');
    expect(text()).toContain('필수 1/1 · 우대 0/1 근거 확인');
    expect(text()).toContain('문장 다듬기 2개');
    expect(text()).toContain('선택한 2개 적용');
    expect(button('첨삭 완료')).toBeDefined();
    // 바뀐 글자만 굵게
    expect([...document.querySelectorAll('.rv-revision b')].map((b) => b.textContent)).toContain('정제해 ');

    // 건너뛰면 내용 수정안 카드가 나온다
    await act(async () => button('건너뛰기')!.click());
    expect(text()).toContain('문장 다듬기를 건너뛰었습니다.');
    expect(text()).toContain('AI 수정안');
    expect(text()).toContain('이 문장으로 바꾸기');
    // 수정안을 정하기 전에는 질문 입력을 막고 이유를 말한다
    expect((document.querySelector('.rv-answer textarea') as HTMLTextAreaElement).placeholder).toBe(
      '수정안을 반영하면 다음 질문을 이어갑니다.',
    );
    await act(async () => button('건너뛰기')!.click());
    expect(text()).toContain('성과 수치가 있나요?');
    expect(text()).toContain('남은 질문 약 1개');
  });
});
