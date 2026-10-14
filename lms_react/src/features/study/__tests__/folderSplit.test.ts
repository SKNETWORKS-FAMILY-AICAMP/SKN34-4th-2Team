import { describe, expect, it } from 'vitest';

import { notebookCells, partialNotebook } from '../folderFiles';
import {
  blockedReason,
  initialDates,
  initialSplits,
  manualSplit,
  reviewRows,
  splitProblem,
  uploadItems,
  type PlanCalendar,
  type PlanFile,
  type PlanSubject,
} from '../folderUploadModel';

const CAL: PlanCalendar = {
  today: '2026-10-01', start: '2026-06-15', end: '2026-12-07',
  holidays: { '2026-09-24': '추석' }, classDays: [], extraDays: [],
};
const CELLS = ['# JS 심화', '## 배열 메서드', 'arr.map(x => x)', '## 콜백 함수', 'setTimeout(cb)', '## 정리'];
const file = (path: string, extra: Partial<PlanFile> = {}): PlanFile => ({
  path, blob: '0'.repeat(40), size: 100, basis: 'pick', date: null, status: 'new', ...extra,
});
const subject = (files: PlanFile[]): PlanSubject => ({
  name: 'web_client', source: null, topic: null, topicBy: null, start: '', classDays: [], files,
  counts: { files: files.length, same: 0, dated: 0, past: 0, estimated: 0 }, warnings: [],
});

describe('두 날에 걸친 파일 — 나눠 넣기', () => {
  const nb = file('0928_0929_JS심화.ipynb', { basis: 'split', from: 'name', dates: ['2026-09-28', '2026-09-29'], cutCells: [3], cells: CELLS });
  const py = file('0928_0929_a.py', { basis: 'split', from: 'name', dates: ['2026-09-28', '2026-09-29'], cutCells: null });
  const s = subject([nb, py, file('a/plain.ipynb', { cells: CELLS })]);

  it('노트북은 나눠 넣기가 기본, 셀로 못 나누는 파일은 첫 날짜로 통째로', () => {
    const splits = initialSplits(s);
    expect(splits[nb.path]).toEqual({ mode: 'split', dates: ['2026-09-28', '2026-09-29'], cuts: [3] });
    expect(splits[py.path].mode).toBe('single');
  });

  it('날짜마다 올릴 몫 — 앞 날짜는 그날까지의 셀만, 마지막은 전체', () => {
    const splits = initialSplits(s);
    const items = uploadItems(s, initialDates(s), splits).filter((i) => i.path === nb.path);
    expect(items).toEqual([
      { path: nb.path, date: '2026-09-28', size: 100, upto: 3 },
      { path: nb.path, date: '2026-09-29', size: 100 },
    ]);
    // 줄 보기 — 날짜마다 그날 몫 줄(날짜는 칸에서 고친다)
    const parts = reviewRows(s, initialDates(s), new Set(), splits).filter((r) => r.part);
    expect(parts.map((r) => r.date)).toEqual(['2026-09-28', '2026-09-29']);
  });

  it('직접 나누기 — 둘째 날짜를 고르기 전엔 올릴 수 없다', () => {
    const plain = s.files[2];
    const manual = manualSplit(plain, '2026-09-28');
    expect(manual).toEqual({ mode: 'split', dates: ['2026-09-28', ''], cuts: [3], manual: true });
    expect(splitProblem(manual, CAL, CELLS.length)).toContain('날짜를 골라');
    expect(blockedReason(s, initialDates(s), CAL, { [plain.path]: manual })).toContain('a/plain.ipynb');
    const ok = { ...manual, dates: ['2026-09-28', '2026-09-29'] };
    expect(splitProblem(ok, CAL, CELLS.length)).toBe('');
    expect(splitProblem({ ...ok, dates: ['2026-09-29', '2026-09-28'] }, CAL, CELLS.length)).toContain('앞 날짜가 먼저');
    expect(splitProblem({ ...ok, cuts: [0] }, CAL, CELLS.length)).toContain('셀');
    expect(splitProblem({ ...ok, dates: ['2026-09-28', '2026-10-05'] }, CAL, CELLS.length)).toContain('앞으로');
  });
});

describe('앞 셀만 잘라낸 노트북', () => {
  it('셀 번호는 화면 · 서버가 센 것과 같다 — 셀이 아닌 항목은 빼고 센다', () => {
    const raw = JSON.stringify({
      nbformat: 4,
      metadata: { kernelspec: { name: 'python3' } },
      cells: [
        { cell_type: 'markdown', source: ['# 1일차'] },
        'not a cell',
        { cell_type: 'code', source: 'x = 1', outputs: [] },
        { cell_type: 'markdown', source: '## 2일차' },
        { cell_type: 'code', source: 'y = 2', outputs: [] },
      ],
    });
    expect(notebookCells(raw).map((c) => c.source)).toEqual(['# 1일차', 'x = 1', '## 2일차', 'y = 2']);
    const first = JSON.parse(partialNotebook(raw, 2));
    expect(first.cells.map((c: { source: unknown }) => c.source)).toEqual([['# 1일차'], 'x = 1']);
    expect(first.metadata).toEqual({ kernelspec: { name: 'python3' } });
    expect(first.nbformat).toBe(4);
    // 앞부분 셀은 원래 노트북과 글이 같다 — 둘째 날엔 새 셀(2일차)만 새 내용이 된다
    expect(notebookCells(partialNotebook(raw, 2))).toEqual(notebookCells(raw).slice(0, 2));
  });
});
