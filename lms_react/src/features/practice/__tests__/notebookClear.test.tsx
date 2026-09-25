import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { beforeEach, describe, expect, it } from 'vitest';

import type { PracticeSet } from '../../../domain/types';
import type { PythonRunner } from '../pythonRunner';
import { useNotebook, type Notebook } from '../useNotebook';

/** 실행기는 부르지 않는다 — 지우기가 변수를 비우는지(reset)만 센다 */
function fakeRunner() {
  const calls = { reset: 0, stop: 0 };
  const runner = { reset: () => void calls.reset++, stop: () => void calls.stop++ } as unknown as PythonRunner;
  return { runner, calls };
}

function mount(set: PracticeSet | undefined) {
  const { runner, calls } = fakeRunner();
  let nb: Notebook | null = null;
  function Harness() {
    nb = useNotebook(runner, set);
    return null;
  }
  act(() => createRoot(document.createElement('div')).render(<Harness />));
  return { nb: () => nb!, calls };
}

beforeEach(() => localStorage.clear());

describe('모든 셀 지우기', () => {
  it('일반 연습장은 빈 코드 셀 하나만 남기고 변수도 비운다', () => {
    const { nb, calls } = mount(undefined);
    act(() => nb().addCellAfter(nb().cells[0].id));
    act(() => nb().addCellAfter(nb().cells[0].id, 'markdown'));
    expect(nb().cells.length).toBeGreaterThanOrEqual(3);

    act(() => nb().clearAll());
    expect(nb().cells).toHaveLength(1);
    expect(nb().cells[0].type).toBe('code');
    expect(nb().cells[0].code).toBe('');
    expect(nb().activeId).toBe(nb().cells[0].id);
    expect(calls.reset).toBe(1);
  });

  it('복습 세트는 문제 셀만 남긴다', () => {
    const set: PracticeSet = {
      id: 'ps-clear',
      cohortId: 'cohort_34',
      sourceTitle: 'dl',
      lessonDate: '2026-09-24',
      dayLabel: '1일차',
      title: '리스트',
      files: [],
      model: 'm',
      problems: [
        {
          kind: 'code_output',
          topic: '리스트',
          prompt: '출력은?',
          sourceFiles: [],
          explanation: '',
          choices: [],
          answerIndex: null,
          starterCode: 'print([1])',
          expectedStdout: '[1]',
          blankAnswers: [],
          referenceSolution: 'print([1])',
          hiddenTests: '',
          packages: [],
        },
      ],
    };
    const { nb } = mount(set);
    const problems = nb().cells.filter((c) => c.type === 'problem').length;
    expect(problems).toBeGreaterThan(0);
    act(() => nb().addCellAfter(nb().cells[nb().cells.length - 1].id));

    act(() => nb().clearAll());
    expect(nb().cells.every((c) => c.type === 'problem')).toBe(true);
    expect(nb().cells).toHaveLength(problems);
  });
});
