import type { ProjectTeam, SeatingRoom } from '@web/domain/types';

import { runCommand, useDb } from './query';

export function useRooms(): SeatingRoom[] {
  return useDb()?.seatingRooms ?? [];
}

export function useTeams(): ProjectTeam[] {
  return useDb()?.projectTeams ?? [];
}

export async function replaceTeams(
  cohortId: string,
  teams: { id?: string; name: string; memberIds: string[]; sortOrder: number; colorIndex: number }[],
  deleteIds: string[],
): Promise<void> {
  await runCommand('replaceProjectTeams', { cohortId, teams, deleteIds });
}
