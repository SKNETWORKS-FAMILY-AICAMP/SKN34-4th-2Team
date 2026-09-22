import { Link } from 'react-router-dom';

import { RoutePaths, studyRoomNoteSourcePath } from '../../app/routePaths';
import { useCurriculumSheets, useMyPracticeAttempts, usePracticeSets, useStudyNotes } from '../../data/repository';
import type { AssessmentQuestion } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { useCurrentUser } from '../auth/session';
import { shortDate } from './review';
import { buildReviewLinks, relatedProblemIndexes, type LessonLink } from './reviewLinks';

/** 세트를 열되 n번째 문제로 바로 간다 */
export const playgroundProblemPath = (setId: string, indexes: number[]) =>
  `${RoutePaths.studyRoomPlayground}?set=${encodeURIComponent(setId)}${indexes.length ? `&focus=${indexes[0] + 1}` : ''}`;

/**
 * 성취도평가 결과 위의 「복습할 곳」 — 틀린 문항을 수업별로 묶어 그날 노트와 복습 문제로 보낸다.
 * 새로 저장하는 것은 없다. 문항의 근거 일수 · 커리큘럼 날짜 · 복습 세트 · 노트를 읽어 잇기만 한다.
 */
export function ReviewLinksPanel({ wrong }: { wrong: AssessmentQuestion[] }) {
  const user = useCurrentUser();
  const sheets = useCurriculumSheets();
  const sets = usePracticeSets(user.cohortId);
  const notes = useStudyNotes();
  const attempts = useMyPracticeAttempts(user.uid);
  if (wrong.length === 0) return null;

  const rows = sheets.flatMap((s) => s.rows);
  const links = buildReviewLinks({ wrong, rows, sets, notes, yearHint: new Date().getFullYear() });
  const linked = links.filter((l) => l.set || l.notes.length);
  const orphan = links.filter((l) => !l.set && !l.notes.length);

  return (
    <section className="review-links" aria-label="복습할 곳">
      <header className="review-links__head">
        <Icon name="replay" size={18} />
        <h2>복습할 곳</h2>
        <span>
          틀린 문항 {wrong.length}개 · 수업 {linked.length}군데
        </span>
      </header>

      {linked.map((link) => (
        <LessonRow key={link.day ?? 'none'} link={link} passedOf={(i) => attempts.some((a) => a.setId === link.set?.id && a.index === i && a.passed)} />
      ))}

      {orphan.length > 0 && (
        <p className="review-links__orphan">
          {orphan.flatMap((l) => l.questions).length}문항은 근거 수업 정보가 없어 바로 잇지 못했어요. 문항 아래 해설을 참고하세요.
        </p>
      )}
    </section>
  );
}

function LessonRow({ link, passedOf }: { link: LessonLink; passedOf: (index: number) => boolean }) {
  const { set, notes, questions, date, label } = link;
  const indexes = [...new Set(questions.flatMap((q) => relatedProblemIndexes(link, q)))];
  const target = indexes.length ? indexes : set ? set.problems.map((_, i) => i) : [];
  const passed = target.filter(passedOf).length;
  return (
    <div className="review-links__row">
      <div className="review-links__lesson">
        <strong>{label}</strong>
        <span>
          {date ? `${shortDate(date)}${link.day ? ` · ${link.day}일차` : ''}` : link.day ? `${link.day}일차` : ''} · 틀린 문항 {questions.length}개
        </span>
        <ul className="review-links__questions">
          {questions.map((q) => (
            <li key={q.id}>{q.sourceTopic ?? q.prompt}</li>
          ))}
        </ul>
      </div>
      <div className="review-links__actions">
        {notes.map((n) => (
          <Link key={n.id} className="btn btn--outline btn--sm" to={`${studyRoomNoteSourcePath(n.sourceId)}?note=${encodeURIComponent(n.id)}`}>
            <Icon name="description" size={16} />
            수업 노트
          </Link>
        ))}
        {set ? (
          <Link className="btn btn--filled btn--sm" to={playgroundProblemPath(set.id, indexes)}>
            <Icon name="fitness_center" size={16} />
            복습 문제 {target.length}개 풀기{passed ? ` · 통과 ${passed}` : ''}
          </Link>
        ) : (
          <span className="hint">이 수업의 복습 문제가 아직 없어요</span>
        )}
      </div>
    </div>
  );
}
