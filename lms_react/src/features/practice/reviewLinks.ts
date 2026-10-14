import { noteDate } from '../study/noteScope';
import type { AssessmentQuestion, CurriculumRow, PracticeSet, StudyNote } from '../../domain/types';

/**
 * 성취도평가에서 틀린 문항 → 그 내용을 배운 수업 → 그날 노트와 복습 문제.
 *
 * 문항의 근거 일수(sourceDay) → 커리큘럼 행(dayIndex) → 수업일자(dateLabel) → 그 날짜의 복습 세트 · 노트.
 * 커리큘럼 「수업일자」가 실제 날짜여야 이어진다. 「15일차」처럼 날짜가 없으면 주제(sourceTopic)로 세트를 찾아 본다.
 * 화면과 떨어진 순수 함수 — 데이터가 데모에서 오든 DB 에서 오든 같다.
 */

/** '2026년 9월 15일' · '2026-09-15' · '2026.9.15' · '9/15'(연도는 hint) → 'YYYY-MM-DD'. 못 읽으면 null */
export function parseLessonDate(label: string, yearHint?: number): string | null {
  const s = label.trim();
  let m = /(\d{4})\s*[년.\-/]\s*(\d{1,2})\s*[월.\-/]\s*(\d{1,2})/.exec(s);
  if (m) return ymd(+m[1], +m[2], +m[3]);
  m = /^(\d{1,2})\s*[/.월]\s*(\d{1,2})\s*일?/.exec(s);
  if (m && yearHint) return ymd(yearHint, +m[1], +m[2]);
  return null;
}

function ymd(y: number, mo: number, d: number): string | null {
  if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  return `${y}-${String(mo).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

export interface LessonLink {
  /** 커리큘럼 일수. 문항에 근거 일수가 없으면 null */
  day: number | null;
  /** 'YYYY-MM-DD' — 커리큘럼에서 못 찾으면 null */
  date: string | null;
  /** 커리큘럼 행의 교과목 · 내용 (예: '멀티모달 · 영상 RAG') */
  label: string;
  /** 이 수업에서 틀린 문항들 */
  questions: AssessmentQuestion[];
  /** 그 날짜의 복습 세트 (없으면 주제로 찾은 것) */
  set: PracticeSet | null;
  /** 그날 노트 — 날짜 범위 노트(scope_type 'date')이거나 files 에 그 날짜가 든 것 */
  notes: StudyNote[];
}

/**
 * 틀린 문항을 수업별로 묶는다. 근거 일수가 같은 문항은 한 묶음이다.
 * 반환 순서: 틀린 문항이 많은 수업부터.
 */
export function buildReviewLinks(input: {
  wrong: AssessmentQuestion[];
  rows: CurriculumRow[];
  sets: PracticeSet[];
  notes: StudyNote[];
  yearHint?: number;
}): LessonLink[] {
  const { wrong, rows, sets, notes, yearHint } = input;
  const byDay = new Map<number | null, AssessmentQuestion[]>();
  for (const q of wrong) {
    const key = typeof q.sourceDay === 'number' ? q.sourceDay : null;
    byDay.set(key, [...(byDay.get(key) ?? []), q]);
  }
  const links: LessonLink[] = [];
  for (const [day, questions] of byDay) {
    const row = day === null ? undefined : rows.find((r) => r.dayIndex === day);
    const date = row ? parseLessonDate(row.dateLabel, yearHint) : null;
    const topic = questions.find((q) => q.sourceTopic)?.sourceTopic ?? row?.topic ?? '';
    const set =
      (date && sets.find((s) => s.lessonDate === date)) ||
      (topic ? sets.find((s) => matchesTopic(s, topic)) : undefined) ||
      null;
    links.push({
      day,
      date: date ?? set?.lessonDate ?? null,
      label: row ? `${row.subject} · ${row.detail || row.topic}` : topic || '근거 수업 없음',
      questions,
      set,
      notes: date ? notes.filter((n) => noteIsForDate(n, date)) : [],
    });
  }
  return links.sort((a, b) => b.questions.length - a.questions.length || (a.day ?? 1e9) - (b.day ?? 1e9));
}

/** 세트 제목·주제·문제 주제에 낱말이 들어 있으면 같은 내용으로 본다 */
function matchesTopic(set: PracticeSet, topic: string): boolean {
  const words = topic.toLowerCase().split(/[\s·,/]+/).filter((w) => w.length >= 2);
  const hay = `${set.title} ${set.dayLabel} ${set.problems.map((p) => p.topic).join(' ')}`.toLowerCase();
  return words.some((w) => hay.includes(w));
}

function noteIsForDate(note: StudyNote, date: string): boolean {
  if (noteDate(note) === date) return true;
  return note.files.some((f) => f.path.includes(date) || f.path.includes(date.replace(/-/g, '')));
}

/** 문항 하나가 이어지는 복습 문제 — 세트에서 같은 주제 낱말이 든 문제, 없으면 세트 전체 */
export function relatedProblemIndexes(link: LessonLink, question: AssessmentQuestion): number[] {
  if (!link.set) return [];
  const topic = (question.sourceTopic ?? '').toLowerCase();
  const words = topic.split(/[\s·,/]+/).filter((w) => w.length >= 2);
  const hits = link.set.problems
    .map((p, i) => (words.some((w) => `${p.topic} ${p.prompt}`.toLowerCase().includes(w)) ? i : -1))
    .filter((i) => i >= 0);
  return hits;
}
