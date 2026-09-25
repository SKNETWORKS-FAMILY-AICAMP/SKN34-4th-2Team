import { reviewPracticeProblem, usePracticeReports, usePracticeReviews, usePracticeSets, useUsers } from '../../data/repository';
import { Icon } from '../../ui/Icon';
import { Badge, PageHeader } from '../../ui/components';
import { formatRelative } from '../../utils/format';
import { useCurrentUser } from '../auth/session';
import { KIND_LABEL } from '../practice/practiceLabels';
import { NotebookMarkdown } from '../practice/NotebookMarkdown';
import { flaggedProblems, HIDE_AT, REASON_LABEL, type FlaggedProblem } from '../practice/reports';
import { shortDate } from '../practice/review';

/**
 * 복습 문제 — 학생 신고가 모인 문제를 강사가 본다.
 *
 * 생성 쪽 자동 규칙(정적 검사 · 실행 검증)은 「돌아가는지」만 본다. 「풀 만한 문제인지」는
 * 실제로 푼 학생이 안다. 서로 다른 학생 HIDE_AT 명이 신고하면 그 문제는 학생 화면에서
 * 자동으로 빠지고 여기 맨 위로 온다. 강사는 「다시 보이기」 또는 「숨김 유지」만 고른다.
 */
export function InstructorPracticeScreen() {
  const user = useCurrentUser();
  const sets = usePracticeSets(user.cohortId);
  const reports = usePracticeReports();
  const reviews = usePracticeReviews();
  const list = flaggedProblems(sets, reports, reviews);
  const hidden = list.filter((f) => f.hidden).length;

  return (
    <div className="practice-mod">
      <PageHeader
        title="복습 문제 신고"
        description={`학생이 「이상해요」를 누른 문제입니다. 서로 다른 학생 ${HIDE_AT}명이 신고하면 자동으로 숨겨져요. 확인한 뒤 다시 보일지 정해 주세요.`}
        actions={
          <div className="practice-mod__stats">
            <Stat label="신고된 문제" value={list.length} />
            <Stat label="숨김" value={hidden} tone={hidden ? 'warn' : undefined} />
            <Stat label="복습 세트" value={sets.length} />
          </div>
        }
      />

      {list.length === 0 ? (
        <div className="list-page__empty">
          <Icon name="flag" size={44} />
          <p>신고된 문제가 없습니다</p>
        </div>
      ) : (
        <div className="practice-mod__list">
          {list.map((f) => (
            <FlaggedRow key={`${f.set.id}#${f.index}`} item={f} decidedBy={user.uid} />
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: 'warn' }) {
  return (
    <div className={`practice-mod__stat${tone ? ` practice-mod__stat--${tone}` : ''}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function FlaggedRow({ item, decidedBy }: { item: FlaggedProblem; decidedBy: string }) {
  const users = useUsers();
  const problem = item.set.problems[item.index];
  const nameOf = (uid: string) => users.find((u) => u.uid === uid)?.displayName ?? '학생';
  const decide = (decision: 'kept' | 'hidden') => reviewPracticeProblem(decidedBy, item.set.id, item.index, decision);

  return (
    <article className={`flag-row${item.hidden ? ' flag-row--hidden' : ''}`}>
      <div className="flag-row__head">
        <span className="pb__num">
          {shortDate(item.set.lessonDate)} · 문제 {item.index + 1}
        </span>
        <span className="pb__kind">{KIND_LABEL[problem.kind]}</span>
        <span className="pb__topic">{problem.topic}</span>
        <span className="py-grow" />
        {item.review ? (
          <Badge tone={item.review.decision === 'hidden' ? 'warning' : 'success'}>
            {item.review.decision === 'hidden' ? '강사가 숨김' : '강사가 다시 보임'}
          </Badge>
        ) : item.hidden ? (
          <Badge tone="warning">신고 {item.reporters}명 · 자동 숨김</Badge>
        ) : (
          <Badge tone="neutral">
            신고 {item.reporters}명 · {HIDE_AT}명이면 숨김
          </Badge>
        )}
      </div>

      <div className="flag-row__body">
        <div className="flag-row__prompt">
          <NotebookMarkdown source={problem.prompt} />
          {problem.kind === 'concept' && (
            <ol className="flag-row__choices" type="A">
              {problem.choices.map((c, i) => (
                <li key={i} className={i === problem.answerIndex ? 'is-answer' : ''}>
                  {c}
                </li>
              ))}
            </ol>
          )}
          {problem.hiddenTests && (
            <details className="flag-row__tests">
              <summary>숨긴 테스트 · 모범답안</summary>
              <pre>{problem.hiddenTests}</pre>
              {problem.referenceSolution && <pre>{problem.referenceSolution}</pre>}
            </details>
          )}
        </div>
        <ul className="flag-row__reports">
          {item.reports.map((r) => (
            <li key={r.id}>
              <Icon name="flag" size={14} fill />
              <div>
                <strong>{REASON_LABEL[r.reason]}</strong>
                {r.note && <p>“{r.note}”</p>}
                <small>
                  {nameOf(r.uid)} · {formatRelative(r.createdAt)}
                </small>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <div className="flag-row__actions">
        <button type="button" className="btn btn--outline btn--sm" onClick={() => decide('kept')} disabled={item.review?.decision === 'kept'}>
          <Icon name="visibility" size={16} />
          다시 보이기
        </button>
        <button type="button" className="btn btn--filled btn--sm" onClick={() => decide('hidden')} disabled={item.review?.decision === 'hidden'}>
          <Icon name="visibility_off" size={16} />
          숨김 유지
        </button>
        {item.review && (
          <span className="pb__muted">
            {formatRelative(item.review.decidedAt)} 결정 · 문제 자체는 다음 세트 생성 때 빼는 쪽으로 넘겨요
          </span>
        )}
      </div>
    </article>
  );
}
