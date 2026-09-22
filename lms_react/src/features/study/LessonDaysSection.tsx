import { Link } from 'react-router-dom';

import { RoutePaths, studyRoomNoteSourcePath } from '../../app/routePaths';
import { useMyPracticeAttempts, usePracticeSets, useStudyNotes, useStudySources } from '../../data/repository';
import type { PracticeAttempt, PracticeSet } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { KIND_LABEL } from '../practice/practiceLabels';
import { RETRY_SET_ID, retryDates, retryItems, retryTopics } from '../practice/review';
import { useIsHidden } from '../practice/useIsHidden';
import { lessonDays, type LessonDay } from './lessonDays';

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

/**
 * 공부방의 수업별 복습 — 날짜 카드마다 그날 노트와 그날 복습 문제.
 * 맨 앞에는 날짜와 상관없이 틀린 문제를 모은 「다시 풀 문제」.
 */
export function LessonDaysSection({ cohortId, uid }: { cohortId: string; uid: string }) {
  const sets = usePracticeSets(cohortId);
  const notes = useStudyNotes();
  const sources = useStudySources();
  const attempts = useMyPracticeAttempts(uid);
  const isHidden = useIsHidden();
  const retries = retryItems(sets, attempts).filter((i) => !isHidden(i.set.id, i.index));
  const days = lessonDays(sets, notes);
  const sourceId = sources[0]?.id;

  if (days.length === 0 && retries.length === 0) return null;

  return (
    <section className="practice-sets">
      <header className="study-section__head">
        <h2 className="study-section__title">수업별 복습</h2>
      </header>
      <p className="study-section__desc">수업 날짜마다 노트로 다시 읽고, 복습 문제로 확인해요. 문제는 연습장에서 바로 실행하고 채점합니다.</p>
      <div className="practice-sets__list">
        {retries.length > 0 && (
          <Link className="practice-set practice-set--retry" to={`${RoutePaths.studyRoomPlayground}?set=${RETRY_SET_ID}`}>
            <span className="practice-set__date">틀린 문제 모음 · {retryDates(retries)} 수업</span>
            <strong className="practice-set__title">다시 풀 문제 {retries.length}개</strong>
            <span className="practice-set__kinds">{retryTopics(retries, 3)}</span>
            <span className="practice-set__foot">
              다시 풀기
              <Icon name="arrow_forward" size={16} />
            </span>
          </Link>
        )}
        {days.map((d) => (
          <LessonDayCard key={d.date} day={d} attempts={attempts} isHidden={isHidden} sourceId={sourceId} />
        ))}
      </div>
    </section>
  );
}

function LessonDayCard({
  day,
  attempts,
  isHidden,
  sourceId,
}: {
  day: LessonDay;
  attempts: PracticeAttempt[];
  isHidden: (setId: string, i: number) => boolean;
  sourceId: string | undefined;
}) {
  const { date, set, note } = day;
  const progress = set ? setProgress(set, attempts, isHidden) : null;
  const kinds = set ? [...new Set(set.problems.map((p) => KIND_LABEL[p.kind]))] : [];
  const notePath = note
    ? `${studyRoomNoteSourcePath(note.sourceId)}?note=${encodeURIComponent(note.id)}`
    : sourceId
      ? `${studyRoomNoteSourcePath(sourceId)}?date=${date}`
      : null;

  return (
    <article className="practice-set lesson-day">
      <span className="practice-set__date">
        {dayText(date)}
        {set?.dayLabel ? ` · ${set.dayLabel}` : ''}
      </span>
      <strong className="practice-set__title">{set?.title ?? '복습 문제 준비 중'}</strong>
      <span className="practice-set__kinds">{set ? kinds.join(' · ') : '이 날 수업 코드로 문제가 만들어지면 여기에 붙어요.'}</span>
      {progress && (
        <span className="practice-set__bar" aria-hidden>
          {progress.visible.map((i) => {
            const a = progress.mine.find((x) => x.index === i);
            return <i key={i} className={a?.passed ? 'ok' : a ? 'no' : ''} />;
          })}
        </span>
      )}
      <div className="lesson-day__actions">
        {notePath && (
          <Link className={`lesson-day__link${note ? '' : ' lesson-day__link--quiet'}`} to={notePath}>
            <Icon name={note ? 'description' : 'note_add'} size={16} />
            {note ? '노트' : '노트 만들기'}
          </Link>
        )}
        {set && progress && (
          <Link className="lesson-day__link lesson-day__link--main" to={practicePath(set.id)}>
            {progress.passed === progress.total && progress.total > 0
              ? '모두 통과'
              : progress.mine.length
                ? `통과 ${progress.passed} / ${progress.total}`
                : `문제 ${progress.total}개 풀기`}
            <Icon name="arrow_forward" size={16} />
          </Link>
        )}
      </div>
    </article>
  );
}
