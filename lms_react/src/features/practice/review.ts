import type { PracticeAttempt, PracticeKind, PracticeSet } from '../../domain/types';

/**
 * 「오늘 복습」 판단 — 화면과 떨어진 순수 함수.
 *
 * 날짜는 모두 'YYYY-MM-DD' 문자열로 받는다(dateKeyOf 와 같은 모양). 문자열 비교가 곧 날짜 비교다.
 */

/** 오늘 수업 세트가 없을 때 거슬러 올라가 볼 날 수. 이보다 오래된 수업은 「오늘 복습」에 올리지 않는다 */
export const RECENT_DAYS = 14;

/** 문제 종류별 대략의 풀이 시간(분) — 카드의 「약 N분」 */
const MINUTES: Record<PracticeKind, number> = {
  concept: 1,
  code_output: 1.5,
  code_blank: 2,
  code_fix: 2.5,
  code_write: 3,
};

export function estimateMinutes(set: PracticeSet): number {
  const total = set.problems.reduce((sum, p) => sum + MINUTES[p.kind], 0);
  return Math.max(5, Math.round(total / 5) * 5);
}

export function daysBetween(from: string, to: string): number {
  const a = Date.UTC(+from.slice(0, 4), +from.slice(5, 7) - 1, +from.slice(8, 10));
  const b = Date.UTC(+to.slice(0, 4), +to.slice(5, 7) - 1, +to.slice(8, 10));
  return Math.round((b - a) / 86_400_000);
}

export type ReviewState = 'new' | 'partial' | 'done';

export interface TodayReview {
  set: PracticeSet;
  /** 오늘 수업이면 0 */
  daysAgo: number;
  state: ReviewState;
  passed: number;
  total: number;
  minutes: number;
  /** 앞 수업에서 이어진 내용이면 그 수업 */
  continuesFrom: { date: string; files: string[] } | null;
}

/**
 * 오늘 보여 줄 복습 세트를 고른다.
 * 오늘 수업 세트가 있으면 그것, 없으면 최근 RECENT_DAYS 안의 가장 최근 수업. 둘 다 없으면 null.
 * 미래 날짜 세트는 보지 않는다.
 */
export function pickTodayReview(sets: PracticeSet[], attempts: PracticeAttempt[], today: string): TodayReview | null {
  const past = sets
    .filter((s) => s.lessonDate <= today && daysBetween(s.lessonDate, today) <= RECENT_DAYS)
    .sort((a, b) => b.lessonDate.localeCompare(a.lessonDate));
  const set = past[0];
  if (!set) return null;

  const mine = attempts.filter((a) => a.setId === set.id);
  const passed = mine.filter((a) => a.passed).length;
  const total = set.problems.length;
  return {
    set,
    daysAgo: daysBetween(set.lessonDate, today),
    state: passed >= total ? 'done' : mine.length ? 'partial' : 'new',
    passed,
    total,
    minutes: estimateMinutes(set),
    continuesFrom: continuationOf(set, sets),
  };
}

/**
 * 바로 앞 수업과 같은 수업 파일을 다뤘으면 「이어진 수업」이다.
 * 수업이 중간에 끝나 다음 날 이어서 하면 같은 노트북 파일이 이틀 연속 바뀐다.
 */
export function continuationOf(set: PracticeSet, sets: PracticeSet[]): TodayReview['continuesFrom'] {
  const prev = sets
    .filter((s) => s.cohortId === set.cohortId && s.lessonDate < set.lessonDate)
    .sort((a, b) => b.lessonDate.localeCompare(a.lessonDate))[0];
  if (!prev) return null;
  const shared = set.files.filter((f) => prev.files.includes(f));
  return shared.length ? { date: prev.lessonDate, files: shared } : null;
}

/** 'day15/02_video_rag_frame_extraction.ipynb' → 'video rag frame extraction' */
export function lessonFileLabel(path: string): string {
  const name = path.split('/').pop() ?? path;
  return name
    .replace(/\.(ipynb|py|md)$/i, '')
    .replace(/^\d+[_-]/, '')
    .replace(/[_-]+/g, ' ')
    .trim();
}

/** '2026-09-15' → '9/15' */
export function shortDate(date: string): string {
  return `${+date.slice(5, 7)}/${+date.slice(8, 10)}`;
}
