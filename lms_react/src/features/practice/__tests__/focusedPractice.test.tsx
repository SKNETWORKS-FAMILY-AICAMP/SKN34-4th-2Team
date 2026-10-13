import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { PracticeAttempt, PracticeProblem, PracticeReview, PracticeSet } from '../../../domain/types';

const spies = vi.hoisted(() => ({ record: vi.fn(), run: vi.fn(), reset: vi.fn() }));
let attempts: PracticeAttempt[] = [];
let reviews: PracticeReview[] = [];

const base: PracticeProblem = {
  kind: 'concept', topic: '개념 문제', prompt: '정답을 고르세요', sourceFiles: [], explanation: '정답 설명',
  choices: ['맞는 답', '틀린 답'], answerIndex: 0, starterCode: '', expectedStdout: '', blankAnswers: [],
  referenceSolution: '', hiddenTests: '', packages: [],
};
const set: PracticeSet = {
  id: 'focus-set', cohortId: 'cohort_34', sourceTitle: 'cloud', lessonDate: '2026-09-24', dayLabel: 'cloud 2일차',
  title: '개념 · 출력 · 함수', files: [], model: 'test', problems: [
    base,
    { ...base, kind: 'code_output', topic: '출력 문제', choices: [], starterCode: 'print(12)', expectedStdout: '12', answerIndex: null },
    { ...base, kind: 'code_write', topic: '함수 문제', choices: [], starterCode: 'def answer():\n    return 12', answerIndex: null },
  ],
};

vi.mock('../../../data/repository', async (importOriginal) => ({
  ...await importOriginal<object>(),
  usePracticeSet: (id: string | null) => id === set.id ? set : undefined,
  usePracticeSets: () => [set],
  useFullPracticeSets: () => ({ ready: true, failed: false }),
  useMyPracticeAttempts: () => attempts,
  usePracticeReports: () => [],
  usePracticeReviews: () => reviews,
  recordPracticeAttempt: spies.record,
}));
vi.mock('../../auth/session', () => ({ useCurrentUser: () => ({ uid: 'student', cohortId: 'cohort_34' }) }));
vi.mock('../pythonRunner', async (importOriginal) => ({
  ...await importOriginal<object>(),
  usePythonRunner: () => ({ runner: { run: spies.run, reset: spies.reset, stop: vi.fn(), status: 'ready', generation: 1, version: 'test' }, status: 'ready' }),
}));
vi.mock('../CodeEditor', () => ({
  CodeEditor: ({ value, onChange, label, readOnly, onRunAndNext }: {
    value: string; onChange?: (value: string) => void; label: string; readOnly?: boolean; onRunAndNext?: () => void;
  }) => <textarea aria-label={label} value={value} readOnly={readOnly || !onChange}
    onChange={(event) => onChange?.(event.target.value)} onKeyDown={(event) => {
      if (event.key === 'Enter' && event.shiftKey) onRunAndNext?.();
    }} />,
}));
// 튜터 서버 대화는 이 UI 테스트 범위 밖이다. 실제 context 등록/따라가기는 그대로 검증한다.
vi.mock('../TutorPanel', async () => {
  const { useTutor } = await import('../TutorContext');
  return { TutorPanel: () => {
    const target = useTutor()?.target;
    return target ? <aside className="tutor" data-target={target.index}>{target.label}</aside> : null;
  } };
});

const { EmbeddedPlayground } = await import('../PythonPlaygroundScreen');
const { PracticeDockHost, PracticeLink } = await import('../PracticeDock');
let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  localStorage.clear();
  attempts = [];
  reviews = [];
  spies.record.mockReset();
  spies.reset.mockReset();
  spies.run.mockReset().mockImplementation(async (_steps, options) => {
    options?.onStdout?.('12\n');
    return { ok: true, stdout: '12\n', value: null, table: null, images: [], ms: 1, error: null, stopped: false, timedOut: false };
  });
  host = document.createElement('div');
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); });

async function render(setId: string | null = set.id, focusProblem = 0) {
  await act(async () => root.render(<MemoryRouter><EmbeddedPlayground setId={setId} focusProblem={focusProblem} active /></MemoryRouter>));
}
async function click(element: Element) { await act(async () => (element as HTMLElement).click()); }
const button = (text: string, scope: ParentNode = host) => [...scope.querySelectorAll('button')].find((item) => {
  const copy = item.cloneNode(true) as HTMLElement;
  copy.querySelectorAll('[aria-hidden]').forEach((icon) => icon.remove());
  return copy.textContent?.trim() === text;
})!;
const panel = () => host.querySelector<HTMLElement>('.pf-problems > div:not([hidden])')!;
async function type(element: HTMLTextAreaElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(element, value);
    element.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

describe('집중형 복습', () => {
  it('문제 이동 후 선택 답안·출력 답안·실행 결과가 유지되고 튜터는 선택 문제를 따라간다', async () => {
    await render();
    expect(host.querySelector('.tutor')).toBeNull();
    expect(panel().textContent).toContain('개념 문제');
    await click(panel().querySelector('input[type=radio]')!);
    const first = panel();
    await click(button('다음'));
    const second = panel();
    await type(second.querySelector('.pb__answer textarea')!, 'my pending answer');
    await click(button('다음'));
    const third = panel();
    await type(third.querySelector('textarea')!, 'def answer():\n    return 33');
    await click(button('실행', third));
    expect(third.textContent).toContain('12');
    await click(button('AI 튜터'));
    expect(host.querySelector('.tutor')?.getAttribute('data-target')).toBe('2');
    await click(button('이전'));
    expect(panel()).toBe(second);
    expect(second.querySelector<HTMLTextAreaElement>('textarea:not([readonly])')?.value).toBe('my pending answer');
    expect(host.querySelector('.tutor')?.getAttribute('data-target')).toBe('1');
    await click(button('이전'));
    expect(panel()).toBe(first);
    expect(first.querySelector<HTMLInputElement>('input[type=radio]')?.checked).toBe(true);
    await click(button('정답 확인', first));
    expect(spies.record).toHaveBeenLastCalledWith('student', set.id, 0, true);
    await click(button('다음'));
    await click(button('다음'));
    expect(panel()).toBe(third);
    expect(third.querySelector<HTMLTextAreaElement>('textarea')?.value).toContain('return 33');
    expect(third.textContent).toContain('12');
    expect(spies.reset).not.toHaveBeenCalled();
    expect(spies.run).toHaveBeenCalledWith(['def answer():\n    return 33'], expect.objectContaining({ session: 'playground' }));
  });

  it('focus와 목록 이동을 적용하고 숨긴 문제는 번호를 유지한 채 건너뛴다', async () => {
    reviews = [{ setId: set.id, index: 1, decision: 'hidden', decidedBy: 'teacher', decidedAt: new Date() }];
    await render(set.id, 3);
    expect(panel().textContent).toContain('함수 문제');
    expect(host.querySelector('.pf-navigation')?.textContent).toContain('문제 3');
    expect(host.querySelector('.pf-navigation')?.textContent).toContain('2 / 2');
    await click(button('이전'));
    expect(panel().textContent).toContain('개념 문제');
    await click(button('문제 목록'));
    expect(host.querySelectorAll('.pf-list > button')).toHaveLength(2);
    await click(host.querySelectorAll('.pf-list > button')[1]);
    expect(panel().textContent).toContain('함수 문제');
    await render(set.id, 1);
    expect(panel().textContent).toContain('개념 문제');
    await render(set.id, 2); // 숨김 focus는 현재 유효 문제를 유지한다
    expect(panel().textContent).toContain('개념 문제');
  });

  it.each(['retry', 'retry:all', 'retry:2026-09-24'])('%s도 집중형 UI에서 원수업 번호로 기록한다', async (id) => {
    attempts = [{ id: 'a', uid: 'student', setId: set.id, index: 0, passed: false, tries: 1, answeredAt: new Date('2026-09-25') }];
    await render(id);
    expect(panel().textContent).toContain('9/24 문제 1');
    await click(panel().querySelector('input[type=radio]')!);
    await click(button('정답 확인', panel()));
    expect(spies.record).toHaveBeenCalledWith('student', set.id, 0, true);
  });

  it('복습 추가 도구는 셀 편집·전체 실행을 숨기고 자유모드는 기존 노트북 도구를 제공한다', async () => {
    await render();
    expect(host.querySelector('[aria-label="모두 실행"]')).toBeNull();
    expect(host.querySelector('[aria-label="문제 만들기"]')).toBeNull();
    expect(host.querySelector<HTMLDetailsElement>('.pf-details')?.open).toBe(false);
    await click(button('추가 도구'));
    expect(host.querySelector('[aria-label="입력값"]')).not.toBeNull();
    act(() => root.unmount());
    root = createRoot(host);
    await render(null);
    expect(host.querySelector('.pf-study')).toBeNull();
    expect(host.querySelector('[aria-label="모두 실행"]')).not.toBeNull();
    expect(host.querySelector('[aria-label="셀 추가"]')).not.toBeNull();
    expect(host.querySelector('[aria-label="문제 만들기"]')).not.toBeNull();
    expect(host.querySelector('input[type=file]')).not.toBeNull();
  });

  it('자유 연습장 탭을 열었다 돌아와도 복습 답안과 문제 컴포넌트는 남는다', async () => {
    await act(async () => root.render(<MemoryRouter><PracticeDockHost>
      <PracticeLink setId={set.id}>복습 열기</PracticeLink>
      <PracticeLink setId={set.id} focus={2}>출력 문제 열기</PracticeLink>
    </PracticeDockHost></MemoryRouter>));
    await click(host.querySelector('a')!);
    const first = panel();
    await click(first.querySelector('input[type=radio]')!);
    await click(host.querySelector('[title="연습장 열기"]')!);
    expect(host.querySelectorAll('.pd-pane')).toHaveLength(2);
    await click(host.querySelector('.pd-tab__label')!);
    expect(panel()).toBe(first);
    expect(first.querySelector<HTMLInputElement>('input[type=radio]')?.checked).toBe(true);
    expect(spies.reset).not.toHaveBeenCalled();
    const focusedLink = [...host.querySelectorAll('a')].find((link) => link.textContent === '출력 문제 열기')!;
    await click(focusedLink);
    expect(panel().textContent).toContain('출력 문제');
    await click(button('이전'));
    await click(focusedLink); // 같은 번호로 재진입해도 새 탭 없이 그 문제로 이동
    expect(panel().textContent).toContain('출력 문제');
    expect(host.querySelectorAll('.pd-pane')).toHaveLength(2);
  });
});
