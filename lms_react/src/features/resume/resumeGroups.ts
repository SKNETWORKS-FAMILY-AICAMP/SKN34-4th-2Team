import type { Resume, ResumeStatus } from '../../domain/types';

/**
 * 이력서 상태 · 묶음 — Flutter 원본(resume_model.dart · resume_screen.dart) 규칙 그대로.
 *
 * DB 의 status 는 Flutter 가 쓰던 값이다: writing · ready(작성 중), submitted(피드백 요청), approved · completed(승인).
 * 화면은 draft · feedbackRequested · approved 세 갈래로 본다. 받을 때 한 번 바꾸고, 저장할 때 되돌린다.
 */
export function resumeStatusFromServer(status: unknown): ResumeStatus {
  const s = String(status ?? '');
  if (s === 'submitted' || s === 'feedbackRequested') return 'feedbackRequested';
  if (s === 'approved' || s === 'completed') return 'approved';
  return 'draft';
}

export function resumeStatusToServer(status: ResumeStatus): string {
  if (status === 'feedbackRequested' || status === 'submitted') return 'submitted';
  if (status === 'approved') return 'approved';
  return 'writing';
}

/** 공고 맞춤 이력서 — 다른 이력서(원본)에서 만들어진 것 */
export function isTailored(resume: Resume): boolean {
  return Boolean(resume.baseResumeId) && !resume.isBaseResume;
}

export interface ResumeRow {
  resume: Resume;
  /** 이 이력서를 원본으로 만든 공고 맞춤 이력서 — 줄을 누르면 밑으로 펼친다 */
  children: Resume[];
}

/**
 * 「전체」 탭의 묶음.
 * - 기본 이력서에서 만든 맞춤 이력서: 기본 이력서 카드 밑.
 * - 다른 이력서에서 만든 것: 표의 그 원본 줄 밑.
 * - 원본이 지워졌거나 안 보이면: 찾을 길이 없어지므로 표에 한 줄로 남긴다.
 */
export function groupResumes(resumes: Resume[], base: Resume | undefined): { baseTailored: Resume[]; rows: ResumeRow[] } {
  const others = resumes.filter((r) => r.id !== base?.id);
  const parents = others.filter((r) => !isTailored(r));
  const parentIds = new Set(parents.map((r) => r.id));
  const baseTailored = others.filter((r) => isTailored(r) && base !== undefined && r.baseResumeId === base.id);
  const rows: ResumeRow[] = parents.map((p) => ({
    resume: p,
    children: others.filter((r) => isTailored(r) && r.baseResumeId === p.id),
  }));
  const orphans = others.filter(
    (r) => isTailored(r) && r.baseResumeId !== base?.id && !parentIds.has(r.baseResumeId ?? ''),
  );
  return { baseTailored, rows: [...rows, ...orphans.map((r) => ({ resume: r, children: [] }))] };
}
