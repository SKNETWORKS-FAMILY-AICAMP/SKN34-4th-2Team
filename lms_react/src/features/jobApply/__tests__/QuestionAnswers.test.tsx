import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ questionAnswer: vi.fn() }));
const repo = vi.hoisted(() => ({ updateResume: vi.fn(() => Promise.resolve()) }));
const question = { id: 'cq1', question: '지원 동기를 쓰시오.', limit: 500, answer: '' };
// 화면이 읽는 자소서. 테스트마다 문항을 바꿔 끼운다
const store = vi.hoisted(() => ({ questions: [] as unknown[] }));

vi.mock('../../resume/review/reviewApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../resume/review/reviewApi')>()),
  reviewApi: api,
}));
vi.mock('../../../data/repository', () => ({
  useResume: () => ({ id: 'r1/tailored/apply_1', content: { companyQuestions: store.questions } }),
  updateResume: repo.updateResume,
}));

const { QuestionAnswers } = await import('../QuestionAnswers');

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  store.questions = [question];
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.clearAllMocks();
});

const flush = () => act(async () => {
  await new Promise((resolve) => setTimeout(resolve, 0));
});

function type(el: HTMLTextAreaElement, value: string) {
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set?.call(el, value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

const button = (label: string) => [...host.querySelectorAll('button')].find((b) => b.textContent?.includes(label)) as HTMLButtonElement;

describe('문항 답변 — 메모로 쓰기', () => {
  it('키워드 메모를 근거로 실어 보내고, 초안의 메모 근거를 표시한다', async () => {
    api.questionAnswer.mockResolvedValue({
      draft: '마케팅 인턴 때 인스타그램 운영을 맡았습니다.',
      char_count: 25,
      limit: 500,
      sentences: [{ text: '마케팅 인턴 때 인스타그램 운영을 맡았습니다.', basis: 'answer', quote: '인스타 운영 맡음', requirement_ids: [] }],
      dropped: 0,
      gaps: [{ requirement_id: '', question: '팔로워는 얼마에서 얼마로 늘었나요?' }],
      requirements: [],
    });
    act(() => root.render(<QuestionAnswers resumeId="r1" tailoredId="apply_1" editId="r1/tailored/apply_1" />));
    expect(button('AI 초안 쓰기')).toBeTruthy();

    type(host.querySelector('#qa-memo-cq1') as HTMLTextAreaElement, '마케팅 인턴, 인스타 운영 맡음');
    act(() => button('메모로 쓰기').click());
    await flush();

    expect(api.questionAnswer).toHaveBeenCalledWith('r1', 'apply_1', 'cq1', [
      { question: '「지원 동기를 쓰시오.」에 쓰고 싶은 내용 (지원자 메모)', answer: '마케팅 인턴, 인스타 운영 맡음' },
    ]);
    // 빈 칸이었으니 초안이 들어가고, 근거가 「내 메모 · 답변」으로 보인다
    expect((host.querySelector('textarea[aria-label="문항 1 답변"]') as HTMLTextAreaElement).value).toBe('마케팅 인턴 때 인스타그램 운영을 맡았습니다.');
    expect(host.querySelector('.qa-basis--answer')?.textContent).toBe('내 메모·답변');
    expect(host.textContent).toContain('팔로워는 얼마에서 얼마로 늘었나요?');
  });

  it('질문에 답하고 다시 쓰면 메모와 답을 함께 보낸다', async () => {
    api.questionAnswer.mockResolvedValue({
      draft: '', char_count: 0, limit: 500, sentences: [], dropped: 0,
      gaps: [{ requirement_id: '', question: '팔로워는 얼마에서 얼마로 늘었나요?' }], requirements: [],
    });
    act(() => root.render(<QuestionAnswers resumeId="r1" tailoredId="apply_1" editId="r1/tailored/apply_1" />));
    type(host.querySelector('#qa-memo-cq1') as HTMLTextAreaElement, '인스타 운영');
    act(() => button('메모로 쓰기').click());
    await flush();

    type(host.querySelector('.qa-gap textarea') as HTMLTextAreaElement, '3천에서 6천으로');
    act(() => button('답하고 다시 쓰기').click());
    await flush();

    expect(api.questionAnswer).toHaveBeenLastCalledWith('r1', 'apply_1', 'cq1', [
      { question: '「지원 동기를 쓰시오.」에 쓰고 싶은 내용 (지원자 메모)', answer: '인스타 운영' },
      { question: '팔로워는 얼마에서 얼마로 늘었나요?', answer: '3천에서 6천으로' },
    ]);
  });

  it('메모는 칸에서 나갈 때, 질문 답은 초안을 쓸 때 저장하고, 다시 열면 이어 쓴다', async () => {
    api.questionAnswer.mockResolvedValue({
      draft: '', char_count: 0, limit: 500, sentences: [], dropped: 0,
      gaps: [{ requirement_id: '', question: '팔로워는 얼마에서 얼마로 늘었나요?' }], requirements: [],
    });
    act(() => root.render(<QuestionAnswers resumeId="r1" tailoredId="apply_1" editId="r1/tailored/apply_1" />));
    const memo = host.querySelector('#qa-memo-cq1') as HTMLTextAreaElement;
    type(memo, '인스타 운영');
    act(() => memo.dispatchEvent(new FocusEvent('focusout', { bubbles: true })));
    expect(repo.updateResume).toHaveBeenLastCalledWith('r1/tailored/apply_1', {
      content: { companyQuestions: [{ ...question, memo: '인스타 운영' }] },
    });

    act(() => button('메모로 쓰기').click());
    await flush();
    type(host.querySelector('.qa-gap textarea') as HTMLTextAreaElement, '3천에서 6천으로');
    act(() => button('답하고 다시 쓰기').click());
    await flush();
    const notes = [{ question: '팔로워는 얼마에서 얼마로 늘었나요?', answer: '3천에서 6천으로' }];
    expect(repo.updateResume).toHaveBeenLastCalledWith('r1/tailored/apply_1', {
      content: { companyQuestions: [{ ...question, memo: '인스타 운영', notes }] },
    });

    // 새로고침 — 저장된 메모와 질문 답으로 다시 연다
    act(() => root.unmount());
    root = createRoot(host);
    store.questions = [{ ...question, memo: '인스타 운영', notes }];
    act(() => root.render(<QuestionAnswers resumeId="r1" tailoredId="apply_1" editId="r1/tailored/apply_1" />));
    expect((host.querySelector('#qa-memo-cq1') as HTMLTextAreaElement).value).toBe('인스타 운영');
    act(() => button('메모로 쓰기').click());
    await flush();
    expect(api.questionAnswer).toHaveBeenLastCalledWith('r1', 'apply_1', 'cq1', [
      { question: '「지원 동기를 쓰시오.」에 쓰고 싶은 내용 (지원자 메모)', answer: '인스타 운영' },
      ...notes,
    ]);
  });

  it('두 문항이 연달아 저장해도 서로의 메모를 덮지 않는다', () => {
    const second = { id: 'cq2', question: '협업 경험을 쓰시오.', limit: 500, answer: '' };
    store.questions = [question, second];
    act(() => root.render(<QuestionAnswers resumeId="r1" tailoredId="apply_1" editId="r1/tailored/apply_1" />));
    for (const [id, value] of [['cq1', '인스타 운영'], ['cq2', '디자이너와 주간 회의']]) {
      const el = host.querySelector(`#qa-memo-${id}`) as HTMLTextAreaElement;
      type(el, value);
      act(() => el.dispatchEvent(new FocusEvent('focusout', { bubbles: true })));
    }
    expect(repo.updateResume).toHaveBeenLastCalledWith('r1/tailored/apply_1', {
      content: { companyQuestions: [{ ...question, memo: '인스타 운영' }, { ...second, memo: '디자이너와 주간 회의' }] },
    });
  });
});
