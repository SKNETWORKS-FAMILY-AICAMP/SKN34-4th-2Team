import { describe, expect, it } from 'vitest';

import type { PracticeAttempt, PracticeProblem, PracticeSet } from '../../../domain/types';
import {
  continuationOf,
  dueRetries,
  estimateMinutes,
  lessonFileLabel,
  pickTodayReview,
  RETRY_SET_ID,
  retryDates,
  retryItems,
  retrySet,
  retryTopics,
  shortDate,
} from '../review';

function problem(kind: PracticeProblem['kind']): PracticeProblem {
  return {
    kind, topic: '', prompt: '', sourceFiles: [], explanation: '', choices: [], answerIndex: null,
    starterCode: '', expectedStdout: '', blankAnswers: [], referenceSolution: '', hiddenTests: '', packages: [],
  };
}

function set(id: string, lessonDate: string, files: string[]): PracticeSet {
  return {
    id, cohortId: 'c34', sourceTitle: 'multimodal', lessonDate, dayLabel: '', title: id, files, model: '',
    problems: [problem('concept'), problem('concept'), problem('code_output'), problem('code_blank'), problem('code_fix'), problem('code_write')],
  };
}

const S0911 = set('s11', '2026-09-11', ['01_cnn/01_cnn.ipynb']);
const S0914 = set('s14', '2026-09-14', ['03_vlm/02_BLIP.ipynb', '05_rag/02_video_rag_frame_extraction.ipynb']);
const S0915 = set('s15', '2026-09-15', ['05_rag/02_video_rag_frame_extraction.ipynb', '05_rag/03_caption.ipynb']);
const SETS = [S0911, S0914, S0915];

function attempt(setId: string, index: number, passed: boolean): PracticeAttempt {
  return { id: `${setId}-${index}`, uid: 'u', setId, index, passed, tries: 1, answeredAt: new Date() };
}

describe('오늘 복습', () => {
  it('오늘 수업 세트가 있으면 그것을 고른다', () => {
    const r = pickTodayReview(SETS, [], '2026-09-15');
    expect(r?.set.id).toBe('s15');
    expect(r?.daysAgo).toBe(0);
    expect(r?.state).toBe('new');
  });

  it('오늘 수업이 없으면 가장 최근 수업, 미래 세트는 보지 않는다', () => {
    const r = pickTodayReview(SETS, [], '2026-09-14');
    expect(r?.set.id).toBe('s14');
    expect(pickTodayReview(SETS, [], '2026-09-22')?.set.id).toBe('s15');
    expect(pickTodayReview(SETS, [], '2026-09-22')?.daysAgo).toBe(7);
  });

  it('2주가 넘은 수업은 올리지 않는다', () => {
    expect(pickTodayReview(SETS, [], '2026-10-10')).toBeNull();
  });

  it('풀이 기록으로 상태를 정한다', () => {
    const some = [attempt('s15', 0, true), attempt('s15', 1, false)];
    expect(pickTodayReview(SETS, some, '2026-09-15')).toMatchObject({ state: 'partial', passed: 1, total: 6 });
    const all = [0, 1, 2, 3, 4, 5].map((i) => attempt('s15', i, true));
    expect(pickTodayReview(SETS, all, '2026-09-15')?.state).toBe('done');
    // 다른 세트 기록은 세지 않는다
    expect(pickTodayReview(SETS, [attempt('s14', 0, true)], '2026-09-15')?.state).toBe('new');
  });

  it('같은 수업 파일이 앞 수업과 겹치면 이어진 수업이다', () => {
    expect(continuationOf(S0915, SETS)).toEqual({ date: '2026-09-14', files: ['05_rag/02_video_rag_frame_extraction.ipynb'] });
    expect(continuationOf(S0914, SETS)).toBeNull();
    expect(continuationOf(S0911, SETS)).toBeNull();
  });

  it('표시용 글자', () => {
    expect(estimateMinutes(S0915)).toBe(10);
    expect(lessonFileLabel('05_rag/02_video_rag_frame_extraction.ipynb')).toBe('video rag frame extraction');
    expect(shortDate('2026-09-05')).toBe('9/5');
  });
});

describe('다시 풀 문제', () => {
  const at = (setId: string, index: number, passed: boolean, date: string, tries = 1): PracticeAttempt => ({
    id: `${setId}-${index}`, uid: 'u', setId, index, passed, tries, answeredAt: new Date(`${date}T10:00:00`),
  });
  const attempts = [
    at('s14', 2, false, '2026-09-15', 2),
    at('s14', 0, true, '2026-09-15'),
    at('s15', 4, false, '2026-09-22'),
    at('s15', 1, false, '2026-09-16'),
    at('gone', 0, false, '2026-09-10'),
  ];

  it('통과 못 한 것만, 최근 수업부터 문제 순서대로. 없는 세트는 뺀다', () => {
    const items = retryItems(SETS, attempts);
    expect(items.map((i) => `${i.set.id}#${i.index}`)).toEqual(['s15#1', 's15#4', 's14#2']);
    expect(items[2]).toMatchObject({ tries: 2, lastTried: '2026-09-15' });
  });

  it('오늘 틀린 것은 오늘 다시 보여 주지 않는다', () => {
    const due = dueRetries(retryItems(SETS, attempts), '2026-09-22');
    expect(due.map((i) => `${i.set.id}#${i.index}`)).toEqual(['s15#1', 's14#2']);
  });

  it('세트 하나로 묶고 원래 자리를 기억한다', () => {
    const r = retrySet(retryItems(SETS, attempts), '2026-09-22');
    expect(r?.set.id).toBe(RETRY_SET_ID);
    expect(r?.set.problems).toHaveLength(3);
    expect(r?.origins).toEqual([{ setId: 's15', index: 1 }, { setId: 's15', index: 4 }, { setId: 's14', index: 2 }]);
    expect(retrySet([], '2026-09-22')).toBeNull();
  });

  it('주제와 날짜를 짧게 보여 준다', () => {
    const named = (id: string, date: string, topics: string[]): PracticeSet => ({
      ...set(id, date, []),
      problems: topics.map((topic) => ({ ...problem('code_fix'), topic })),
    });
    const sets = [named('a', '2026-09-14', ['확산 수식', 'ITM 판정', '확산 수식']), named('b', '2026-09-15', ['정규식'])];
    const items = retryItems(sets, [at('a', 0, false, '2026-09-20'), at('a', 1, false, '2026-09-20'), at('a', 2, false, '2026-09-20'), at('b', 0, false, '2026-09-20')]);
    expect(retryTopics(items)).toBe('정규식, 확산 수식 외 1개');
    expect(retryTopics(items, 3)).toBe('정규식, 확산 수식, ITM 판정');
    expect(retryDates(items)).toBe('9/15, 9/14');
  });
});
