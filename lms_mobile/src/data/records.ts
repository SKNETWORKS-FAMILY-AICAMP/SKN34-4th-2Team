import type { Submission, SubmissionStatus } from '@web/domain/types';

import { http, readApiError } from './http';
import { runCommand, useDb } from './query';

export interface UploadedEvidence {
  key: string;
  name: string;
  contentType: string;
  size: number;
  url: string;
}

export function useSubmissions(): Submission[] {
  return useDb()?.submissions ?? [];
}

export async function uploadEvidence(file: { uri: string; name: string; type: string }): Promise<UploadedEvidence> {
  const form = new FormData();
  form.append('file', { uri: file.uri, name: file.name, type: file.type } as unknown as Blob);
  try {
    const { data } = await http.post<UploadedEvidence>('/uploads/record-evidence', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  } catch (error) {
    throw new Error(await readApiError(error));
  }
}

export async function createSubmission(
  submission: Omit<Submission, 'id' | 'submittedAt' | 'fileUrls'>,
  evidence: UploadedEvidence[],
  cohortId: string,
): Promise<string> {
  const result = await runCommand('upsert', {
    table: 'record_submissions',
    action: 'insert',
    ...submission,
    files: evidence.map(({ key, name, contentType, size }) => ({ key, name, contentType, size })),
    cohortId,
  });
  return String(result.id ?? '');
}

export async function reviewSubmission(
  id: string,
  status: SubmissionStatus,
  reviewComment?: string,
  mileageAmount?: number,
): Promise<void> {
  await runCommand('reviewRecord', { id, status, reviewComment, mileageAmount });
}
