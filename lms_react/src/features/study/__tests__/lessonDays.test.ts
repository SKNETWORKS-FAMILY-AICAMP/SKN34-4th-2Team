import { describe, expect, it } from 'vitest';

import type { PracticeSet, StudyNote } from '../../../domain/types';
import { lessonDays, looseNotes, noteDate, noteLabel } from '../lessonDays';

const set = (lessonDate: string): PracticeSet => ({
  id: `ps-${lessonDate}`, cohortId: 'c', sourceTitle: 'r', lessonDate, dayLabel: '', title: lessonDate, files: [], model: '', problems: [],
});
/** DB 모양 그대로 — 날짜면 scope_type 'date' · scope_key '2026-09-15', 폴더면 'prefix' */
const note = (id: string, value: string, at = 0): StudyNote => {
  const isDate = /^\d{4}-\d{2}-\d{2}$/.test(value);
  return {
    id, sourceId: 'src1', status: 'done',
    scopeType: isDate ? 'date' : 'prefix', scopeValue: value, scopeKey: isDate ? value : `prefix_${value.replace(/[^A-Za-z0-9._-]+/g, '_')}`,
    reportMarkdown: '', reviewMarkdown: '', files: [], createdAt: new Date(at),
  };
};

describe('공부방 수업 날짜', () => {
  it('날짜 노트만 날짜로 읽는다', () => {
    expect(noteDate(note('a', '2026-09-15'))).toBe('2026-09-15');
    expect(noteDate(note('b', 'python/day01'))).toBeNull();
    expect(noteDate({ ...note('c', 'x'), scopeType: 'files', scopeValue: ['a.py'], scopeKey: 'files_1234' })).toBeNull();
    // scope_type 이 없는 옛 데이터도 키가 날짜면 날짜로 본다
    expect(noteDate({ ...note('d', '2026-09-11'), scopeType: undefined, scopeValue: undefined })).toBe('2026-09-11');
  });

  it('같은 날 노트와 복습 문제를 한 칸에, 최근 수업부터', () => {
    const days = lessonDays(
      [set('2026-09-11'), set('2026-09-15')],
      [note('n15', '2026-09-15'), note('n19', '2026-09-19'), note('loose', 'python/day01')],
    );
    expect(days.map((d) => [d.date, d.set?.id ?? null, d.note?.id ?? null])).toEqual([
      ['2026-09-19', null, 'n19'],
      ['2026-09-15', 'ps-2026-09-15', 'n15'],
      ['2026-09-11', 'ps-2026-09-11', null],
    ]);
  });

  it('같은 날 노트가 여럿이면 가장 최근 것', () => {
    const days = lessonDays([], [note('old', '2026-09-15', 1), note('new', '2026-09-15', 5), note('mid', '2026-09-15', 3)]);
    expect(days[0].note?.id).toBe('new');
  });

  it('폴더·파일 범위 노트는 따로 모은다', () => {
    expect(looseNotes([note('a', '2026-09-15'), note('b', 'python/day01')]).map((n) => n.id)).toEqual(['b']);
  });

  it('목록 이름 — 날짜 노트는 날짜로', () => {
    expect(noteLabel(note('a', '2026-09-15'))).toBe('09/15 수업');
    expect(noteLabel(note('b', 'python/day01'))).toBe('폴더 python/day01');
    expect(noteLabel({ ...note('c', 'x'), scopeType: 'files', scopeValue: ['lab/a.py', 'lab/b.py'] })).toBe('파일 a.py, b.py');
  });
});
