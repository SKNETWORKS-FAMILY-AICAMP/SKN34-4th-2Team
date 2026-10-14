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
  code_scratch: 5,
  sql_query: 3,
  web_task: 3,
};

/** 수업 세트인지 — 학생이 만든 세트(note · file)는 「오늘 복습」 · 과목 목록에 넣지 않고 「내가 만든 문제」로 따로 */
export function isLessonSet(set: PracticeSet): boolean {
  return (set.origin ?? 'lesson') === 'lesson';
}

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

// ── 다시 풀 문제 ─────────────────────────────────────────

export interface RetryItem {
  set: PracticeSet;
  index: number;
  tries: number;
  /** 마지막으로 틀린 날 'YYYY-MM-DD' */
  lastTried: string;
}

/** 풀었지만 아직 통과 못 한 문제. 최근 수업 것부터, 같은 날이면 문제 순서대로. */
export function retryItems(sets: PracticeSet[], attempts: PracticeAttempt[]): RetryItem[] {
  const byId = new Map(sets.map((s) => [s.id, s]));
  return attempts
    .filter((a) => !a.passed && byId.get(a.setId)?.problems[a.index])
    .map((a) => ({ set: byId.get(a.setId)!, index: a.index, tries: a.tries, lastTried: dateKey(a.answeredAt) }))
    .sort((x, y) => y.set.lessonDate.localeCompare(x.set.lessonDate) || x.index - y.index);
}

/**
 * 오늘 다시 볼 문제 — 틀린 날이 오늘보다 앞선 것만.
 * 방금 틀린 문제를 바로 다시 풀면 기억으로 맞힌다. 하루 두고 본다.
 */
export function dueRetries(items: RetryItem[], today: string): RetryItem[] {
  return items.filter((i) => i.lastTried < today);
}

/**
 * 다시 풀 문제 세트 id — 무엇을 모으는지가 id 에 있다(연습장 주소 ?set= · 창 탭 하나).
 * - 'retry'            하루 지난 것만(대시보드 「지난번에 틀린 문제」 — 방금 틀린 걸 바로 풀면 기억으로 맞힌다)
 * - 'retry:all'        지금 못 푼 것 모두(공부방 · 오답노트 「전체 다시 풀기」)
 * - 'retry:2026-09-29' 그 수업 날짜의 못 푼 것(오답노트 「이날 다시 풀기」)
 */
export const RETRY_SET_ID = 'retry';
export const RETRY_ALL_ID = 'retry:all';

export function retryDateId(date: string): string {
  return `retry:${date}`;
}

export function isRetryId(id: string | null | undefined): boolean {
  return id === RETRY_SET_ID || Boolean(id?.startsWith('retry:'));
}

/** 그 id 가 모으는 문제 */
export function retryScope(id: string, items: RetryItem[], today: string): RetryItem[] {
  if (id === RETRY_ALL_ID) return items;
  if (id.startsWith('retry:')) return items.filter((i) => i.set.lessonDate === id.slice('retry:'.length));
  return dueRetries(items, today);
}

/** 창 탭 · 제목에 쓸 이름 */
export function retryLabel(id: string): string {
  if (id === RETRY_ALL_ID) return '오답 전체';
  if (id.startsWith('retry:')) return `${shortDate(id.slice('retry:'.length))} 오답`;
  return '다시 풀 문제';
}

/** 다시 풀 문제를 연습장이 열 수 있는 세트 하나로 묶는다. origins[i] 가 원래 세트·문제 번호다. */
export function retrySet(
  items: RetryItem[],
  today: string,
  id: string = RETRY_SET_ID,
): { set: PracticeSet; origins: { setId: string; index: number }[] } | null {
  if (items.length === 0) return null;
  const first = items[0].set;
  return {
    set: {
      id,
      cohortId: first.cohortId,
      sourceTitle: first.sourceTitle,
      lessonDate: today,
      dayLabel: retryLabel(id),
      title: `틀렸던 문제 ${items.length}개`,
      files: [...new Set(items.flatMap((i) => i.set.problems[i.index].sourceFiles))],
      model: first.model,
      problems: items.map((i) => i.set.problems[i.index]),
    },
    origins: items.map((i) => ({ setId: i.set.id, index: i.index })),
  };
}

// ── 오답노트 ─────────────────────────────────────────────

export interface WrongNoteDay {
  /** 수업 날짜 'YYYY-MM-DD' */
  date: string;
  /** 그날 세트들(수업 세트 · 내가 만든 세트) */
  sets: PracticeSet[];
  /** 아직 못 푼 문제 — 다시 풀 문제와 같은 순서 */
  wrong: RetryItem[];
  /** 틀렸다가 다시 풀어 통과한 문제 */
  solved: { set: PracticeSet; index: number; tries: number }[];
}

/**
 * 오답노트 — 틀린 적 있는 문제를 수업 날짜별로. 최근 수업부터.
 * 못 푼 것은 다시 풀 문제(retryItems)와 같다. 해결한 것은 통과했지만 한 번 넘게 낸 문제(한 번은 틀렸다).
 */
export function wrongNoteDays(
  sets: PracticeSet[],
  attempts: PracticeAttempt[],
  hidden: (setId: string, index: number) => boolean,
): WrongNoteDay[] {
  const byId = new Map(sets.map((s) => [s.id, s]));
  const days = new Map<string, WrongNoteDay>();
  const dayOf = (set: PracticeSet) => {
    const day = days.get(set.lessonDate) ?? { date: set.lessonDate, sets: [], wrong: [], solved: [] };
    if (!day.sets.includes(set)) day.sets.push(set);
    days.set(set.lessonDate, day);
    return day;
  };
  for (const item of retryItems(sets, attempts)) {
    if (!hidden(item.set.id, item.index)) dayOf(item.set).wrong.push(item);
  }
  for (const a of attempts) {
    const set = byId.get(a.setId);
    if (set && a.passed && a.tries > 1 && set.problems[a.index] && !hidden(a.setId, a.index)) {
      dayOf(set).solved.push({ set, index: a.index, tries: a.tries });
    }
  }
  for (const day of days.values()) day.solved.sort((x, y) => x.index - y.index);
  return [...days.values()].sort((x, y) => y.date.localeCompare(x.date));
}

function dateKey(d: Date): string {
  const p = (v: number) => String(v).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** 다시 풀 문제의 주제를 짧게 — 'A, B 외 3개' */
export function retryTopics(items: RetryItem[], max = 2): string {
  const topics = [...new Set(items.map((i) => i.set.problems[i.index].topic).filter(Boolean))];
  const shown = topics.slice(0, max).join(', ');
  return topics.length > max ? `${shown} 외 ${topics.length - max}개` : shown;
}

/** 다시 풀 문제의 수업 날짜들 — '9/14, 9/15' */
export function retryDates(items: RetryItem[]): string {
  return [...new Set(items.map((i) => shortDate(i.set.lessonDate)))].join(', ');
}
