import { describe, expect, it } from 'vitest';

import type { PracticeKind, PracticeProblem, PracticeSet } from '../../../domain/types';
import { cellsForSet, SCRATCH_START } from '../notebookModel';

function problem(kind: PracticeKind, starterCode: string): PracticeProblem {
  return {
    kind, topic: kind, prompt: '', sourceFiles: [], explanation: '', choices: [], answerIndex: null,
    starterCode, expectedStdout: '', blankAnswers: [], referenceSolution: '', hiddenTests: '', packages: [],
  };
}

const SET: PracticeSet = {
  id: 'ps-t', cohortId: 'c', sourceTitle: 'multimodal', lessonDate: '2026-09-11', dayLabel: '1일차', title: 't',
  files: ['a.ipynb'], model: 'm',
  problems: [problem('code_write', 'def f(x):\n    pass'), problem('code_scratch', 'def g(x):\n    pass')],
};

describe('세트로 채운 노트북', () => {
  it('처음부터 문제는 뼈대 없이 열고, 다른 문제는 시작 코드로 연다', () => {
    const problems = cellsForSet(SET).filter((c) => c.type === 'problem');
    expect(problems.map((c) => c.code)).toEqual(['def f(x):\n    pass', SCRATCH_START]);
    expect(SCRATCH_START).not.toContain('def');
  });
});
