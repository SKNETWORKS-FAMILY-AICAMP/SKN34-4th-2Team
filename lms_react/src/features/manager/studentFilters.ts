import { dateKeyOf } from '../../data/seed';
import type { Attendance, AttendanceIssue, SpotCheck, User } from '../../domain/types';
import type { ExportTable } from '../export/tableExport';

/**
 * 학생 빠른 필터 — 지정 알림의 대상 고르기와 AI 어시스턴트가 같은 기준을 쓴다.
 * 서버 쪽 기준은 lms_api/lms/manager_commands.py 의 find_students.
 */
export type StudentFilterId = 'missingCheckIn' | 'missingAttendanceForm' | 'absentInSpotCheck';

export const StudentFilterLabels: Record<StudentFilterId, string> = {
  missingCheckIn: '입실 기록 없음',
  missingAttendanceForm: '출결 신청 없음',
  absentInSpotCheck: '최근 불시 점검 「무」',
};

export const StudentFilterHints: Record<StudentFilterId, string> = {
  missingCheckIn: '그날 출석부에 입실 시각도, 출석 · 지각 처리도 없는 학생',
  missingAttendanceForm: '그날 날짜로 출결 신청(지각 · 조퇴 · 외출 · 결석 · 공가)을 하지 않은 학생',
  absentInSpotCheck: '그날 마지막 불시 점검에서 「무」였던 학생',
};

export interface FilterSources {
  attendances: Attendance[];
  issues: AttendanceIssue[];
  spotChecks: SpotCheck[];
}

export function checkedInIds(attendances: Attendance[], dateKey: string): Set<string> {
  return new Set(
    attendances
      .filter(
        (a) =>
          a.dateKey === dateKey &&
          (a.checkInTime !== undefined || a.status === 'present' || a.status === 'late'),
      )
      .map((a) => a.userId),
  );
}

export function formSubmittedIds(issues: AttendanceIssue[], dateKey: string): Set<string> {
  return new Set(issues.filter((i) => i.dateKey === dateKey).map((i) => i.userId));
}

/** 그날 마지막 불시 점검 */
export function latestSpotCheckOn(checks: SpotCheck[], dateKey: string): SpotCheck | undefined {
  return checks
    .filter((c) => dateKeyOf(c.checkedAt) === dateKey)
    .reduce<SpotCheck | undefined>((latest, c) => (latest === undefined || c.checkedAt > latest.checkedAt ? c : latest), undefined);
}

/** 고른 조건을 모두 만족하는(교집합) 학생. 조건이 없으면 모두. */
export function matchStudents(
  students: User[],
  filters: StudentFilterId[],
  dateKey: string,
  sources: FilterSources,
): User[] {
  if (filters.length === 0) return students;
  const checkedIn = filters.includes('missingCheckIn') ? checkedInIds(sources.attendances, dateKey) : null;
  const submitted = filters.includes('missingAttendanceForm') ? formSubmittedIds(sources.issues, dateKey) : null;
  const latest = filters.includes('absentInSpotCheck') ? latestSpotCheckOn(sources.spotChecks, dateKey) : undefined;
  const absent = new Set(latest?.items.filter((i) => i.state === 'absent').map((i) => i.userId) ?? []);
  return students.filter(
    (s) =>
      (checkedIn === null || !checkedIn.has(s.uid)) &&
      (submitted === null || !submitted.has(s.uid)) &&
      (!filters.includes('absentInSpotCheck') || absent.has(s.uid)),
  );
}

// ── 불시 점검 내려받기 ─────────────────────────────────

export const SpotCheckPeriodLabels = { am: '오전', pm: '오후' } as const;

function clock(at: Date): string {
  return `${String(at.getHours()).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')}`;
}

/**
 * 점검 기록을 한 줄에 학생 한 명씩 펼친다.
 * 점검 뒤에 들어온 학생처럼 기록이 없는 학생은 「미확인」으로 적는다.
 */
export function spotChecksTable(
  checks: SpotCheck[],
  students: User[],
  seatLabelOf: (uid: string) => string,
): ExportTable {
  const header = ['점검일', '점검시각', '구분', '점검자', '이름', '좌석', '상태', '사유', '메모'];
  const byName = [...students].sort((a, b) => a.displayName.localeCompare(b.displayName, 'ko'));
  const rows: string[][] = [];
  for (const check of [...checks].sort((a, b) => a.checkedAt.getTime() - b.checkedAt.getTime())) {
    const itemOf = new Map(check.items.map((i) => [i.userId, i]));
    const people = [
      ...byName.filter((s) => itemOf.has(s.uid)),
      ...byName.filter((s) => !itemOf.has(s.uid)),
    ];
    for (const student of people) {
      const item = itemOf.get(student.uid);
      rows.push([
        dateKeyOf(check.checkedAt),
        clock(check.checkedAt),
        SpotCheckPeriodLabels[check.period],
        check.checkedByName ?? '',
        student.displayName,
        seatLabelOf(student.uid),
        item === undefined ? '미확인' : item.state === 'present' ? '유' : '무',
        item?.reason ?? '',
        check.note ?? '',
      ]);
    }
  }
  return { title: '불시 점검', header, rows };
}
