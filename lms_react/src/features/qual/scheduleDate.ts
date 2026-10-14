import type { QualExamSchedule } from '../../domain/types';
import { parseYmd } from '../../utils/format';

/** 필기가 끝났어도 접수·실기·발표가 남은 회차는 유지한다. 진행 중인 기간은 오늘로 정렬한다. */
export function nextScheduleDay(exam: QualExamSchedule, now = new Date()): Date | null {
  const today = new Date(now);
  today.setHours(0, 0, 0, 0);
  const periods = [
    [exam.docRegStartDt, exam.docRegEndDt],
    [exam.docExamStartDt, exam.docExamEndDt],
    [exam.docPassDt, exam.docPassDt],
    [exam.pracRegStartDt, exam.pracRegEndDt],
    [exam.pracExamStartDt, exam.pracExamEndDt],
    [exam.pracPassDt, exam.pracPassDt],
  ];
  const dates = periods.flatMap(([from, to]) => {
    const start = parseYmd(from);
    const end = parseYmd(to) ?? start;
    if (!end || end < today) return [];
    return [Math.max((start ?? end).getTime(), today.getTime())];
  });
  return dates.length ? new Date(Math.min(...dates)) : null;
}
