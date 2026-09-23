import { Link } from 'react-router-dom';

import { RoutePaths, studyRoomNoteSourcePath } from '../../app/routePaths';
import { useMyPracticeAttempts, usePracticeSets, useStudyNotes, useStudySources } from '../../data/repository';
import type { PracticeAttempt, PracticeSet } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { RETRY_SET_ID, retryDates, retryItems, retryTopics } from '../practice/review';
import { useIsHidden } from '../practice/useIsHidden';
import { reviewBoard, type Subject, type SubjectDay } from './lessonDays';
import { noteLabel } from './noteScope';

const WEEKDAY = ['일', '월', '화', '수', '목', '금', '토'];

/** '2026-09-15' → '09/15 (화)' */
function dayText(date: string): string {
  const d = new Date(`${date}T00:00:00`);
  return `${date.slice(5).replace('-', '/')} (${WEEKDAY[d.getDay()]})`;
}

/** 복습 문제 링크 */
export function practicePath(setId: string): string {
  return `${RoutePaths.studyRoomPlayground}?set=${encodeURIComponent(setId)}`;
}

/** 이 세트에서 내 통과 상태 — 숨긴 문제는 뺀다 */
export function setProgress(set: PracticeSet, attempts: PracticeAttempt[], hidden: (setId: string, i: number) => boolean) {
  const visible = set.problems.map((_, i) => i).filter((i) => !hidden(set.id, i));
  const mine = attempts.filter((a) => a.setId === set.id);
  const passed = visible.filter((i) => mine.find((a) => a.index === i)?.passed).length;
  return { visible, mine, passed, total: visible.length };
}

type Progress = ReturnType<typeof setProgress>;

/** 문제 버튼 글자 — 안 풀었으면 풀기, 풀던 중이면 이어서, 다 맞았으면 다시 보기 */
function actionText(p: Progress): string {
  if (p.total > 0 && p.passed === p.total) return '다시 보기';
  return p.mine.length ? '이어서 풀기' : `${p.total}문제 풀기`;
}

/** 그날 노트 — 있으면 열고, 없으면 그 과목 저장소에서 그날로 만들기 */
function notePath(subject: Subject, day: SubjectDay): string | null {
  if (day.note) return `${studyRoomNoteSourcePath(day.note.sourceId)}?note=${encodeURIComponent(day.note.id)}`;
  return subject.source ? `${studyRoomNoteSourcePath(subject.source.id)}?date=${day.date}` : null;
}

/**
 * 공부방 — 맨 위에 가장 최근 수업의 복습 하나, 그 아래 틀린 문제, 그리고 과목(수업 저장소)별 목록.
 *
 * 복습 문제는 강사가 저장소에 올린 수업으로 매일 18:30 에 자동으로 생기고, 노트는 학생이 필요할 때 만든다.
 * 둘은 따로다 — 노트가 없어도 문제는 보인다.
 */
export function LessonDaysSection({ cohortId, uid }: { cohortId: string; uid: string }) {
  const sets = usePracticeSets(cohortId);
  const notes = useStudyNotes();
  const sources = useStudySources().filter((s) => s.isActive);
  const attempts = useMyPracticeAttempts(uid);
  const isHidden = useIsHidden();
  const retries = retryItems(sets, attempts).filter((i) => !isHidden(i.set.id, i.index));
  const board = reviewBoard(sources, sets, notes);
  const progressOf = (set: PracticeSet) => setProgress(set, attempts, isHidden);

  return (
    <section className="review-board">
      {board.latest ? (
        <TodayHero subject={board.latest.subject} day={board.latest.day} progress={progressOf(board.latest.day.set!)} />
      ) : (
        <div className="review-hero review-hero--empty">
          <Icon name="schedule" size={22} />
          <div>
            <strong>아직 복습 문제가 없어요</strong>
            <p className="hint">강사님이 수업 저장소에 올린 내용으로 매일 18:30 에 만들어져요. 노트는 아래 과목에서 지금 만들 수 있어요.</p>
          </div>
        </div>
      )}

      {retries.length > 0 && (
        <Link className="review-retry" to={`${RoutePaths.studyRoomPlayground}?set=${RETRY_SET_ID}`}>
          <Icon name="replay" size={18} />
          <strong>다시 풀 문제 {retries.length}개</strong>
          <span className="review-retry__meta">
            {retryDates(retries)} 수업 · {retryTopics(retries, 3)}
          </span>
          <span className="review-retry__go">
            다시 풀기
            <Icon name="arrow_forward" size={16} />
          </span>
        </Link>
      )}

      <header className="study-section__head">
        <h2 className="study-section__title">과목별 복습</h2>
      </header>
      <p className="study-section__desc">과목을 펼치면 수업 날짜마다 복습 문제와 노트가 있어요. 노트는 날짜 · 폴더 · 파일로 골라 만들 수 있어요.</p>
      <div className="review-subjects">
        {board.subjects.map((subject) => (
          <SubjectRow
            key={subject.key}
            subject={subject}
            open={subject.key === board.latest?.subject.key}
            progressOf={progressOf}
          />
        ))}
      </div>
    </section>
  );
}

function TodayHero({ subject, day, progress }: { subject: Subject; day: SubjectDay; progress: Progress }) {
  const set = day.set!;
  const note = notePath(subject, day);
  const done = progress.total > 0 && progress.passed === progress.total;
  return (
    <article className={`review-hero${done ? ' review-hero--done' : ''}`}>
      <div className="review-hero__body">
        <span className="review-hero__eyebrow">
          <Icon name="today" size={16} />
          오늘 복습 · {dayText(day.date)} · {set.dayLabel || subject.title}
        </span>
        <strong className="review-hero__title">{set.title || `${subject.title} 수업`}</strong>
        <div className="review-hero__progress">
          <ProgressBar progress={progress} />
          <span>
            통과 <strong>{progress.passed}</strong> / {progress.total}
          </span>
        </div>
      </div>
      <div className="review-hero__actions">
        <Link className="btn btn--filled btn--md" to={practicePath(set.id)}>
          {actionText(progress)}
          <Icon name="arrow_forward" size={18} />
        </Link>
        {note && (
          <Link className="btn btn--text btn--sm" to={note}>
            <Icon name={day.note ? 'description' : 'note_add'} size={16} />
            {day.note ? '그날 노트' : '노트 만들기'}
          </Link>
        )}
      </div>
    </article>
  );
}

function ProgressBar({ progress }: { progress: Progress }) {
  const pct = progress.total ? Math.round((progress.passed / progress.total) * 100) : 0;
  const tried = progress.visible.filter((i) => progress.mine.some((a) => a.index === i)).length;
  const triedPct = progress.total ? Math.round((tried / progress.total) * 100) : 0;
  return (
    <span className="review-bar" role="img" aria-label={`통과 ${progress.passed} / ${progress.total}`}>
      <i className="review-bar__tried" style={{ width: `${triedPct}%` }} />
      <i className="review-bar__passed" style={{ width: `${pct}%` }} />
    </span>
  );
}

function SubjectRow({
  subject,
  open,
  progressOf,
}: {
  subject: Subject;
  open: boolean;
  progressOf: (set: PracticeSet) => Progress;
}) {
  const withSets = subject.days.filter((d) => d.set);
  const totals = withSets.reduce(
    (acc, d) => {
      const p = progressOf(d.set!);
      return { passed: acc.passed + p.passed, total: acc.total + p.total };
    },
    { passed: 0, total: 0 },
  );
  const first = subject.days.at(-1)?.date;
  const last = subject.days[0]?.date;
  const period = first && last ? (first === last ? dayText(first) : `${first.slice(5).replace('-', '/')} – ${last.slice(5).replace('-', '/')}`) : '';

  return (
    <details className="review-subject" open={open}>
      <summary>
        <Icon name="chevron_right" size={18} className="review-subject__chevron" />
        <strong>{subject.title}</strong>
        <span className="review-subject__meta">
          {subject.days.length ? `${period} · ${subject.days.length}일` : '복습 자료 아직 없음'}
        </span>
        <span className="spacer" />
        {totals.total > 0 && (
          <span className={`review-subject__score${totals.passed === totals.total ? ' review-subject__score--done' : ''}`}>
            통과 {totals.passed} / {totals.total}
          </span>
        )}
      </summary>

      <ul className="review-days">
        {subject.days.map((day) => {
          const p = day.set ? progressOf(day.set) : null;
          const note = notePath(subject, day);
          return (
            <li key={day.date} className="review-day">
              <span className="review-day__date">{dayText(day.date)}</span>
              <span className="review-day__title">
                {day.set ? day.set.title || day.set.dayLabel : day.note ? noteLabel(day.note) : ''}
                {!day.set && <span className="hint"> · 복습 문제 없음</span>}
              </span>
              {p && (
                <span className="review-day__progress">
                  <ProgressBar progress={p} />
                  <span>
                    {p.passed}/{p.total}
                  </span>
                </span>
              )}
              <span className="review-day__actions">
                {day.set && p && (
                  <Link className="btn btn--outline btn--sm" to={practicePath(day.set.id)}>
                    {actionText(p)}
                  </Link>
                )}
                {note && (
                  <Link className="btn btn--text btn--sm" to={note}>
                    {day.note ? '노트' : '노트 만들기'}
                  </Link>
                )}
              </span>
            </li>
          );
        })}
      </ul>

      {(subject.looseNotes.length > 0 || subject.source) && (
        <div className="review-subject__foot">
          {subject.looseNotes.map((n) => (
            <Link
              key={n.id}
              className="chip"
              to={`${studyRoomNoteSourcePath(n.sourceId)}?note=${encodeURIComponent(n.id)}`}
            >
              <Icon name="description" size={15} />
              {noteLabel(n)}
            </Link>
          ))}
          <span className="spacer" />
          {subject.source && (
            <Link className="btn btn--text btn--sm" to={studyRoomNoteSourcePath(subject.source.id)}>
              <Icon name="note_add" size={16} />
              이 과목 노트 만들기
            </Link>
          )}
        </div>
      )}
    </details>
  );
}
