import { beforeEach, describe, expect, it } from 'vitest';

import {
  cancelAttendanceRequest,
  reviewAttendanceRequests,
  submitAttendanceRequest,
} from '../../data/repository';
import { DemoAccounts, seedUsers } from '../../data/seed';
import { getDb, resetDb } from '../../data/store';
import type { AttendanceIssue } from '../../domain/types';
import {
  draftError,
  requestDateRange,
  requestLabel,
  requestsToCsv,
  resultingStatus,
  type AttendanceRequestDraft,
} from './attendanceRequest';

const student = seedUsers.find((u) => u.uid === DemoAccounts.studentUid)!;
const admin = seedUsers.find((u) => u.uid === DemoAccounts.adminUid)!;

const base: AttendanceRequestDraft = {
  dateKey: '2026-09-30',
  issueType: 'earlyLeave',
  timeFrom: '15:00',
  reason: '병원 진료',
  officialLeaveUsed: true,
  officialLeaveType: 'sick',
};

beforeEach(() => {
  resetDb();
});

describe('출결 신청 규칙', () => {
  it('유형별 필수 칸을 막는다', () => {
    expect(draftError({ ...base, timeFrom: undefined })).toContain('퇴실 시각');
    expect(draftError({ ...base, issueType: 'outing', timeFrom: '13:00', timeTo: '12:00' })).toContain('복귀 시각');
    expect(draftError({ ...base, officialLeaveType: undefined })).toContain('공가 유형');
    expect(draftError({ ...base, reason: '  ' })).toContain('사유');
    expect(draftError(base)).toBeNull();
  });

  it('요약과 반영 상태를 만든다', () => {
    expect(requestLabel(base)).toBe('조퇴 15:00 · 공가(병가)');
    const late = { issueType: 'late', officialLeaveUsed: false } as AttendanceIssue;
    const absent = { issueType: 'absent', officialLeaveUsed: false } as AttendanceIssue;
    expect(resultingStatus([late, absent])).toBe('absent');
    expect(resultingStatus([late, { ...absent, officialLeaveUsed: true }])).toBe('officialLeave');
  });

  it('발생일 범위는 서버와 같다(31일 전 ~ 62일 뒤)', () => {
    expect(requestDateRange('2026-09-30')).toEqual({ min: '2026-08-30', max: '2026-12-01' });
  });

  it('CSV 는 BOM 과 따옴표 이스케이프를 넣는다', () => {
    const row = { id: 'x', userId: 'u', dateKey: '2026-09-30', issueType: 'late', status: 'submitted', reason: '버스, "고장"' } as AttendanceIssue;
    const csv = requestsToCsv([row], () => '홍길동');
    expect(csv.startsWith('\uFEFF발생일')).toBe(true);
    expect(csv).toContain('"버스, ""고장"""');
  });
});

describe('출결 신청 흐름', () => {
  it('학생이 신청하고 매니저가 승인하면 출석부 상태가 바뀐다', async () => {
    const id = await submitAttendanceRequest(base, null, student);
    const saved = getDb().attendanceIssues.find((i) => i.id === id)!;
    expect(saved.status).toBe('submitted');
    expect(saved.label).toBe('조퇴 15:00 · 공가(병가)');

    await reviewAttendanceRequests([id], 'approved', admin);
    expect(getDb().attendanceIssues.find((i) => i.id === id)?.status).toBe('approved');
    const day = getDb().attendances.find((a) => a.userId === student.uid && a.dateKey === base.dateKey);
    expect(day?.status).toBe('officialLeave');
    expect(day?.statusSource).toBe('form');
  });

  it('반려는 메모를 남기고 출석부를 건드리지 않는다', async () => {
    const before = getDb().attendances.find((a) => a.userId === student.uid && a.dateKey === base.dateKey)?.status;
    const id = await submitAttendanceRequest({ ...base, officialLeaveUsed: false }, null, student);
    await reviewAttendanceRequests([id], 'rejected', admin, '증빙이 필요합니다');
    const saved = getDb().attendanceIssues.find((i) => i.id === id)!;
    expect(saved.status).toBe('rejected');
    expect(saved.reviewComment).toBe('증빙이 필요합니다');
    expect(getDb().attendances.find((a) => a.userId === student.uid && a.dateKey === base.dateKey)?.status).toBe(before);
  });

  it('승인을 거두면 출석부가 신청 전 상태로 돌아간다', async () => {
    const dayOf = () => getDb().attendances.find((a) => a.userId === student.uid && a.dateKey === base.dateKey);
    const before = { status: dayOf()?.status, source: dayOf()?.statusSource };
    const id = await submitAttendanceRequest(base, null, student);
    await reviewAttendanceRequests([id], 'approved', admin);
    expect(dayOf()?.status).toBe('officialLeave');

    await reviewAttendanceRequests([id], 'submitted', admin);
    expect(dayOf()?.status).toBe(before.status);
    expect(dayOf()?.statusSource).toBe(before.source);
  });

  it('같은 날 다른 승인이 남아 있으면 그 상태로 다시 매긴다', async () => {
    const dayOf = () => getDb().attendances.find((a) => a.userId === student.uid && a.dateKey === base.dateKey);
    const leave = await submitAttendanceRequest(base, null, student);
    const late = await submitAttendanceRequest(
      { ...base, issueType: 'late', timeFrom: '10:00', officialLeaveUsed: false, officialLeaveType: undefined },
      null,
      student,
    );
    await reviewAttendanceRequests([leave, late], 'approved', admin);
    expect(dayOf()?.status).toBe('officialLeave');

    await reviewAttendanceRequests([leave], 'rejected', admin, '증빙 없음');
    expect(dayOf()?.status).toBe('late');
    expect(dayOf()?.statusSource).toBe('form');
  });

  it('매니저가 승인된 신청을 지워도 출석부를 되돌린다', async () => {
    const dayOf = () => getDb().attendances.find((a) => a.userId === student.uid && a.dateKey === base.dateKey);
    const before = dayOf()?.status;
    const id = await submitAttendanceRequest(base, null, student);
    await reviewAttendanceRequests([id], 'approved', admin);
    await cancelAttendanceRequest(id);
    expect(dayOf()?.status).toBe(before);
  });

  it('고치면 다시 확인 대기가 되고 취소하면 사라진다', async () => {
    const id = await submitAttendanceRequest(base, null, student);
    await reviewAttendanceRequests([id], 'rejected', admin, '다시');
    await submitAttendanceRequest({ ...base, id, reason: '병원 진료(진단서 첨부)' }, null, student);
    const edited = getDb().attendanceIssues.find((i) => i.id === id)!;
    expect(edited.status).toBe('submitted');
    expect(edited.reason).toBe('병원 진료(진단서 첨부)');

    await cancelAttendanceRequest(id);
    expect(getDb().attendanceIssues.some((i) => i.id === id)).toBe(false);
  });
});
