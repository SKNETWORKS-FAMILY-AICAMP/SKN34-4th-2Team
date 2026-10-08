import { ClassPeriods } from '../../domain/constants';
import type { SeatPresence, User } from '../../domain/types';
import type { ExportTable } from '../export/csv';

/**
 * 교시 호명 기록 — 강사가 교시마다 남긴 확인 · 보류를 관리자가 내려받는다.
 * 호명을 한 번이라도 한 교시만 싣고, 그 교시에 기록이 없는 학생은 「미확인」으로 적는다.
 */
export interface RollCallSession {
  dateKey: string;
  period: number;
  confirmed: number;
  held: number;
  unknown: number;
}

export function periodLabelOf(period: number): string {
  return ClassPeriods.find((p) => Number(p.id) === period)?.label ?? `${period}시`;
}

function inRange(presence: SeatPresence[], students: User[], from: string, to: string): SeatPresence[] {
  const ids = new Set(students.map((s) => s.uid));
  return presence.filter((p) => ids.has(p.userId) && p.dateKey >= from && p.dateKey <= to);
}

const sessionKey = (dateKey: string, period: number) => `${dateKey}|${String(period).padStart(2, '0')}`;

/** 기간 안에 호명한 교시 — 날짜 · 교시 차례 */
export function rollCallSessions(presence: SeatPresence[], students: User[], from: string, to: string): RollCallSession[] {
  const byKey = new Map<string, RollCallSession>();
  for (const p of inRange(presence, students, from, to)) {
    const key = sessionKey(p.dateKey, p.period);
    const session = byKey.get(key) ?? { dateKey: p.dateKey, period: p.period, confirmed: 0, held: 0, unknown: 0 };
    if (p.state === 'confirmed') session.confirmed += 1;
    else if (p.state === 'held') session.held += 1;
    byKey.set(key, session);
  }
  return [...byKey.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, s]) => ({ ...s, unknown: Math.max(0, students.length - s.confirmed - s.held) }));
}

const STATE_LABEL = { confirmed: '확인', held: '보류', unknown: '미확인' } as const;

/** 한 줄에 학생 한 명씩 — 교시마다 이름 차례 */
export function rollCallTable(
  sessions: RollCallSession[],
  presence: SeatPresence[],
  students: User[],
  seatLabelOf: (uid: string) => string,
): ExportTable {
  const header = ['날짜', '교시', '이름', '좌석', '호명 결과'];
  const byName = [...students].sort((a, b) => a.displayName.localeCompare(b.displayName, 'ko'));
  const stateOf = new Map(presence.map((p) => [`${sessionKey(p.dateKey, p.period)}|${p.userId}`, p.state]));
  const rows: string[][] = [];
  for (const session of sessions) {
    const key = sessionKey(session.dateKey, session.period);
    for (const student of byName) {
      const state = stateOf.get(`${key}|${student.uid}`) ?? 'unknown';
      rows.push([session.dateKey, periodLabelOf(session.period), student.displayName, seatLabelOf(student.uid), STATE_LABEL[state]]);
    }
  }
  return { title: '교시 호명 기록', header, rows };
}
