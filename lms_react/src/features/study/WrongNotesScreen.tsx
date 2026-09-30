import { useState } from 'react';

import { usePageCrumbs } from '../../app/crumbs';
import { RoutePaths } from '../../app/routePaths';
import { useMyPracticeAttempts, usePracticeSets } from '../../data/repository';
import type { PracticeProblem, PracticeSet } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { useCurrentUser } from '../auth/session';
import { PracticeLink } from '../practice/PracticeDock';
import { KIND_LABEL } from '../practice/practiceLabels';
import { isLessonSet, RETRY_ALL_ID, retryDateId, shortDate, wrongNoteDays, type WrongNoteDay } from '../practice/review';
import { useIsHidden } from '../practice/useIsHidden';
import { dayText } from './LessonDaysSection';

/**
 * 오답노트 — 복습에서 틀린 문제를 수업 날짜별로 모은다(학습실 › 오답노트).
 *
 * 못 푼 문제는 「이날 다시 풀기」로 그날 것만, 「전체 다시 풀기」로 모두 연습장(창)에 연다.
 * 대시보드의 「지난번에 틀린 문제」와 달리 오늘 틀린 것도 바로 모은다 — 여기는 학생이 날짜를 골라 들어오는 곳이다.
 * 다시 풀어 통과하면 원래 세트에 통과로 남고 「해결한 문제」로 옮겨진다.
 */
export function WrongNotesScreen() {
  const user = useCurrentUser();
  usePageCrumbs([{ label: '학습실', to: RoutePaths.studyRoom }, { label: '오답노트' }]);
  const sets = usePracticeSets(user.cohortId);
  const attempts = useMyPracticeAttempts(user.uid);
  const isHidden = useIsHidden();
  const [showSolved, setShowSolved] = useState(false);

  const days = wrongNoteDays(sets, attempts, isHidden);
  const wrongCount = days.reduce((n, d) => n + d.wrong.length, 0);
  const solvedCount = days.reduce((n, d) => n + d.solved.length, 0);
  const shown = days.filter((d) => d.wrong.length > 0 || (showSolved && d.solved.length > 0));

  return (
    <div className="screen__inner study-room wrong-notes">
      <header className="study-head">
        <div>
          <h1 className="study-head__title">오답노트</h1>
          <p className="study-head__desc">복습에서 틀린 문제를 수업 날짜별로 모았어요. 다시 풀어 통과하면 「해결한 문제」로 옮겨져요.</p>
        </div>
      </header>

      {days.length === 0 ? (
        <div className="review-hero review-hero--empty">
          <Icon name="task_alt" size={22} />
          <div>
            <strong>틀린 복습 문제가 없어요</strong>
            <p className="hint">복습 문제를 풀다 틀리면 여기에 수업 날짜별로 모여요.</p>
          </div>
        </div>
      ) : (
        <>
          <div className="wrong-summary">
            <span className="study-entry__pill study-entry__pill--warn">못 푼 문제 {wrongCount}</span>
            <span className="study-entry__pill wrong-summary__solved">해결한 문제 {solvedCount}</span>
            <label className="wrong-summary__toggle">
              <input type="checkbox" checked={showSolved} onChange={(e) => setShowSolved(e.target.checked)} />
              해결한 문제도 보기
            </label>
            <span className="spacer" />
            {wrongCount > 0 && (
              <PracticeLink className="btn btn--filled btn--sm" setId={RETRY_ALL_ID}>
                전체 다시 풀기 ({wrongCount})
                <Icon name="arrow_forward" size={16} />
              </PracticeLink>
            )}
          </div>

          {shown.length === 0 ? (
            <div className="review-hero review-hero--empty">
              <Icon name="celebration" size={22} />
              <div>
                <strong>틀렸던 문제를 모두 다시 풀었어요</strong>
                <p className="hint">「해결한 문제도 보기」를 켜면 다시 풀어 맞힌 문제를 볼 수 있어요.</p>
              </div>
            </div>
          ) : (
            <div className="wrong-days">
              {shown.map((day) => (
                <WrongDay key={day.date} day={day} showSolved={showSolved} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function WrongDay({ day, showSolved }: { day: WrongNoteDay; showSolved: boolean }) {
  const solved = showSolved ? day.solved : [];
  return (
    <section className="wrong-day" aria-label={`${dayText(day.date)} 오답`}>
      <header className="wrong-day__head">
        <span className="wrong-day__date">{dayText(day.date)}</span>
        <strong className="wrong-day__title">{day.sets.map(setLabel).join(' / ')}</strong>
        <span className="wrong-day__count">
          {day.wrong.length > 0 && <span className="wrong-day__wrong">못 푼 {day.wrong.length}</span>}
          {day.solved.length > 0 && <span>해결 {day.solved.length}</span>}
        </span>
        {day.wrong.length > 0 && (
          <PracticeLink className="btn btn--outline btn--sm" setId={retryDateId(day.date)}>
            이날 다시 풀기
            <Icon name="arrow_forward" size={16} />
          </PracticeLink>
        )}
      </header>
      <ul className="wrong-list">
        {day.wrong.map((item, k) => (
          <li key={`${item.set.id}:${item.index}`}>
            {/* 그날 오답 세트를 이 문제 자리로 연다 — 세트 안 순서가 곧 k */}
            <PracticeLink className="wrong-item" setId={retryDateId(day.date)} focus={k + 1}>
              <Icon name="close" size={16} className="wrong-item__mark" />
              <ProblemText set={item.set} index={item.index} />
              <span className="wrong-item__meta">
                {item.tries}번 틀림 · {shortDate(item.lastTried)}
              </span>
            </PracticeLink>
          </li>
        ))}
        {solved.map((s) => (
          <li key={`${s.set.id}:${s.index}`}>
            <PracticeLink className="wrong-item wrong-item--solved" setId={s.set.id} focus={s.index + 1}>
              <Icon name="check" size={16} className="wrong-item__mark" />
              <ProblemText set={s.set} index={s.index} />
              <span className="wrong-item__meta">{s.tries}번 만에 해결</span>
            </PracticeLink>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ProblemText({ set, index }: { set: PracticeSet; index: number }) {
  const problem = set.problems[index];
  return (
    <>
      <span className="wrong-item__no">문제 {index + 1}</span>
      <span className="wrong-item__kind">{kindText(problem)}</span>
      <span className="wrong-item__topic">
        {problem.topic || problem.prompt}
        {!isLessonSet(set) && <span className="hint"> · 내가 만든 문제</span>}
      </span>
    </>
  );
}

/** 그날 세트 이름 — 「web_client 3일차 · DOM의 의미」 */
function setLabel(set: PracticeSet): string {
  return [set.dayLabel, set.title].filter(Boolean).join(' · ');
}

/** 종류 · 언어 — 「디버깅 · JS」. 웹 실습 · SQL 은 이름에 언어가 있다 */
function kindText(problem: PracticeProblem): string {
  const js = problem.packages?.includes('js') ? ' · JS' : '';
  return `${KIND_LABEL[problem.kind]}${js}`;
}
