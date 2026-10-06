import type { Cohort, CurriculumSheet, InflearnPackage, StudentIntake, User } from '@web/domain/types';

import { http } from './http';
import { runCommand, useDb } from './query';

export function useUsers(): User[] {
  return useDb()?.users ?? [];
}

export function useCohorts(): Cohort[] {
  return useDb()?.cohorts ?? [];
}

export function useCurriculum(): CurriculumSheet[] {
  return useDb()?.curriculumSheets ?? [];
}

export function usePackages(): InflearnPackage[] {
  return useDb()?.inflearnPackages ?? [];
}

export async function updateProfile(uid: string, patch: Partial<User>): Promise<void> {
  await runCommand('updateProfile', { uid, ...patch });
}

/** 서버가 만든 로그인 이메일과 임시 비밀번호를 한 번만 돌려준다 */
export async function createUser(
  user: Partial<User> & { email: string; role: User['role']; cohortId: string },
): Promise<{ email: string; password: string }> {
  const data = await runCommand('createUser', { ...user });
  return { email: String(data.email ?? user.email), password: String(data.password ?? '') };
}

export async function resetPassword(uid: string): Promise<Record<string, unknown>> {
  return runCommand('resetPassword', { uid });
}

export async function saveIntake(uid: string, intake: StudentIntake): Promise<void> {
  await runCommand('saveStudentIntake', { uid, ...intake });
}

export async function createCohort(cohort: Cohort): Promise<void> {
  await runCommand('createCohort', { ...cohort });
}

export async function updateCohort(cohortId: string, patch: Partial<Cohort>): Promise<void> {
  await runCommand('updateCohort', { cohortId, ...patch });
}

export async function replaceCurriculum(sheet: CurriculumSheet, cohortId: string): Promise<void> {
  await runCommand('replaceCurriculumSheet', {
    cohortId,
    title: sheet.title,
    fileName: sheet.fileName,
    rows: sheet.rows,
  });
}

export async function savePackage(pack: InflearnPackage, cohortId: string): Promise<void> {
  await runCommand('upsert', {
    table: 'inflearn_packages',
    id: pack.id || undefined,
    cohortId,
    title: pack.title,
    subject: pack.subject,
    type: pack.type,
    summary: pack.summary,
    units: pack.units,
    courses: pack.courses,
    isPublished: pack.isPublished,
    sortOrder: pack.sortOrder,
  });
}

export async function deletePackage(id: string): Promise<void> {
  await runCommand('upsert', { table: 'inflearn_packages', id, action: 'delete' });
}

export async function syncQualExams(): Promise<Record<string, number>> {
  const { data } = await http.post<{ counts: Record<string, number> }>('/qual-exams/sync', {});
  const { queryClient, queryKeys } = await import('./query');
  await queryClient.invalidateQueries({ queryKey: queryKeys.bootstrap });
  return data.counts;
}
