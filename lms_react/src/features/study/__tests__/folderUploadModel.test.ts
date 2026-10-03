import { describe, expect, it } from 'vitest';

import {
  batches,
  blockedReason,
  dayNotice,
  initialDates,
  manifest,
  pickedPathOf,
  reviewRows,
  setRowDate,
  uploadItems,
  withEstimates,
  withoutEstimates,
  type PlanCalendar,
  type PlanFile,
  type PlanSubject,
} from '../folderUploadModel';

const CAL: PlanCalendar = {
  today: '2026-10-01',
  start: '2026-06-15',
  end: '2026-12-07',
  holidays: { '2026-09-24': '추석', '2026-10-03': '개천절' },
  classDays: ['2026-06-16', '2026-06-17', '2026-06-18', '2026-09-23', '2026-09-28', '2026-09-29', '2026-09-30', '2026-10-01'],
  extraDays: [],
};

const file = (path: string, extra: Partial<PlanFile> = {}): PlanFile => ({
  path, blob: '0'.repeat(40), size: 100, basis: 'pick', date: null, status: 'new', ...extra,
});

const subject = (files: PlanFile[], extra: Partial<PlanSubject> = {}): PlanSubject => ({
  name: 'python_basic', source: null, topic: '기초|Python', topicBy: 'name', start: '2026-06-16', classDays: [],
  files, counts: { files: files.length, same: 0, dated: 0, past: 0, estimated: 0 }, warnings: [], ...extra,
});

describe('확인 화면 — 줄 묶기', () => {
  // 실제 python_basic 처럼 날짜 단서가 없는 지난 자료 + 이름에 날짜가 있는 파일 + 지난번과 같은 파일
  const s = subject([
    file('01_variable/exercise.ipynb', { estimate: '2026-06-16' }),
    file('01_variable/question.ipynb', { estimate: '2026-06-16' }),
    file('07_package/team/a.py', { estimate: '2026-06-17' }),
    file('07_package/work/b.py', { estimate: '2026-06-17' }),
    file('0923_HTML/index.html', { basis: 'name', date: '2026-09-23' }),
    file('0928_0929_JS.ipynb', { basis: 'split', dates: ['2026-09-28', '2026-09-29'] }),
    file('02_data-type/exercise.ipynb', { status: 'same' }),
  ]);

  it('날짜를 찾은 파일은 날짜별, 나머지는 큰 주제 폴더별 지난 자료 — 같은 파일은 빼고', () => {
    const rows = reviewRows(s, initialDates(s), new Set());
    expect(rows.map((r) => [r.kind, r.date || r.folder, r.files.length])).toEqual([
      ['date', '2026-09-23', 1],
      ['date', '2026-09-28', 1], // 두 날에 걸친 파일은 첫 날짜로 통째로(첫 버전)
      ['past', '01_variable', 2],
      ['past', '07_package', 2],
    ]);
    expect(rows[3].inner).toBe(2);
  });

  it('펼치면 안쪽 폴더로 나뉜다', () => {
    const rows = reviewRows(s, initialDates(s), new Set(['07_package']));
    expect(rows.filter((r) => r.kind === 'past').map((r) => r.folder)).toEqual(['01_variable', '07_package/team', '07_package/work']);
  });

  it('커리큘럼 추정 날짜를 채우고 되돌린다 — 지난 자료 줄이 그 날짜를 보인다', () => {
    const filled = withEstimates(s, initialDates(s));
    const past = reviewRows(s, filled, new Set()).filter((r) => r.kind === 'past');
    expect(past.map((r) => [r.folder, r.date, r.estimated])).toEqual([
      ['01_variable', '2026-06-16', true],
      ['07_package', '2026-06-17', true],
    ]);
    expect(withoutEstimates(s, filled)['01_variable/exercise.ipynb']).toBeNull();
    // 직접 고친 날짜는 되돌리지 않는다
    const edited = setRowDate(filled, past[1], '2026-06-18');
    expect(withoutEstimates(s, edited)['07_package/team/a.py']).toBe('2026-06-18');
  });

  it('날짜가 섞인 지난 자료 줄은 날짜를 비워 보인다', () => {
    const dates = { ...initialDates(s), '07_package/team/a.py': '2026-06-17' };
    const row = reviewRows(s, dates, new Set()).find((r) => r.folder === '07_package')!;
    expect([row.date, row.mixed]).toEqual(['', true]);
  });
});

describe('고른 날짜 확인 — 막지 않고 묻는다', () => {
  it('공휴일 · 주말 · 커리큘럼 밖 · 앞으로 올 날', () => {
    expect(dayNotice('2026-09-24', CAL)).toBe('추석 — 수업한 날이 맞나요?');
    expect(dayNotice('2026-09-27', CAL)).toBe('일요일 — 수업한 날이 맞나요?');
    expect(dayNotice('2026-09-22', CAL)).toBe('커리큘럼엔 수업이 없는 날이에요. 보강이었나요?');
    expect(dayNotice('2026-10-02', CAL)).toBe('앞으로 올 날짜로는 올릴 수 없어요.');
    expect(dayNotice('2026-09-23', CAL)).toBe('');
    expect(dayNotice('2026-09-24', { ...CAL, extraDays: ['2026-09-24'] })).toBe('');
    expect(dayNotice('2026-09-22', { ...CAL, classDays: [] })).toBe('');
  });

  it('GitHub 과목과 같은 이름 · 앞으로 올 날짜는 올릴 수 없다', () => {
    const s = subject([file('a.py')], { source: { id: '3', kind: 'github' } });
    expect(blockedReason(s, {}, CAL)).toContain('GitHub');
    expect(blockedReason(subject([file('a.py')]), { 'a.py': '2026-10-05' }, CAL)).toContain('앞으로');
    expect(blockedReason(subject([file('a.py')]), { 'a.py': null }, CAL)).toBe('');
  });
});

describe('올리기 — 100개씩, 지난 자료 먼저', () => {
  it('같은 파일은 빼고 지난 자료 → 날짜 순', () => {
    const s = subject([
      file('b.py', { basis: 'name', date: '2026-09-29' }),
      file('a.py', { basis: 'name', date: '2026-09-23' }),
      file('z.py'),
      file('same.py', { status: 'same' }),
    ]);
    expect(uploadItems(s, initialDates(s)).map((i) => [i.path, i.date])).toEqual([
      ['z.py', null],
      ['a.py', '2026-09-23'],
      ['b.py', '2026-09-29'],
    ]);
  });

  it('파일 수 · 크기로 나누고, 묶음마다 manifest 번호는 그 묶음 안에서', () => {
    const items = Array.from({ length: 205 }, (_, i) => ({ path: `f${i}.py`, date: i < 5 ? null : '2026-09-23', size: 10 }));
    const parts = batches(items);
    expect(parts.map((p) => p.length)).toEqual([100, 100, 5]);
    const m = manifest(parts[0]);
    expect(m.past).toEqual([0, 1, 2, 3, 4]);
    expect(m.days).toEqual([{ date: '2026-09-23', files: Array.from({ length: 95 }, (_, i) => i + 5) }]);
    expect(batches([{ path: 'big1', date: null, size: 15 }, { path: 'big2', date: null, size: 15 }], 100, 20).length).toBe(2);
  });

  it('고른 파일 경로 — 과목 하나면 맨 위 폴더가 과목, 여러 과목이면 그 아래', () => {
    expect(pickedPathOf({ what: 'subject', root: 'python_basic' }, 'python_basic', '01/a.py')).toBe('python_basic/01/a.py');
    expect(pickedPathOf({ what: 'cohort', root: '34기' }, 'web_client', 'x/a.js')).toBe('34기/web_client/x/a.js');
  });
});
