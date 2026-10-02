import type { Assessment, AssessmentQuestion, AssessmentSubmission, User } from '@web/domain/types';

import { http, readApiError } from './http';
import { runCommand, useDb } from './query';

export function useAssessments(): Assessment[] {
  return useDb()?.assessments ?? [];
}

export function useSubmissions(assessmentId?: string): AssessmentSubmission[] {
  const rows = useDb()?.assessmentSubmissions ?? [];
  return assessmentId === undefined ? rows : rows.filter((row) => row.assessmentId === assessmentId);
}

export async function fetchTake(assessmentId: string): Promise<AssessmentQuestion[]> {
  try {
    const { data } = await http.get<{ questions: AssessmentQuestion[] }>(
      `/assessments/${encodeURIComponent(assessmentId)}/take`,
    );
    return data.questions.map((question) => ({ ...question, acceptedAnswers: [] }));
  } catch (error) {
    throw new Error(await readApiError(error));
  }
}

export async function fetchReview(assessmentId: string, user: User) {
  try {
    return await loadReview(assessmentId, user);
  } catch (error) {
    throw new Error(await readApiError(error));
  }
}

async function loadReview(assessmentId: string, user: User) {
  const { data } = await http.get<{
    questions: AssessmentQuestion[];
    submission: {
      id: string;
      totalScore: number;
      autoTotalScore: number;
      submittedAt: string | null;
      answers: AssessmentSubmission['answers'];
    };
  }>(`/assessments/${encodeURIComponent(assessmentId)}/review`);
  return {
    questions: data.questions,
    submission: {
      id: data.submission.id,
      assessmentId,
      userId: user.uid,
      userDisplayName: user.displayName,
      answers: data.submission.answers,
      autoTotalScore: data.submission.autoTotalScore,
      totalScore: data.submission.totalScore,
      submittedAt: data.submission.submittedAt ? new Date(data.submission.submittedAt) : undefined,
    } satisfies AssessmentSubmission,
  };
}

export async function submitAssessment(
  assessmentId: string,
  answers: Record<string, number | string | null>,
): Promise<Record<string, unknown>> {
  return runCommand('submitAssessment', { assessmentId, answers });
}

export async function saveAssessment(
  assessment: Assessment,
  questions: AssessmentQuestion[],
  cohortId: string,
): Promise<void> {
  await runCommand('saveAssessment', {
    id: assessment.id || undefined,
    cohortId,
    title: assessment.title,
    tags: assessment.tags,
    maxScore: assessment.maxScore,
    startAt: assessment.startAt?.toISOString(),
    endAt: assessment.endAt?.toISOString(),
    published: assessment.published,
    questions,
  });
}

export async function deleteAssessment(id: string): Promise<void> {
  await runCommand('upsert', { table: 'assessments', id, action: 'delete' });
}

export async function setPublished(id: string, published: boolean): Promise<void> {
  await runCommand('upsert', { table: 'assessments', id, action: 'update', published });
}

export async function gradeAnswer(submissionId: string, questionId: string, score: number): Promise<void> {
  await runCommand('gradeAssessmentAnswer', { submissionId, questionId, score });
}
