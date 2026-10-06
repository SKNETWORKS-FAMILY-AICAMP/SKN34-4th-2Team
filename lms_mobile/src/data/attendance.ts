import type { Attendance, AttendanceIssue, SeatPresence, SeatPresenceState, SpotCheck } from '@web/domain/types';

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

export async function savePresenceCheck(payload: Record<string, unknown>): Promise<void> {
  await runCommand('savePresenceCheck', payload);
}
