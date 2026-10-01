import { useQuery } from '@tanstack/react-query';
import type { CounselNote, Quest, QuestSubmission } from '@web/domain/types';

import { http } from './http';
import { queryClient } from './query';

export function useQuests(cohortId: string) {
  return useQuery({
    queryKey: ['quests', cohortId],
    enabled: Boolean(cohortId),
    queryFn: async () => {
      const { data } = await http.get<{ quests: Quest[]; submissions?: QuestSubmission[] }>('/quests', {
        params: { cohort: cohortId },
      });
      return data;
    },
  });
}

export function useQuestSubmissions(cohortId: string) {
  return useQuery({
    queryKey: ['quest-submissions', cohortId],
    enabled: Boolean(cohortId),
    queryFn: async () => {
      const { data } = await http.get<{ submissions: QuestSubmission[] }>('/quest-submissions', {
        params: { cohort: cohortId },
      });
      return data.submissions;
    },
  });
}

async function refreshQuests(): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: ['quests'] });
  await queryClient.invalidateQueries({ queryKey: ['quest-submissions'] });
}

export async function saveQuest(cohortId: string, draft: Partial<Quest> & { title: string }, id?: string): Promise<void> {
  if (id) await http.patch(`/quests/${id}`, draft);
  else await http.post('/quests', { cohortId, ...draft });
  await refreshQuests();
}

export async function submitQuest(
  id: string,
  evidence: { text?: string; link?: string },
): Promise<void> {
  await http.post(`/quests/${id}/submit`, evidence);
  await refreshQuests();
}

export async function reviewQuest(id: string, decision: 'approved' | 'rejected' | 'revoked', comment: string): Promise<void> {
  await http.post(`/quest-submissions/${id}/review`, { decision, comment });
  await refreshQuests();
}

export function useCounsel(cohortId: string, student?: string) {
  return useQuery({
    queryKey: ['counsel', cohortId, student ?? ''],
    enabled: Boolean(cohortId),
    queryFn: async () => {
      const { data } = await http.get<{ notes: CounselNote[] }>('/counsel-notes', {
        params: student ? { student } : { cohort: cohortId },
      });
      return data.notes;
    },
  });
}

export async function saveCounsel(uid: string, draft: Partial<CounselNote>, id?: string): Promise<void> {
  if (id) await http.patch(`/counsel-notes/${id}`, draft);
  else await http.post('/counsel-notes', { uid, ...draft });
  await queryClient.invalidateQueries({ queryKey: ['counsel'] });
}

export async function deleteCounsel(id: string): Promise<void> {
  await http.delete(`/counsel-notes/${id}`);
  await queryClient.invalidateQueries({ queryKey: ['counsel'] });
}
