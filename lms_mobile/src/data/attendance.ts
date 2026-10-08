import type {
  Attendance,
  AttendanceIssue,
  SeatPresence,
  SeatPresenceState,
  SpotCheck,
  SpotCheckItem,
  SpotCheckPeriod,
} from '@web/domain/types';

import { readApiError } from './http';
import { patchBootstrap, refreshBootstrap, runCommand, useDb } from './query';

export function useAttendance(): Attendance[] {
  return useDb()?.attendances ?? [];
}

export function useIssues(): AttendanceIssue[] {
  return useDb()?.attendanceIssues ?? [];
}

export function usePresence(): SeatPresence[] {
  return useDb()?.seatPresence ?? [];
}

export function useSpotChecks(): SpotCheck[] {
  return useDb()?.spotChecks ?? [];
}

export async function submitAttendanceRequest(payload: Record<string, unknown>): Promise<void> {
  try {
    await runCommand('submitAttendanceRequest', payload);
  } catch (error) {
    throw new Error(await readApiError(error));
  }
}

export async function cancelAttendanceRequest(id: string): Promise<void> {
  await runCommand('cancelAttendanceRequest', { id });
}

export async function reviewAttendanceRequest(ids: string[], decision: 'approved' | 'rejected', comment: string): Promise<void> {
  await runCommand('reviewAttendanceRequest', { ids, decision, comment });
}

export async function setSeatPresence(
  dateKey: string,
  period: number,
  userId: string,
  state: SeatPresenceState,
): Promise<void> {
  patchBootstrap((db) => ({
    seatPresence: [
      ...db.seatPresence.filter((row) => !(row.dateKey === dateKey && row.period === period && row.userId === userId)),
      { dateKey, period, userId, state },
    ],
  }));
  try {
    await runCommand('setSeatPresence', { dateKey, period, userId, state });
  } catch (error) {
    void refreshBootstrap();
    throw error;
  }
}

export interface SpotCheckDraft {
  id?: string;
  checkedAt: Date;
  period: SpotCheckPeriod;
  note?: string;
  items: SpotCheckItem[];
}

/** 점검 한 번을 통째로 저장한다 — id 가 있으면 그 점검을 고쳐 쓴다. 저장된 id 를 돌려준다. */
export async function savePresenceCheck(cohortId: string, draft: SpotCheckDraft): Promise<string> {
  const data = await runCommand('savePresenceCheck', {
    id: draft.id,
    cohortId,
    checkedAt: draft.checkedAt.toISOString(),
    period: draft.period,
    note: draft.note,
    items: draft.items,
  });
  return String(data.id ?? draft.id ?? '');
}

export async function deletePresenceCheck(id: string): Promise<void> {
  patchBootstrap((db) => ({ spotChecks: db.spotChecks.filter((row) => row.id !== id) }));
  try {
    await runCommand('deletePresenceCheck', { id });
  } catch (error) {
    void refreshBootstrap();
    throw error;
  }
}
