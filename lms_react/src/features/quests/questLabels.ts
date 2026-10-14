import type { Quest, QuestApproval, QuestEvidenceType, QuestSubmissionStatus } from '../../domain/types';

export const EVIDENCE_LABEL: Record<QuestEvidenceType, string> = {
  none: '인증 없음',
  text: '글',
  link: '링크',
  file: '사진 · 파일',
};

export const APPROVAL_LABEL: Record<QuestApproval, string> = {
  manual: '관리자 승인 후 지급',
  auto: '제출 즉시 지급',
};

export const STATUS_LABEL: Record<QuestSubmissionStatus, string> = {
  pending: '검토 중',
  approved: '완료',
  rejected: '반려',
  revoked: '승인 취소',
};

export const STATUS_TONE: Record<QuestSubmissionStatus, 'warning' | 'success' | 'error' | 'neutral'> = {
  pending: 'warning',
  approved: 'success',
  rejected: 'error',
  revoked: 'neutral',
};

export function periodLabel(q: Pick<Quest, 'startOn' | 'endOn'>): string {
  if (q.startOn === null && q.endOn === null) return '기간 제한 없음';
  return `${q.startOn ?? '지금'} ~ ${q.endOn ?? '마감 없음'}`;
}
