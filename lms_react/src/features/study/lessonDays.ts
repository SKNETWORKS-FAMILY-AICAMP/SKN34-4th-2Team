import type { PracticeSet, StudyNote } from '../../domain/types';
import { isReadyNote, noteDate } from './noteScope';

export { noteDate, noteLabel } from './noteScope';

/**
 * 공부방의 수업 날짜 — 그날 노트와 그날 복습 문제를 한 칸에 묶는다.
 *
 * 둘 다 같은 수업 저장소 파일로 만들고 단위도 수업 날짜라서, 학생이 날짜 하나로 찾게 한다.
 * 노트는 범위를 날짜로 고른 것(scope_type 'date')만 날짜에 붙는다. 폴더·파일 범위 노트는 따로 둔다.
 */
export interface LessonDay {
  /** 'YYYY-MM-DD' */
  date: string;
  set?: PracticeSet;
  note?: StudyNote;
}

/** 최근 수업부터. 같은 날 노트가 여럿이면 가장 최근에 만든 것 */
export function lessonDays(sets: PracticeSet[], notes: StudyNote[]): LessonDay[] {
  const days = new Map<string, LessonDay>();
  const day = (date: string) => {
    let d = days.get(date);
    if (!d) days.set(date, (d = { date }));
    return d;
  };
  for (const s of sets) day(s.lessonDate).set = s;
  for (const n of notes) {
    const date = noteDate(n);
    // 정리 중 · 실패한 노트는 수업 카드에 붙이지 않는다 — 노트 화면에서 상태를 본다
    if (!date || !isReadyNote(n)) continue;
    const d = day(date);
    const older = d.note && (d.note.createdAt?.getTime() ?? 0) > (n.createdAt?.getTime() ?? 0);
    if (!older) d.note = n;
  }
  return [...days.values()].sort((a, b) => b.date.localeCompare(a.date));
}

/** 날짜와 상관없는 노트 — 폴더·파일로 범위를 고른 것. 다 만든 것만 */
export function looseNotes(notes: StudyNote[]): StudyNote[] {
  return notes.filter((n) => noteDate(n) === null && isReadyNote(n));
}
