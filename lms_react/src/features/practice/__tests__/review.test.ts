import { describe, expect, it } from 'vitest';

import type { PracticeAttempt, PracticeProblem, PracticeSet } from '../../../domain/types';
import { continuationOf, estimateMinutes, lessonFileLabel, pickTodayReview, shortDate } from '../review';

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
