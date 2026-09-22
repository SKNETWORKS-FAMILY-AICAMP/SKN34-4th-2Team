import { describe, expect, it } from 'vitest';

import type { PracticeSet, StudyNote } from '../../../domain/types';
import { lessonDays, looseNotes, noteDate, noteLabel } from '../lessonDays';

const set = (lessonDate: string): PracticeSet => ({
  id: `ps-${lessonDate}`, cohortId: 'c', sourceTitle: 'r', lessonDate, dayLabel: '', title: lessonDate, files: [], model: '', problems: [],
});
const note = (id: string, scopeKey: string, at = 0): StudyNote => ({
  id, sourceId: 'src1', status: 'done', scopeKey, reportMarkdown: '', reviewMarkdown: '', files: [], createdAt: new Date(at),
});

describe('공부방 수업 날짜', () => {
  it('날짜 노트만 날짜로 읽는다', () => {
    expect(noteDate(note('a', 'date:2026-09-15'))).toBe('2026-09-15');
    expect(noteDate(note('b', 'python/day01'))).toBeNull();
    expect(noteDate(note('c', 'files:3개'))).toBeNull();
  });

  it('같은 날 노트와 복습 문제를 한 칸에, 최근 수업부터', () => {
    const days = lessonDays(
      [set('2026-09-11'), set('2026-09-15')],
      [note('n15', 'date:2026-09-15'), note('n19', 'date:2026-09-19'), note('loose', 'python/day01')],
    );
    expect(days.map((d) => [d.date, d.set?.id ?? null, d.note?.id ?? null])).toEqual([
      ['2026-09-19', null, 'n19'],
      ['2026-09-15', 'ps-2026-09-15', 'n15'],
      ['2026-09-11', 'ps-2026-09-11', null],
    ]);
  });

  it('같은 날 노트가 여럿이면 가장 최근 것', () => {
    const days = lessonDays([], [note('old', 'date:2026-09-15', 1), note('new', 'date:2026-09-15', 5), note('mid', 'date:2026-09-15', 3)]);
    expect(days[0].note?.id).toBe('new');
  });

  it('폴더·파일 범위 노트는 따로 모은다', () => {
    expect(looseNotes([note('a', 'date:2026-09-15'), note('b', 'python/day01')]).map((n) => n.id)).toEqual(['b']);
  });

  it('목록 이름 — 날짜 노트는 날짜로', () => {
    expect(noteLabel(note('a', 'date:2026-09-15'))).toBe('09/15 수업');
    expect(noteLabel(note('b', 'python/day01'))).toBe('python/day01');
  });
});
