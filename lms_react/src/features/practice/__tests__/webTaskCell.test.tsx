import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, expect, it, vi } from 'vitest';

import type { WebGrade } from '../../../data/repository';
import type { PracticeProblem } from '../../../domain/types';
import { ProblemCell } from '../ProblemCell';
import type { RunResult } from '../pythonProtocol';

const STARTER = '<style>.menu { display: block; }</style>\n<ul class="menu"><li>홈</li></ul>';

const PROBLEM: PracticeProblem = {
  kind: 'web_task',
  topic: 'flexbox 정렬',
  prompt: '메뉴가 가로 한 줄로 놓이게 고치세요.',
  sourceFiles: ['02_css/11_layout_flexbox.html'],
  explanation: 'display: flex 는 자식을 가로로 늘어놓는다.',
  choices: [],
  answerIndex: null,
  starterCode: STARTER,
  expectedStdout: '',
  blankAnswers: [],
  referenceSolution: STARTER.replace('block', 'flex'),
  hiddenTests: '',
  packages: ['web'],
};

const noRun = async () => ({}) as RunResult;

function mount(grade: (html: string) => Promise<WebGrade>, code = STARTER) {
  const host = document.createElement('div');
  const onAttempt = vi.fn();
  act(() =>
    createRoot(host).render(
      <ProblemCell
        problem={PROBLEM}
        number={3}
        code={code}
        attempt={undefined}
        onCodeChange={() => undefined}
        onAttempt={onAttempt}
        runInSession={noRun}
        grade={noRun}
        gradeWeb={grade}
        onFocus={() => undefined}
        focusSignal={0}
        onRunAndNext={() => undefined}
      />,
    ),
  );
  return { host, onAttempt };
}

const button = (host: HTMLElement, text: string) =>
  [...host.querySelectorAll('button')].find((b) => b.textContent?.includes(text)) as HTMLButtonElement;

describe('웹 실습 문제 셀', () => {
  it('편집기 옆에 스크립트를 막은 미리보기가 있다', () => {
    const { host } = mount(async () => ({ passed: false, checks: [], error: '' }));
    const frame = host.querySelector('iframe')!;
    expect(frame.getAttribute('sandbox')).toBe('');
    expect(frame.getAttribute('srcdoc')).toContain('class="menu"');
    expect(host.textContent).toContain('웹 실습');
  });

  it('채점하면 지금 HTML 을 보내고 검사마다 결과를 보인다', async () => {
    const grade = vi.fn(async () => ({
      passed: false,
      checks: [
        { message: '메뉴가 있어요', ok: true },
        { message: '메뉴가 가로 한 줄로 놓여요', ok: false },
      ],
      error: '',
    }));
    const { host, onAttempt } = mount(grade);
    await act(async () => button(host, '채점').click());
    expect(grade).toHaveBeenCalledWith(STARTER);
    expect(host.textContent).toContain('검사 2개 중 1개 통과');
    expect(host.querySelectorAll('.pb__test--fail')).toHaveLength(1);
    expect(onAttempt).toHaveBeenCalledWith(false);
  });

  it('채점을 못 했으면 시도로 세지 않는다', async () => {
    const { host, onAttempt } = mount(async () => ({ passed: false, checks: [], error: '데모에서는 웹 실습 채점을 할 수 없어요.' }));
    await act(async () => button(host, '채점').click());
    expect(host.textContent).toContain('데모에서는 웹 실습 채점을 할 수 없어요.');
    expect(onAttempt).not.toHaveBeenCalled();
  });

  it('통과하면 해설을 보인다', async () => {
    const { host, onAttempt } = mount(async () => ({ passed: true, checks: [{ message: '메뉴가 가로 한 줄로 놓여요', ok: true }], error: '' }));
    await act(async () => button(host, '채점').click());
    expect(host.textContent).toContain('정답이에요 · 검사 1개 모두 통과');
    expect(host.textContent).toContain('display: flex 는 자식을 가로로 늘어놓는다.');
    expect(onAttempt).toHaveBeenCalledWith(true);
  });
});
