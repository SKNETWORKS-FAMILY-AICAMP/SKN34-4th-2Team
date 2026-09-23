import { describe, expect, it } from 'vitest';

import type { PracticeSet, StudyNote, StudySource } from '../../../domain/types';
import { lessonDays, looseNotes, noteDate, noteLabel, repoName, reviewBoard } from '../lessonDays';

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

  it('정리 중 · 실패한 노트는 수업 카드와 따로 노트 목록에 붙이지 않는다', () => {
    const days = lessonDays(
      [set('2026-09-15')],
      [{ ...note('done', '2026-09-15', 1) }, { ...note('busy', '2026-09-15', 2), status: 'generating' }, { ...note('bad', '2026-09-19'), status: 'failed' }],
    );
    expect(days.map((d) => [d.date, d.note?.id ?? null])).toEqual([['2026-09-15', 'done']]);
    expect(looseNotes([{ ...note('f', 'python/day01'), status: 'generating' }, note('g', 'python/day02')]).map((n) => n.id)).toEqual(['g']);
    // 서버가 새로 만든 노트는 ready, 옛 데이터는 done
    expect(lessonDays([], [{ ...note('r', '2026-09-20'), status: 'ready' }])[0].note?.id).toBe('r');
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

describe('공부방 과목별 목록', () => {
  const source = (id: string, repo: string, title: string): StudySource => ({
    id, title, repoUrl: `https://github.com/skn-ai34-260616/${repo}`, branch: 'main', allowedPrefixes: [], isActive: true, sortOrder: 0,
  });
  const setOf = (name: string, lessonDate: string): PracticeSet => ({ ...set(lessonDate), id: `ps-${name}-${lessonDate}`, sourceTitle: name });
  const sources = [source('mm', 'multimodal', 'Multimodal'), source('sw', 'sw_engineering', 'SW 공학'), source('dl', 'DL', 'Deep Learning')];

  it('저장소 이름은 주소 끝을 소문자로 — 세트의 sourceTitle 과 맞춘다', () => {
    expect(repoName('https://github.com/skn-ai34-260616/DL.git/')).toBe('dl');
  });

  it('세트는 저장소 이름으로, 노트는 저장소 id 로 과목에 붙고 최근 수업 과목부터', () => {
    const board = reviewBoard(
      sources,
      [setOf('multimodal', '2026-09-11'), setOf('multimodal', '2026-09-15'), setOf('sw_engineering', '2026-09-21')],
      [{ ...note('n', '2026-09-14'), sourceId: 'mm' }, { ...note('f', 'lab/'), sourceId: 'mm' }],
    );
    expect(board.subjects.map((s) => s.key)).toEqual(['sw', 'mm', 'dl']); // 자료 없는 DL 은 맨 뒤
    const mm = board.subjects[1];
    expect(mm.days.map((d) => [d.date, Boolean(d.set), Boolean(d.note)])).toEqual([
      ['2026-09-15', true, false],
      ['2026-09-14', false, true],
      ['2026-09-11', true, false],
    ]);
    expect(mm.looseNotes.map((n) => n.id)).toEqual(['f']);
    expect(board.latest?.subject.key).toBe('sw');
    expect(board.latest?.day.date).toBe('2026-09-21');
  });

  it('저장소 목록에 없는 세트도 버리지 않고 제 이름의 과목으로', () => {
    const board = reviewBoard(sources, [setOf('workflow', '2026-09-21')], []);
    expect(board.subjects[0]).toMatchObject({ key: 'set:workflow', title: 'workflow' });
    expect(board.subjects[0].source).toBeUndefined(); // 저장소가 없으니 노트 만들기는 못 한다
    expect(board.latest?.day.set?.id).toBe('ps-workflow-2026-09-21');
  });

  it('오늘 복습은 문제가 있는 가장 최근 수업 — 노트만 있는 더 늦은 날은 건너뛴다', () => {
    const board = reviewBoard(sources, [setOf('multimodal', '2026-09-15')], [{ ...note('late', '2026-09-22'), sourceId: 'sw' }]);
    expect(board.latest?.day.date).toBe('2026-09-15');
    expect(board.subjects[0].key).toBe('sw'); // 목록 순서는 노트까지 본 최근 수업
  });

  it('문제가 하나도 없으면 오늘 복습이 없다', () => {
    expect(reviewBoard(sources, [], []).latest).toBeUndefined();
  });
});

