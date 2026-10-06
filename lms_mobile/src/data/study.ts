import type { StudyNote, StudySource } from '@web/domain/types';

export interface GithubOwner {
  id: string;
  owner: string;
  lastSyncedAt: string | null;
  lastError: string;
}

import { http, readApiError } from './http';
import { useDb } from './query';

export function useSources(): StudySource[] {
  return useDb()?.studySources ?? [];
}

export function useNotes(): StudyNote[] {
  return useDb()?.studyNotes ?? [];
}

async function call<T>(request: () => Promise<T>): Promise<T> {
  try {
    return await request();
  } catch (error) {
    throw new Error(await readApiError(error));
  }
}

async function refresh(): Promise<void> {
  const { queryClient, queryKeys } = await import('./query');
  await queryClient.invalidateQueries({ queryKey: queryKeys.bootstrap });
}

export async function fetchNote(id: string): Promise<StudyNote> {
  const { mapStudyNote } = await import('@web/data/bootstrapMap');
  const { data } = await http.get<Record<string, unknown>>(`/study-notes/${encodeURIComponent(id)}`);
  return mapStudyNote(data);
}

export async function createNote(sourceId: string, scopeType: string, scopeValue: string): Promise<Record<string, unknown>> {
  const { data } = await http.post<Record<string, unknown>>('/study-notes', { sourceId, scopeType, scopeValue });
  return data;
}

export async function deleteNote(id: string): Promise<void> {
  await http.delete(`/study-notes/${encodeURIComponent(id)}`);
  await refresh();
}

export async function listGithub(cohortId: string): Promise<GithubOwner[]> {
  const { data } = await call(() => http.get<{ owners: GithubOwner[] }>('/study-sources/github', { params: { cohortId } }));
  return data.owners ?? [];
}

export async function addGithub(cohortId: string, owner: string): Promise<void> {
  await call(() => http.post('/study-sources/github', { cohortId, owner }));
}

export async function removeGithub(id: string): Promise<void> {
  await call(() => http.delete(`/study-sources/github/${encodeURIComponent(id)}`));
}

export async function syncSources(cohortId: string): Promise<void> {
  await call(() => http.post('/study-sources/sync', { cohortId, force: true }));
  await refresh();
}

export async function setSourceActive(sourceId: string, isActive: boolean): Promise<void> {
  await call(() => http.patch(`/study-sources/${encodeURIComponent(sourceId)}`, { isActive }));
  await refresh();
}
