import { useMyPracticeAttempts, usePracticeSets } from '../../data/repository';
import { todayKey } from '../../data/store';
import type { PracticeProblem } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { PracticeLink } from './PracticeDock';
import { useCurrentUser } from '../auth/session';
import { useIsHidden } from './useIsHidden';
import {
  dueRetries,
  lessonFileLabel,
  isLessonSet,
  pickTodayReview,
  RETRY_SET_ID,
  retryDates,
  retryItems,
  retryTopics,
  shortDate,
} from './review';

/**
 * 대시보드 「오늘 복습」 — 가장 최근 수업의 복습 문제로 들어가는 문.
 *
 * 오늘 수업 세트가 있으면 그것, 없으면 2주 안의 가장 최근 수업(review.ts).
 * 점수는 보이지 않는다. 학생 혼자 하는 복습이라 「통과 n / 6」만 보인다.
 */
export function TodayReviewCard() {
  const user = useCurrentUser();
  const sets = usePracticeSets(user.cohortId);
  const attempts = useMyPracticeAttempts(user.uid);
  const today = todayKey();
  // 훅은 return 앞에서 — 복습 세트가 없다가 생기면 훅 개수가 달라져 화면이 깨졌다
  const isHidden = useIsHidden();
  const review = pickTodayReview(sets.filter(isLessonSet), attempts, today);
  if (!review) return null;
  // 오늘 틀린 문제는 빼고, 하루 이상 지난 것만 다시 보여 준다
  const retries = dueRetries(retryItems(sets, attempts).filter((i) => !isHidden(i.set.id, i.index)), today);

  const { set, daysAgo, state, passed, total, minutes, continuesFrom } = review;
  const when = daysAgo === 0 ? `오늘 수업 · ${shortDate(set.lessonDate)}` : `지난 수업 · ${shortDate(set.lessonDate)} (${daysAgo}일 전)`;
  const action = state === 'done' ? '다시 보기' : state === 'partial' ? '이어서 풀기' : '복습 시작';

  return (
    <section className={`today-review today-review--${state}`} aria-label="오늘 복습">
      <div className="today-review__body">
        <div className="today-review__eyebrow">
          <Icon name="replay" size={16} />
          <strong>오늘 복습</strong>
          <span>
            {when} · {set.dayLabel}
          </span>
        </div>
        <h2 className="today-review__title">{set.title}</h2>
        {/* 진행 막대 옆에 한 줄로 — 몇 문제 · 몇 분, 풀기 시작했으면 몇 개 통과했는지 */}
        <div className="today-review__progress" aria-label={`통과 ${passed} / ${total}`}>
          <span className="today-review__bar">
            {set.problems.map((_, i) => {
              const a = attempts.find((x) => x.setId === set.id && x.index === i);
              return <i key={i} className={a?.passed ? 'ok' : a ? 'no' : ''} />;
            })}
          </span>
          <span>
            {state === 'done' ? '모두 통과했어요' : state === 'partial' ? `통과 ${passed} / ${total}` : `${total}문제`} · 약 {minutes}분
          </span>
        </div>
        {continuesFrom && (
          <p className="today-review__continue">
            <Icon name="subdirectory_arrow_right" size={15} />
            {shortDate(continuesFrom.date)} 수업에서 이어짐 · {continuedTopic(set.problems, continuesFrom.files)}
          </p>
        )}
        {retries.length > 0 && (
          <PracticeLink className="today-review__retry" setId={RETRY_SET_ID}>
            <Icon name="history" size={16} />
            지난번에 틀린 문제 {retries.length}개 · {retryTopics(retries)}
            <span className="today-review__retry-date">({retryDates(retries)})</span>
            <span className="today-review__retry-go">
              다시 풀기
              <Icon name="chevron_right" size={16} />
            </span>
          </PracticeLink>
        )}
      </div>
      <PracticeLink className={`btn ${state === 'done' ? 'btn--outline' : 'btn--filled'} btn--md today-review__go`} setId={set.id}>
        {action}
        <Icon name="arrow_forward" size={18} />
      </PracticeLink>
    </section>
  );
}

/** 이어진 파일을 근거로 한 문제의 주제. 그런 문제가 없으면 파일 이름으로. */
function continuedTopic(problems: PracticeProblem[], files: string[]): string {
  const topics = [...new Set(problems.filter((p) => p.sourceFiles.some((f) => files.includes(f))).map((p) => p.topic))];
  return topics.length ? topics.slice(0, 2).join(', ') : files.map(lessonFileLabel).join(', ');
}
