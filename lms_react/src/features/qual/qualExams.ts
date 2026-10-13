import type { QualExamSchedule } from '../../domain/types';
import { parseYmd } from '../../utils/format';

export interface QualStage {
  label: string;
  from?: string;
  to?: string;
  extra?: [string, string][];
}

/** 종목 이름 — 등급 단위로 받던 옛 캐시는 「국가기술자격」만 있다 */
export const examName = (e: QualExamSchedule) => e.jmNm ?? e.qualgbNm;

export function stagesOf(e: QualExamSchedule): QualStage[] {
  return [
    { label: '필기 접수', from: e.docRegStartDt, to: e.docRegEndDt, extra: e.docRegExtra },
    { label: '필기 시험', from: e.docExamStartDt, to: e.docExamEndDt },
    { label: '필기 발표', from: e.docPassDt, to: e.docPassDt },
    { label: '실기 접수', from: e.pracRegStartDt, to: e.pracRegEndDt, extra: e.pracRegExtra },
    { label: '실기 시험', from: e.pracExamStartDt, to: e.pracExamEndDt },
    { label: '실기 발표', from: e.pracPassDt, to: e.pracPassDt },
  ].filter((s) => s.from !== undefined);
}

/** 단계가 끝나는 날 — 추가 접수가 있으면 그 끝까지 */
function stageEnd(stage: QualStage): Date | null {
  const ends = [stage.to ?? stage.from, ...(stage.extra ?? []).map(([, to]) => to)]
    .map((d) => parseYmd(d))
    .filter((d): d is Date => d !== null);
  return ends.length ? new Date(Math.max(...ends.map((d) => d.getTime()))) : null;
}

export function startOfToday(): Date {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return today;
}

export interface NextStage {
  stage: QualStage;
  /** 오늘 진행 중이면 0, 아니면 시작까지 남은 날 */
  days: number;
}

/** 아직 끝나지 않은 첫 단계. 다 끝났으면 null */
export function nextStageOf(e: QualExamSchedule, today: Date = startOfToday()): NextStage | null {
  for (const stage of stagesOf(e)) {
    const end = stageEnd(stage);
    if (end === null || end.getTime() < today.getTime()) continue;
    const start = parseYmd(stage.from);
    const days = start === null ? 0 : Math.max(0, Math.round((start.getTime() - today.getTime()) / 86_400_000));
    return { stage, days };
  }
  return null;
}

export function stageStatus(stage: QualStage, today: Date = startOfToday()): 'done' | 'now' | 'later' {
  const start = parseYmd(stage.from);
  const end = stageEnd(stage);
  if (end !== null && end.getTime() < today.getTime()) return 'done';
  if (start !== null && start.getTime() <= today.getTime()) return 'now';
  return 'later';
}

export function nextStageLabel(next: NextStage): string {
  return next.days === 0 ? `${next.stage.label} 중` : `${next.stage.label} D-${next.days}`;
}

/** 남은 단계가 있는 회차를 다음 단계 날짜순으로 */
export function upcomingExams(exams: QualExamSchedule[], today: Date = startOfToday()) {
  return exams
    .map((exam) => ({ exam, next: nextStageOf(exam, today) }))
    .filter((row): row is { exam: QualExamSchedule; next: NextStage } => row.next !== null)
    .sort(
      (a, b) =>
        (parseYmd(a.next.stage.from)?.getTime() ?? 0) - (parseYmd(b.next.stage.from)?.getTime() ?? 0),
    );
}

/** 종목 이름 — 서버가 보낸 순서(정보처리기사가 맨 앞) 그대로 */
export function subjectsOf(exams: QualExamSchedule[]): string[] {
  return [...new Set(exams.map(examName))];
}

export const roundLabel = (e: QualExamSchedule) =>
  e.implSeq > 0 ? `${e.implYy}년 ${e.implSeq}회` : `${e.implYy}년`;
