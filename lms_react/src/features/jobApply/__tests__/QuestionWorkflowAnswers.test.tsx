import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ questionWorkflow: vi.fn() }));
const repo = vi.hoisted(() => ({ updateResume: vi.fn(() => Promise.resolve()) }));
const store = vi.hoisted(() => ({ questions: [] as unknown[] }));

vi.mock('../../resume/review/reviewApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../resume/review/reviewApi')>()),
  reviewApi: api,
}));
vi.mock('../../../data/repository', () => ({
  useResume: () => ({ id: 'r1/tailored/apply_1', content: { companyQuestions: store.questions } }),
  updateResume: repo.updateResume,
}));

const { QuestionWorkflowAnswers } = await import('../QuestionWorkflowAnswers');

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  store.questions = [
    { id: 'cq1', question: '지원 동기를 쓰시오.', limit: 500, answer: '', memo: '데이터로 문제 해결' },
    { id: 'cq2', question: '역량을 쓰시오.', limit: 500, answer: '직접 쓴 답', notes: [{ question: '경험 선택', answer: '', source_type: 'selection' }] },
  ];
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
const answerBox = (n: number) => host.querySelector(`textarea[aria-label="문항 ${n} 답변"]`) as HTMLTextAreaElement;

const plan = { cq1: { question_id: 'cq1', angle: '지원 이유' }, cq2: { question_id: 'cq2', angle: '역량' } };
const response = {
  plan,
  overlaps: [{ story: '추천 품질 개선', keep: 'cq2', others: ['cq1'], reason: '역량 문항' }],
  questions: [
    { question_id: 'cq1', draft: '데이터로 문제를 해결하고 싶어 지원했습니다.', char_count: 22, limit: 500, angle: '지원 이유',
      trimmed_overlap: ['추천 품질 개선'], removed: [], questions: ['이 회사를 고른 이유는 무엇인가요?'],
      sentences: [{ text: '데이터로 문제를 해결하고 싶어 지원했습니다.', sources: [{ kind: 'memo', label: '지원자 메모', text: '데이터로 문제 해결' }] }] },
    { question_id: 'cq2', draft: '추천 품질을 개선했습니다.', char_count: 13, limit: 500, angle: '역량',
      removed: [], questions: [],
      sentences: [{ text: '추천 품질을 개선했습니다.', sources: [{ kind: 'resume', label: 'projects[0].description', text: '추천 품질 개선' }],
        requirements: [{ id: 'R2', label: '필수 · 검색·추천 품질 평가' }] }] },
  ],
  coverage: {
    requirements: [{ id: 'R1', group: 'must', label: 'Python', covered: false }, { id: 'R2', group: 'must', label: '검색·추천 품질 평가', covered: true },
      { id: 'R3', group: 'preferred', label: 'AWS', covered: false }],
    unused_must: [{ id: 'R1', label: 'Python' }], missing_must: [],
  },
};

/** 문항 전체 쓰기는 계획 → 문항마다 → 한 벌 점검 세 번에 부른다. 한 벌 점검은 1번을 겹침 때문에 줄여 다시 쓴다 */
const TRIMMED = '데이터로 문제를 해결하고 싶어 지원했고, 그 이유를 짧게 적었습니다.';
type Options = { only?: string; stage?: string };
function staged(options: Options) {
  if (options.stage === 'plan') return { plan, questions: [], overlaps: [], coverage: null };
  if (options.stage === 'finish') {
    return { ...response, questions: [{ ...response.questions[0], draft: TRIMMED,
      sentences: [{ ...response.questions[0].sentences[0], text: TRIMMED }] }, response.questions[1]] };
  }
  return { plan, overlaps: [], coverage: null, questions: response.questions
    .filter((q) => q.question_id === options.only).map((q) => ({ ...q, trimmed_overlap: undefined })) };
}

describe('문항 전체 답변', () => {
  it('개별 저장 성공 후에는 전체 저장을 누르지 않아도 미저장이 아니다', async () => {
    const onStatus = vi.fn();
    act(() => root.render(<QuestionWorkflowAnswers resumeId="r1" tailoredId="apply_1" editId="r1/tailored/apply_1" onStatus={onStatus} />));
    type(answerBox(1), '개별 저장한 답');
    const save = [...host.querySelectorAll('.qa-card button')].find((b) => b.textContent?.endsWith('저장')) as HTMLButtonElement;
    await act(async () => save.click());
    expect(onStatus.mock.lastCall?.[0].dirty).toBe(false);
  });
  it('저장 버튼 클릭 여부가 아니라 성공한 저장 내용과 비교해 미저장을 알린다', async () => {
    const onStatus = vi.fn();
    act(() => root.render(<QuestionWorkflowAnswers resumeId="r1" tailoredId="apply_1" editId="r1/tailored/apply_1" onStatus={onStatus} />));
    expect(onStatus.mock.lastCall?.[0].dirty).toBe(false);
    type(answerBox(1), '새 답변');
    expect(onStatus.mock.lastCall?.[0].dirty).toBe(true);
    repo.updateResume.mockRejectedValueOnce(new Error('network'));
    await act(async () => button('전체 저장').click());
    expect(onStatus.mock.lastCall?.[0].dirty).toBe(true);
    await act(async () => button('전체 저장').click());
    expect(onStatus.mock.lastCall?.[0].dirty).toBe(false);
    type(answerBox(1), '바뀐 답');
    expect(onStatus.mock.lastCall?.[0].dirty).toBe(true);
    type(answerBox(1), '새 답변');
    expect(onStatus.mock.lastCall?.[0].dirty).toBe(false);
  });
  it('전체 저장은 현재 입력한 답변들을 한 요청에 저장한다', async () => {
    act(() => root.render(<QuestionWorkflowAnswers resumeId="r1" tailoredId="apply_1" editId="r1/tailored/apply_1" />));
    type(answerBox(1), '첫 번째 수정한 답');
    type(answerBox(2), '두 번째 수정한 답');
    await act(async () => button('전체 저장').click());
    expect(repo.updateResume).toHaveBeenCalledTimes(1);
    expect(repo.updateResume).toHaveBeenCalledWith('r1/tailored/apply_1', { content: { companyQuestions: [
      expect.objectContaining({ id: 'cq1', answer: '첫 번째 수정한 답', memo: '데이터로 문제 해결' }),
      expect.objectContaining({ id: 'cq2', answer: '두 번째 수정한 답', notes: expect.any(Array) }),
    ] } });
    expect(host.textContent).toContain('2개 답변을 저장했어요.');
    type(answerBox(1), '다시 수정');
    expect(host.textContent).not.toContain('2개 답변을 저장했어요.');
  });

  it('글자 수 초과는 전체 저장을 막고 빈 답변은 제외한다', async () => {
    act(() => root.render(<QuestionWorkflowAnswers resumeId="r1" tailoredId="apply_1" editId="r1/tailored/apply_1" />));
    type(answerBox(1), '가'.repeat(501));
    await act(async () => button('전체 저장').click());
    expect(repo.updateResume).not.toHaveBeenCalled();
    expect(host.textContent).toContain('1번 문항의 글자 수를 줄인 뒤');
    type(answerBox(1), '');
    await act(async () => button('전체 저장').click());
    expect(host.textContent).toContain('1개 답변을 저장했어요. 빈 답변 1개는 제외했어요.');
  });

  it('저장 중 중복 클릭을 막고 실패해도 입력을 유지하여 재시도한다', async () => {
    let rejectSave: (error: Error) => void = () => undefined;
    repo.updateResume.mockImplementationOnce(() => new Promise<void>((_, reject) => { rejectSave = reject; }));
    act(() => root.render(<QuestionWorkflowAnswers resumeId="r1" tailoredId="apply_1" editId="r1/tailored/apply_1" />));
    type(answerBox(1), '유지할 답변');
    act(() => button('전체 저장').click());
    expect(button('전체 저장 중').disabled).toBe(true);
    expect(answerBox(1).disabled).toBe(true);
    act(() => button('전체 저장 중').click());
    expect(repo.updateResume).toHaveBeenCalledTimes(1);
    await act(async () => rejectSave(new Error('network')));
    expect(host.textContent).toContain('전체 저장하지 못했어요.');
    expect(answerBox(1).value).toBe('유지할 답변');
    await act(async () => button('전체 저장').click());
    expect(host.textContent).toContain('2개 답변을 저장했어요.');
  });

  it('계획 → 문항마다 → 한 벌 점검으로 나눠 부르고, 빈 칸에만 초안을 넣고, 겹쳐 줄인 이야기를 알린다', async () => {
    api.questionWorkflow.mockImplementation((...args: unknown[]) => Promise.resolve(staged(args[3] as Options)));
    act(() => root.render(<QuestionWorkflowAnswers resumeId="r1" tailoredId="apply_1" editId="r1/tailored/apply_1" />));
    await act(async () => button('문항 전체 한 번에 쓰기').click());
    await flush();

    expect(api.questionWorkflow).toHaveBeenCalledWith('r1', 'apply_1', [
      { id: 'cq1', memo: '데이터로 문제 해결', notes: [], written: '' },
      { id: 'cq2', memo: '', notes: [], written: '직접 쓴 답' },
    ], { stage: 'plan' });
    const options = api.questionWorkflow.mock.calls.map((c) => c[3] as Options & { answers?: Record<string, { draft: string }> });
    expect(options.slice(0, 3)).toEqual([{ stage: 'plan' }, { only: 'cq1', plan }, { only: 'cq2', plan }]);
    expect(options[3].stage).toBe('finish');
    expect(options[3].answers?.cq1.draft).toBe('데이터로 문제를 해결하고 싶어 지원했습니다.');  // 문항마다 받은 답을 돌려보낸다
    expect(answerBox(1).value).toBe(TRIMMED);  // 손대지 않은 답 칸은 한 벌 점검이 줄여 쓴 답으로
    expect(answerBox(2).value).toBe('직접 쓴 답'); // 쓴 글은 덮지 않는다
    expect(button('이 초안으로 바꾸기')).toBeTruthy();
    expect(host.textContent).toContain('「추천 품질 개선」 이야기는 2번에 자세히 썼어요. 1번에서는 줄였어요.');
    expect(host.textContent).toContain('내 메모');
    expect([...host.querySelectorAll('.qa-req')].map((e) => e.textContent)).toEqual(['필수 · 검색·추천 품질 평가']);
    expect(host.textContent).toContain('공고 필수 요건 2개 중 1개를 답에 담았어요.');
    expect(host.textContent).toContain('아직 어느 답에도 안 들어간 필수 요건 「Python」');
  });

  it('질문에 답하면 그 문항만 저장한 계획으로 다시 쓰고, 다른 카드는 두고, 예전 기록은 그대로 둔 채 이어 저장한다', async () => {
    const redo = { plan, overlaps: [], coverage: null,
      questions: [{ ...response.questions[0], draft: '고른 이유까지 담은 새 초안입니다.', questions: [],
        sentences: [{ text: '고른 이유까지 담은 새 초안입니다.', sources: [], requirements: [] }] }] };
    let full = true;
    api.questionWorkflow.mockImplementation((...args: unknown[]) => Promise.resolve(full ? staged(args[3] as Options) : redo));
    act(() => root.render(<QuestionWorkflowAnswers resumeId="r1" tailoredId="apply_1" editId="r1/tailored/apply_1" />));
    await act(async () => button('문항 전체 한 번에 쓰기').click());
    await flush();
    const gap = [...host.querySelectorAll('.qa-gap textarea')][0] as HTMLTextAreaElement;
    type(gap, 'AI 서비스 품질을 중시하는 팀이라서');
    full = false;
    await act(async () => button('답하고 이 문항 다시 쓰기').click());
    await flush();

    const [, , questions, options] = api.questionWorkflow.mock.calls.at(-1)!;
    expect(options).toEqual({ only: 'cq1', plan });
    expect(host.textContent).toContain('고른 이유까지 담은 새 초안입니다.');
    expect(host.textContent).toContain('추천 품질을 개선했습니다.'); // 2번 카드 결과는 그대로
    expect(host.textContent).toContain('2번에 자세히 썼어요'); // 한 벌 알림도 그대로
    expect(questions[0].notes).toEqual([{ question: '이 회사를 고른 이유는 무엇인가요?', answer: 'AI 서비스 품질을 중시하는 팀이라서' }]);
    const saved = (repo.updateResume.mock.calls.at(-1) as unknown as [string, { content: { companyQuestions: { notes: unknown[] }[] } }])[1];
    expect(saved.content.companyQuestions[1].notes).toEqual([{ question: '경험 선택', answer: '', source_type: 'selection' }]);
    expect(saved.content.companyQuestions[0].notes).toEqual([
      { question: '이 회사를 고른 이유는 무엇인가요?', answer: 'AI 서비스 품질을 중시하는 팀이라서', source_type: 'answer' },
    ]);
  });

  it('줄이면 너무 짧아져 그대로 둔 문항을 따로 알린다', async () => {
    api.questionWorkflow.mockResolvedValue({
      ...response,
      overlaps: [{ story: '추천 품질 개선', keep: 'cq2', others: [], unchanged: ['cq1'], reason: '역량 문항' }],
      questions: [{ ...response.questions[0], trimmed_overlap: [], overlap_unchanged: ['추천 품질 개선'] }, response.questions[1]],
    });
    act(() => root.render(<QuestionWorkflowAnswers resumeId="r1" tailoredId="apply_1" editId="r1/tailored/apply_1" />));
    await act(async () => button('문항 전체 한 번에 쓰기').click());
    await flush();
    expect(host.textContent).toContain('1번은 줄이면 너무 짧아져 그대로 뒀어요.');
    expect(host.textContent).not.toContain('번에서는 줄였어요');
    expect(host.textContent).toContain('다른 문항과 겹친 이야기 「추천 품질 개선」 — 줄이면 답이 너무 짧아져 그대로 뒀어요.');
  });

  it('카드의 「AI 초안 쓰기」는 그 문항만 쓴다 — 계획이 없으면 서버가 세우고, 받은 계획은 다음 문항에 다시 쓴다', async () => {
    const one = (id: string, draft: string) => ({ plan, overlaps: [], coverage: null,
      questions: [{ question_id: id, draft, char_count: draft.length, limit: 500, removed: [], questions: [],
        sentences: [{ text: draft, sources: [], requirements: [] }] }] });
    api.questionWorkflow.mockResolvedValueOnce(one('cq1', '1번 초안입니다.')).mockResolvedValueOnce(one('cq2', '2번 초안입니다.'));
    act(() => root.render(<QuestionWorkflowAnswers resumeId="r1" tailoredId="apply_1" editId="r1/tailored/apply_1" />));
    await act(async () => button('메모 반영해 AI 초안 쓰기').click());  // 1번 카드(메모 있음)
    await flush();
    expect(api.questionWorkflow.mock.calls[0][3]).toEqual({ only: 'cq1', plan: null });
    expect(answerBox(1).value).toBe('1번 초안입니다.');
    await act(async () => [...host.querySelectorAll('button')].filter((b) => b.textContent?.includes('AI 초안 쓰기'))[0].click());
    await flush();
    expect(api.questionWorkflow.mock.calls[1][3]).toEqual({ only: 'cq2', plan });  // 받은 계획을 다시 쓴다
    expect(api.questionWorkflow.mock.calls[1][2][0].written).toBe('1번 초안입니다.');  // 1번에 쓴 답을 같이 보낸다
  });
});

describe('질문 카드 답 안내', () => {
  it('키워드만 적으면 더 적어 달라고 하고, 상황 · 한 일이 들어가면 안내를 거둔다', async () => {
    api.questionWorkflow.mockResolvedValue(response);
    act(() => root.render(<QuestionWorkflowAnswers resumeId="r1" tailoredId="apply_1" editId="r1/tailored/apply_1" />));
    await act(async () => button('문항 전체 한 번에 쓰기').click());
    await flush();

    expect(host.textContent).toContain('상황 · 내가 한 일 · 결과를 적으면');
    const gap = host.querySelector('.qa-gap textarea') as HTMLTextAreaElement;
    type(gap, '데이터 좋아함');
    expect(host.querySelector('.qa-gap__nudge')?.textContent).toContain('조금만 더 적어 주세요');
    type(gap, '공고 추천을 만들며 사용자가 근거를 보고 고르게 했고, 그때 증권 앱도 이렇게 바뀌어야 한다고 느낌');
    expect(host.querySelector('.qa-gap__nudge')).toBeNull();
  });
});

describe('쓰는 동안 단계', () => {
  it('문항 하나를 쓰는 동안 단계와 지난 시간을 보여 주고, 끝나면 거둔다', async () => {
    vi.useFakeTimers();
    let finish: (v: unknown) => void = () => undefined;
    api.questionWorkflow.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    act(() => root.render(<QuestionWorkflowAnswers resumeId="r1" tailoredId="apply_1" editId="r1/tailored/apply_1" />));
    act(() => button('메모 반영해 AI 초안 쓰기').click());

    const steps = () => host.querySelector('.qw-steps');
    expect(steps()?.textContent).toContain('문항 뼈대 세우는 중');  // 계획이 아직 없으면 뼈대부터
    expect(steps()?.querySelector('.is-now')?.textContent).toContain('문항 뼈대 세우는 중');
    act(() => { vi.advanceTimersByTime(40_000); });
    expect(steps()?.querySelector('.is-now')?.textContent).toContain('쓰는 중');
    expect(steps()?.textContent).toContain('40초 지남');
    act(() => { vi.advanceTimersByTime(200_000); });
    expect(steps()?.textContent).toContain('조금 더 걸리고 있어요');

    vi.useRealTimers();
    await act(async () => finish(response));
    await flush();
    expect(steps()).toBeNull();
  });
});
