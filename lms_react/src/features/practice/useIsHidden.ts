import { usePracticeReports, usePracticeReviews } from '../../data/repository';
import { isHidden } from './reports';

/** 신고·강사 결정으로 숨긴 문제인지 묻는 함수 — 대시보드·학습실이 다시 풀 목록에서 빼는 데 쓴다 */
export function useIsHidden(): (setId: string, index: number) => boolean {
  const reports = usePracticeReports();
  const reviews = usePracticeReviews();
  return (setId, index) => isHidden(reports, reviews, setId, index);
}
