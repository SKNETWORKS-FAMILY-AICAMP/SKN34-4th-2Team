import { act, useEffect } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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

const review: Json = {
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
