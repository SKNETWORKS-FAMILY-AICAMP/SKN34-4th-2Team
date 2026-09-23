import type { PracticeSet, StudyNote, StudySource } from '../../domain/types';
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

// ── 공부방 — 오늘 복습 + 과목별 목록 ─────────────────────────
// 과목 = 수업 저장소 하나. 과목이 차례로 진행돼서(34기 56일 중 두 과목이 겹친 날은 하루) 날짜는 과목 안에 둔다.

export interface SubjectDay {
  date: string;
  set?: PracticeSet;
  note?: StudyNote;
}

export interface Subject {
  /** 저장소가 있으면 그 id, 없으면(저장소 없이 들어온 세트) 'set:<이름>' */
  key: string;
  source?: StudySource;
  title: string;
  /** 최근 수업부터 */
  days: SubjectDay[];
  /** 폴더 · 파일로 범위를 고른 노트 */
  looseNotes: StudyNote[];
}

export interface ReviewBoard {
  /** 수업이 있는 과목(최근 수업이 늦은 과목부터), 그다음 아직 복습 자료가 없는 과목 */
  subjects: Subject[];
  /** 맨 위 「오늘 복습」 — 문제가 있는 가장 최근 수업 */
  latest?: { subject: Subject; day: SubjectDay };
}

/** 세트 · 출제 기록이 쓰는 저장소 이름 — 주소 끝(소문자). 서버 practice_auto._repo_name 과 같다 */
export function repoName(url: string): string {
  return url.replace(/\/+$/, '').replace(/\.git$/, '').split('/').pop()!.toLowerCase();
}

function belongs(set: PracticeSet, source: StudySource): boolean {
  const name = set.sourceTitle.toLowerCase();
  return name === repoName(source.repoUrl) || name === source.title.toLowerCase();
}

export function reviewBoard(sources: StudySource[], sets: PracticeSet[], notes: StudyNote[]): ReviewBoard {
  const ready = notes.filter(isReadyNote);
  const subjects: Subject[] = sources.map((source) => ({
    key: source.id,
    source,
    title: source.title,
    days: [],
    looseNotes: ready.filter((n) => n.sourceId === source.id && noteDate(n) === null),
  }));
  const dayOf = (subject: Subject, date: string) => {
    let d = subject.days.find((x) => x.date === date);
    if (!d) subject.days.push((d = { date }));
    return d;
  };
  for (const set of sets) {
    let subject = subjects.find((s) => s.source && belongs(set, s.source));
    if (!subject) {
      // 저장소 목록에 없는 세트(숨긴 저장소 · 손으로 넣은 세트)도 버리지 않는다
      const key = `set:${set.sourceTitle}`;
      subject = subjects.find((s) => s.key === key);
      if (!subject) subjects.push((subject = { key, title: set.sourceTitle || '기타', days: [], looseNotes: [] }));
    }
    dayOf(subject, set.lessonDate).set = set;
  }
  for (const note of ready) {
    const date = noteDate(note);
    const subject = subjects.find((s) => s.source?.id === note.sourceId);
    if (!date || !subject) continue;
    const d = dayOf(subject, date);
    const older = d.note && (d.note.createdAt?.getTime() ?? 0) > (note.createdAt?.getTime() ?? 0);
    if (!older) d.note = note;
  }
  for (const s of subjects) s.days.sort((a, b) => b.date.localeCompare(a.date));
  const last = (s: Subject) => s.days[0]?.date ?? '';
  const withDays = subjects.filter((s) => s.days.length).sort((a, b) => last(b).localeCompare(last(a)));
  const empty = subjects.filter((s) => !s.days.length);

  let latest: ReviewBoard['latest'];
  for (const subject of withDays) {
    const day = subject.days.find((d) => d.set);
    if (day && (!latest || day.date > latest.day.date)) latest = { subject, day };
  }
  return { subjects: [...withDays, ...empty], latest };
}

