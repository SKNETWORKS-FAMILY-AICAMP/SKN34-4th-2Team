import type { PracticeReport, PracticeReportReason, PracticeReview, PracticeSet } from '../../domain/types';

/**
 * 「이 문제 이상해요」 신고 — 숨김 판단.
 *
 * 자동 규칙만으로는 「돌아가지만 적절하지 않은」 문제를 못 걸러서, 실제로 풀어 본 학생의 신고를 그물로 쓴다.
 * 서로 다른 학생 HIDE_AT 명이 신고하면 그 문제를 숨긴다. 강사가 결정(kept · hidden)을 남기면 그것이 우선한다.
 */
export const HIDE_AT = 2;

export const REASON_LABEL: Record<PracticeReportReason, string> = {
  unclear: '문제 문장이 모호해요',
  answer: '정답이 이상해요',
  tests: '테스트가 문제 문장과 달라요',
  offtopic: '수업과 상관없는 내용이에요',
  other: '기타',
};

export function reportsFor(reports: PracticeReport[], setId: string, index: number): PracticeReport[] {
  return reports.filter((r) => r.setId === setId && r.index === index);
}

export function reviewFor(reviews: PracticeReview[], setId: string, index: number): PracticeReview | undefined {
  return reviews.find((r) => r.setId === setId && r.index === index);
}

/** 이 문제를 학생에게 숨겨야 하나 */
export function isHidden(reports: PracticeReport[], reviews: PracticeReview[], setId: string, index: number): boolean {
  const review = reviewFor(reviews, setId, index);
  if (review) return review.decision === 'hidden';
  const reporters = new Set(reportsFor(reports, setId, index).map((r) => r.uid));
  return reporters.size >= HIDE_AT;
}

export interface FlaggedProblem {
  set: PracticeSet;
  index: number;
  reports: PracticeReport[];
  reporters: number;
  hidden: boolean;
  review: PracticeReview | undefined;
}

/** 강사가 볼 목록 — 신고가 하나라도 있는 문제. 숨긴 것, 신고 많은 것부터. */
export function flaggedProblems(sets: PracticeSet[], reports: PracticeReport[], reviews: PracticeReview[]): FlaggedProblem[] {
  const keys = new Map<string, { setId: string; index: number }>();
  for (const r of reports) keys.set(`${r.setId}#${r.index}`, { setId: r.setId, index: r.index });
  const out: FlaggedProblem[] = [];
  for (const { setId, index } of keys.values()) {
    const set = sets.find((s) => s.id === setId);
    if (!set || !set.problems[index]) continue;
    const list = reportsFor(reports, setId, index);
    out.push({
      set,
      index,
      reports: list,
      reporters: new Set(list.map((r) => r.uid)).size,
      hidden: isHidden(reports, reviews, setId, index),
      review: reviewFor(reviews, setId, index),
    });
  }
  return out.sort((a, b) => Number(b.hidden) - Number(a.hidden) || b.reporters - a.reporters || b.set.lessonDate.localeCompare(a.set.lessonDate));
}
