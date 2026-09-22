import { describe, expect, it } from 'vitest';

import type { PracticeReport, PracticeReview, PracticeSet } from '../../../domain/types';
import { flaggedProblems, HIDE_AT, isHidden } from '../reports';

const set: PracticeSet = {
  id: 's', cohortId: 'c', sourceTitle: '', lessonDate: '2026-09-15', dayLabel: '', title: 't', files: [], model: '',
  problems: [0, 1, 2].map((i) => ({ kind: 'concept', topic: `p${i}`, prompt: '', sourceFiles: [], explanation: '', choices: [], answerIndex: 0, starterCode: '', expectedStdout: '', blankAnswers: [], referenceSolution: '', hiddenTests: '', packages: [] })),
};
const report = (uid: string, index: number): PracticeReport => ({ id: `${uid}-${index}`, uid, setId: 's', index, reason: 'tests', note: '', createdAt: new Date() });

describe('복습 문제 신고', () => {
  it('서로 다른 학생 2명이 신고하면 숨긴다 — 같은 사람이 두 번은 아니다', () => {
    expect(HIDE_AT).toBe(2);
    expect(isHidden([report('a', 0)], [], 's', 0)).toBe(false);
    expect(isHidden([report('a', 0), report('a', 0)], [], 's', 0)).toBe(false);
    expect(isHidden([report('a', 0), report('b', 0)], [], 's', 0)).toBe(true);
    expect(isHidden([report('a', 0), report('b', 0)], [], 's', 1)).toBe(false);
  });

  it('강사 결정이 신고 수보다 우선한다', () => {
    const two = [report('a', 0), report('b', 0)];
    const kept: PracticeReview = { setId: 's', index: 0, decision: 'kept', decidedBy: 'i', decidedAt: new Date() };
    const hidden: PracticeReview = { setId: 's', index: 1, decision: 'hidden', decidedBy: 'i', decidedAt: new Date() };
    expect(isHidden(two, [kept], 's', 0)).toBe(false);
    expect(isHidden([report('a', 1)], [hidden], 's', 1)).toBe(true);
  });

  it('강사 목록은 숨긴 것 · 신고 많은 것부터', () => {
    const list = flaggedProblems([set], [report('a', 2), report('a', 0), report('b', 0), report('c', 1)], []);
    expect(list.map((f) => [f.index, f.reporters, f.hidden])).toEqual([[0, 2, true], [2, 1, false], [1, 1, false]]);
  });

  it('없는 세트·문제의 신고는 뺀다', () => {
    expect(flaggedProblems([set], [{ ...report('a', 0), setId: 'gone' }, report('a', 9)], [])).toEqual([]);
  });
});
