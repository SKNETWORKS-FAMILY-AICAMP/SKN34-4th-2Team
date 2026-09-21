import { Link } from 'react-router-dom';

import { RoutePaths } from '../../app/routePaths';
import { useMyPracticeAttempts, usePracticeSets } from '../../data/repository';
import { todayKey } from '../../data/store';
import type { PracticeKind, PracticeProblem } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { useCurrentUser } from '../auth/session';
import { KIND_LABEL } from './ProblemCell';
import {
  dueRetries,
  lessonFileLabel,
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
  const review = pickTodayReview(sets, attempts, today);
  if (!review) return null;
  // 오늘 틀린 문제는 빼고, 하루 이상 지난 것만 다시 보여 준다
  const retries = dueRetries(retryItems(sets, attempts), today);

  const { set, daysAgo, state, passed, total, minutes, continuesFrom } = review;
  const kinds = countKinds(set.problems.map((p) => p.kind));
  const when = daysAgo === 0 ? `오늘 수업 · ${shortDate(set.lessonDate)}` : `지난 수업 · ${shortDate(set.lessonDate)} (${daysAgo}일 전)`;
  const action = state === 'done' ? '다시 보기' : state === 'partial' ? '이어서 풀기' : '복습 시작';

  return (
    <section className={`today-review today-review--${state}`} aria-label="오늘 복습">
      <div className="today-review__body">
        <div className="today-review__eyebrow">
          <Icon name="replay" size={16} />
          <strong>오늘 복습</strong>
          <span>{when}</span>
        </div>
        <h2 className="today-review__title">
          {set.dayLabel} · {set.title}
        </h2>
        <p className="today-review__meta">
          {total}문제 · {kinds} · 약 {minutes}분
        </p>
        {continuesFrom && (
          <p className="today-review__continue">
            <Icon name="subdirectory_arrow_right" size={15} />
            {shortDate(continuesFrom.date)} 수업에서 이어짐 · {continuedTopic(set.problems, continuesFrom.files)}
          </p>
        )}
        {retries.length > 0 && (
          <Link className="today-review__retry" to={`${RoutePaths.studyRoomPlayground}?set=${RETRY_SET_ID}`}>
            <Icon name="history" size={16} />
            지난번에 틀린 문제 {retries.length}개 · {retryTopics(retries)}
            <span className="today-review__retry-date">({retryDates(retries)})</span>
            <span className="today-review__retry-go">
              다시 풀기
              <Icon name="chevron_right" size={16} />
            </span>
          </Link>
        )}
      </div>
      <div className="today-review__side">
        <div className="today-review__progress" aria-label={`통과 ${passed} / ${total}`}>
          <span className="today-review__bar">
            {set.problems.map((_, i) => {
              const a = attempts.find((x) => x.setId === set.id && x.index === i);
              return <i key={i} className={a?.passed ? 'ok' : a ? 'no' : ''} />;
            })}
          </span>
          <span>{state === 'done' ? '모두 통과했어요' : state === 'partial' ? `통과 ${passed} / ${total}` : '아직 안 풀었어요'}</span>
        </div>
        <Link
          className={`btn ${state === 'done' ? 'btn--outline' : 'btn--filled'} btn--md`}
          to={`${RoutePaths.studyRoomPlayground}?set=${encodeURIComponent(set.id)}`}
        >
          {action}
          <Icon name="arrow_forward" size={18} />
        </Link>
      </div>
    </section>
  );
}

/** 이어진 파일을 근거로 한 문제의 주제. 그런 문제가 없으면 파일 이름으로. */
function continuedTopic(problems: PracticeProblem[], files: string[]): string {
  const topics = [...new Set(problems.filter((p) => p.sourceFiles.some((f) => files.includes(f))).map((p) => p.topic))];
  return topics.length ? topics.slice(0, 2).join(', ') : files.map(lessonFileLabel).join(', ');
}

/** ['concept','concept','code_blank'] → '개념 2 · 빈칸 채우기 1' (문제 순서대로) */
function countKinds(kinds: PracticeKind[]): string {
  const counts = new Map<PracticeKind, number>();
  for (const k of kinds) counts.set(k, (counts.get(k) ?? 0) + 1);
  return [...counts].map(([k, n]) => `${KIND_LABEL[k]} ${n}`).join(' · ');
}
