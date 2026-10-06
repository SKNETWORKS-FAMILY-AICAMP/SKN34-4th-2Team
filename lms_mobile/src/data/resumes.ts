import { resumeStatusToServer } from '@web/features/resume/resumeGroups';
import type { Resume, ResumeFeedback } from '@web/domain/types';

import { http } from './http';
import { patchBootstrap, runCommand, useDb } from './query';

export function useResumes(): Resume[] {
  return useDb()?.resumes ?? [];
}

export function useFeedbacks(resumeId: string): ResumeFeedback[] {
  return (useDb()?.resumeFeedbacks ?? []).filter((row) => row.resumeId === resumeId);
}

function forServer(resume: Partial<Resume>): Record<string, unknown> {
  const { baseResumeId, sourceTailoredResumeId, linkedJobId, ...rest } = resume;
  void baseResumeId;
  void sourceTailoredResumeId;
  void linkedJobId;
  return rest.status === undefined ? rest : { ...rest, status: resumeStatusToServer(rest.status) };
}

export async function createResume(resume: Omit<Resume, 'id' | 'updatedAt'>, cohortId: string): Promise<string> {
  const result = await runCommand('upsert', {
    table: 'resumes',
    action: 'insert',
    ...forServer(resume),
    cohortId,
  });
  return String(result.id);
}

export async function updateResume(id: string, patch: Partial<Resume>): Promise<void> {
  patchBootstrap((db) => ({
    resumes: db.resumes.map((resume) => (resume.id === id ? { ...resume, ...patch, updatedAt: new Date() } : resume)),
  }));
  await runCommand('upsert', { table: 'resumes', id, action: 'update', ...forServer(patch) });
}

export async function deleteResume(id: string): Promise<void> {
  await runCommand('upsert', { table: 'resumes', id, action: 'delete' });
}

export async function setBaseResume(resumeId: string, mine: Resume[]): Promise<void> {
  await Promise.all(
    mine.map((resume) =>
      runCommand('upsert', {
        table: 'resumes',
        id: resume.id,
        action: 'update',
        isBaseResume: resume.id === resumeId,
      }),
    ),
  );
}

export interface ReviewSuggestion {
  index: number;
  fieldPath: string;
  originalQuote: string;
  suggestedRevision: string | null;
  reason: string;
  status: string;
}

export async function requestReview(resumeId: string): Promise<{ summary?: string; suggestions?: ReviewSuggestion[] }> {
  const { data } = await http.post<{ summary?: string; sentence_reviews?: ReviewSuggestion[] }>('/resume-review', {
    resumeId,
  });
  return { summary: data.summary, suggestions: data.sentence_reviews };
}
