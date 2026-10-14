import { describe, expect, it } from 'vitest';

import type { SeatPresence, User } from '../../domain/types';
import { rollCallSessions, rollCallTable } from './rollCallTable';

const student = (uid: string, displayName: string) => ({ uid, displayName }) as User;
const students = [student('b', '나학생'), student('a', '가학생'), student('c', '다학생')];

const presence: SeatPresence[] = [
  { dateKey: '2026-10-07', period: 9, userId: 'a', state: 'confirmed' },
  { dateKey: '2026-10-07', period: 9, userId: 'b', state: 'held' },
  { dateKey: '2026-10-08', period: 14, userId: 'a', state: 'confirmed' },
  { dateKey: '2026-10-08', period: 14, userId: 'x', state: 'confirmed' },
  { dateKey: '2026-09-30', period: 9, userId: 'a', state: 'confirmed' },
];

describe('교시 호명 기록', () => {
  it('기간 안에서 호명한 교시만 날짜 · 교시 차례로 모은다', () => {
    const sessions = rollCallSessions(presence, students, '2026-10-01', '2026-10-08');
    expect(sessions).toEqual([
      { dateKey: '2026-10-07', period: 9, confirmed: 1, held: 1, unknown: 1 },
      { dateKey: '2026-10-08', period: 14, confirmed: 1, held: 0, unknown: 2 },
    ]);
  });

  it('교시마다 학생을 이름 차례로 펼치고, 기록이 없으면 미확인으로 적는다', () => {
    const sessions = rollCallSessions(presence, students, '2026-10-07', '2026-10-07');
    const table = rollCallTable(sessions, presence, students, (uid) => `${uid}번`);
    expect(table.header).toEqual(['날짜', '교시', '이름', '좌석', '호명 결과']);
    expect(table.rows).toEqual([
      ['2026-10-07', '09:00', '가학생', 'a번', '확인'],
      ['2026-10-07', '09:00', '나학생', 'b번', '보류'],
      ['2026-10-07', '09:00', '다학생', 'c번', '미확인'],
    ]);
  });
});
