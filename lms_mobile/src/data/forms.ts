import type { FormAnswer, FormTask } from '@web/domain/types';

import { runCommand, useDb } from './query';

export function useFormTasks(): FormTask[] {
  return useDb()?.formTasks ?? [];
}

export function useFormResponses(taskId?: string) {
  const rows = useDb()?.formResponses ?? [];
  return taskId === undefined ? rows : rows.filter((row) => row.taskId === taskId);
}

export async function saveFormTask(task: FormTask, cohortId: string, exists: boolean): Promise<string> {
  const data = await runCommand('saveFormTask', {
    id: exists ? task.id : undefined,
    cohortId,
    title: task.title,
    description: task.description,
    mode: task.mode === 'builtin' ? 'builtin' : 'external_form',
    formUrl: task.formUrl,
    questions: task.mode === 'builtin' ? task.questions : [],
    notionGuideUrl: task.notionGuideUrl,
    dueAt: task.dueAt.toISOString(),
    published: task.published,
  });
  return String(data.id ?? task.id);
}

export async function deleteFormTask(id: string): Promise<void> {
  await runCommand('deleteFormTask', { id });
}

export async function submitFormResponse(taskId: string, answers: Record<string, FormAnswer>): Promise<void> {
  await runCommand('submitFormResponse', { taskId, answers });
}

export async function markFormResponded(taskId: string, uid: string): Promise<void> {
  await runCommand('markFormResponded', { taskId, uid, source: 'manual' });
}
