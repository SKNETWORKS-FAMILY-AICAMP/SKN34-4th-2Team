import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { RoutePaths, assessmentResultPath, assessmentTakePath } from '../../app/routePaths';
import {
  submitAssessment,
  useAssessment,
  useAssessmentQuestions,
  useAssessments,
  useMyAssessmentSubmission,
} from '../../data/repository';
import type { Assessment } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import {
  Badge,
  Button,
  Card,
  Dialog,
  EmptyState,
  PageHeader,
  ProgressBar,
  Row,
  Spacer,
  StatTile,
  TextInput,
} from '../../ui/components';
import { formatDate } from '../../utils/format';
import { useCurrentUser } from '../auth/session';
import { ReviewLinksPanel } from '../practice/ReviewLinksPanel';

export function windowState(assessment: Assessment): 'before' | 'open' | 'closed' {
  const now = Date.now();
  if (now < assessment.startAt.getTime()) return 'before';
  if (now > assessment.endAt.getTime()) return 'closed';
  return 'open';
}

/** 성취도평가 목록 — features/assessments/presentation/assessments_screen.dart */
export function AssessmentsScreen() {
  const user = useCurrentUser();
  const assessments = useAssessments().filter((a) => a.published);
  const [query, setQuery] = useState('');

  const q = query.trim().toLowerCase();
  const rows = q === '' ? assessments : assessments.filter((a) => a.title.toLowerCase().includes(q));

  // 원본은 860px 한 줄기다. 검색 줄과 목록의 너비가 같다.
  return (
    <div className="screen__inner assess-page">
      <div className="search-bar">
        <Icon name="search" size={20} />
        <input
          className="search-bar__input"
          value={query}
          placeholder="제목 검색"
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {rows.length === 0 ? (
        <Card>
          <EmptyState message="공개된 평가가 없습니다" />
        </Card>
      ) : (
        <div className="stack">
          {rows.map((assessment) => (
            <AssessmentRow key={assessment.id} assessment={assessment} uid={user.uid} />
          ))}
        </div>
      )}
    </div>
  );
}

function AssessmentRow({ assessment, uid }: { assessment: Assessment; uid: string }) {
  const submission = useMyAssessmentSubmission(assessment.id, uid);
  const state = windowState(assessment);
  const [notice, setNotice] = useState('');
  const done = submission !== undefined;
  const closed = state === 'closed';

  const unavailableMessage =
    state === 'before'
      ? '아직 응시 기간이 아닙니다.'
      : state === 'closed' && !done
        ? '종료된 평가이며 응시 기록이 없습니다.'
        : '';

  return (
    <Link
      className="assess-row"
      to={done ? assessmentResultPath(assessment.id) : assessmentTakePath(assessment.id)}
      aria-disabled={unavailableMessage !== ''}
      onClick={(event) => {
        if (unavailableMessage === '') return;
        event.preventDefault();
        setNotice(unavailableMessage);
      }}
    >
      <span className={`assess-row__tile${closed ? ' assess-row__tile--closed' : ''}`}>
        <span>{closed ? '종료' : state === 'before' ? '예정' : '진행중'}</span>
        <strong>{assessment.questionCount}</strong>
      </span>

      <span className="assess-row__body">
        <span className="assess-row__tags">
          {assessment.tags.map((tag) => (
            <span key={tag} className="assess-row__tag">
              {tag}
            </span>
          ))}
        </span>
        <span className="assess-row__title">{assessment.title}</span>
        <span className="hint">
          {assessment.questionCount}문제 · {assessment.maxScore}점
        </span>
        {notice !== '' && <span className="field__error" role="status">{notice}</span>}
      </span>

      {done && (
        <span className="assess-row__score">
          <strong>{submission.totalScore}점</strong>
          <Badge tone="success">
            <Icon name="check_circle" size={14} />
            완료
          </Badge>
        </span>
      )}
    </Link>
  );
}

/** 응시 — assessment_take_screen.dart */
export function AssessmentTakeScreen() {
  const { assessmentId } = useParams<{ assessmentId: string }>();
  const user = useCurrentUser();
  const navigate = useNavigate();
  const assessment = useAssessment(assessmentId);
  const questions = useAssessmentQuestions(assessmentId);
  const submission = useMyAssessmentSubmission(assessmentId, user.uid);
  const [answers, setAnswers] = useState<Record<string, number | string | null>>({});
  const [index, setIndex] = useState(0);
  const [confirmSubmit, setConfirmSubmit] = useState(false);

  if (assessment === undefined) {
    return (
      <div className="screen__inner">
        <Card>
          <EmptyState message="평가를 찾을 수 없습니다" />
        </Card>
      </div>
    );
  }

  if (submission !== undefined) {
    return (
      <div className="screen__inner">
        <Card>
          <EmptyState message="이미 응시한 평가입니다." />
          <Row>
            <Spacer />
            <Link className="btn btn--primary btn--md" to={assessmentResultPath(assessment.id)}>
              결과 보기
            </Link>
            <Spacer />
          </Row>
        </Card>
      </div>
    );
  }

  const state = windowState(assessment);
  if (!assessment.published || state !== 'open') {
    const message = !assessment.published
      ? '공개되지 않은 평가입니다.'
      : state === 'before'
        ? '아직 응시 기간이 아닙니다.'
        : '종료된 평가이며 응시 기록이 없습니다.';
    return (
      <div className="screen__inner">
        <Card>
          <EmptyState message={message} />
          <Row>
            <Spacer />
            <Link className="btn btn--outline btn--md" to={RoutePaths.assessments}>목록으로</Link>
            <Spacer />
          </Row>
        </Card>
      </div>
    );
  }

  const question = questions[index];
  const answered = questions.filter((q) => answers[q.id] !== undefined && answers[q.id] !== '').length;
  const last = index >= questions.length - 1;

  const submit = () => {
    submitAssessment(assessment, questions, user, answers);
    navigate(assessmentResultPath(assessment.id), { replace: true });
  };

  const finish = () => {
    if (answered < questions.length) {
      setConfirmSubmit(true);
      return;
    }
    submit();
  };

  return (
    <div className="screen__inner">
      <PageHeader
        title={assessment.title}
        description={`${questions.length}문항 · ${assessment.maxScore}점`}
        actions={<Badge tone="primary">{answered} / {questions.length} 응답</Badge>}
      />
      <ProgressBar value={answered} max={questions.length} />

      {question === undefined ? (
        <Card>
          <EmptyState message="문항이 없습니다" />
        </Card>
      ) : (
        <Card title={`${index + 1}. ${question.prompt}`}>
          <span className="hint">배점 {question.points}점</span>

          {question.type === 'multipleChoice' ? (
            <div className="choices">
              {question.choices.map((choice, i) => (
                <label key={choice} className={`choice${answers[question.id] === i ? ' choice--on' : ''}`}>
                  <input
                    type="radio"
                    name={question.id}
                    checked={answers[question.id] === i}
                    onChange={() => setAnswers((a) => ({ ...a, [question.id]: i }))}
                  />
                  <span>{choice}</span>
                </label>
              ))}
            </div>
          ) : (
            <TextInput
              value={String(answers[question.id] ?? '')}
              placeholder="답을 입력하세요"
              onChange={(e) => setAnswers((a) => ({ ...a, [question.id]: e.target.value }))}
            />
          )}

          <Row>
            <Button variant="outline" disabled={index === 0} onClick={() => setIndex((i) => i - 1)}>
              이전
            </Button>
            <Spacer />
            {last ? (
              <Button onClick={finish}>제출하기</Button>
            ) : (
              <Button onClick={() => setIndex((i) => i + 1)}>다음</Button>
            )}
          </Row>
        </Card>
      )}

      {confirmSubmit && (
        <Dialog
          title="미응답 문항 확인"
          onClose={() => setConfirmSubmit(false)}
          actions={
            <>
              <Button variant="outline" onClick={() => setConfirmSubmit(false)}>계속 풀기</Button>
              <Button onClick={submit}>그대로 제출</Button>
            </>
          }
        >
          <p>{questions.length - answered}문항이 비어 있습니다. 그대로 제출할까요?</p>
        </Dialog>
      )}
    </div>
  );
}

/** 결과 — assessment_result_screen.dart */
export function AssessmentResultScreen() {
  const { assessmentId } = useParams<{ assessmentId: string }>();
  const user = useCurrentUser();
  const assessment = useAssessment(assessmentId);
  const questions = useAssessmentQuestions(assessmentId);
  const submission = useMyAssessmentSubmission(assessmentId, user.uid);

  if (assessment === undefined || submission === undefined) {
    return (
      <div className="screen__inner">
        <Card>
          <EmptyState message="응시 기록이 없습니다" />
        </Card>
      </div>
    );
  }

  const correct = questions.filter((q) => submission.answers[q.id]?.isCorrect === true).length;
  const wrong = questions.filter((q) => submission.answers[q.id]?.isCorrect !== true);
  const maxScore = assessment.maxScore || questions.reduce((sum, q) => sum + q.points, 0);

  return (
    <div className="screen__inner assess-page">
      <PageHeader
        title={`${assessment.title} 결과`}
        description={`${questions.length}문항 · ${formatDate(submission.submittedAt)} 제출`}
        actions={
          <Link className="btn btn--outline btn--md" to={RoutePaths.assessments}>
            목록으로
          </Link>
        }
      />

      <div className="grid grid--3">
        <StatTile label="점수" value={`${submission.totalScore}점`} sub={`${maxScore}점 만점`} tone="primary" />
        <StatTile label="맞힌 문항" value={`${correct} / ${questions.length}`} sub={correct === questions.length ? '모두 맞혔어요' : `${questions.length - correct}문항 틀림`} tone={correct === questions.length ? 'success' : 'warning'} />
        <StatTile label="정답률" value={`${questions.length ? Math.round((correct / questions.length) * 100) : 0}%`} />
      </div>

      <ReviewLinksPanel wrong={wrong} />

      {questions.map((q, i) => {
        const entry = submission.answers[q.id];
        const isCorrect = entry?.isCorrect === true;
        const given =
          q.type === 'multipleChoice'
            ? q.choices[Number(entry?.value ?? -1)] ?? '무응답'
            : String(entry?.value ?? '무응답');
        const answer =
          q.type === 'multipleChoice'
            ? q.choices[q.correctIndex ?? 0]
            : q.acceptedAnswers.join(' / ');
        return (
          <Card key={q.id} title={`${i + 1}. ${q.prompt}`}>
            <Row gap={6}>
              <Badge tone={isCorrect ? 'success' : 'error'}>{isCorrect ? '정답' : '오답'}</Badge>
              <span className="hint">
                {entry?.finalScore ?? 0} / {q.points}점
              </span>
            </Row>
            <dl className="answer-pair">
              <dt>내 답</dt>
              <dd className={isCorrect ? 'answer-pair__ok' : 'answer-pair__no'}>{given}</dd>
              {!isCorrect && (
                <>
                  <dt>정답</dt>
                  <dd className="answer-pair__ok">{answer}</dd>
                </>
              )}
            </dl>
            {q.explanation !== undefined && <div className="callout">{q.explanation}</div>}
            {!isCorrect && q.sourceDay !== undefined && (
              <p className="hint">
                <Icon name="school" size={14} /> 근거 수업 · {q.sourceDay}일차{q.sourceTopic ? ` · ${q.sourceTopic}` : ''} — 위 「복습할 곳」에서 이어서 복습하세요
              </p>
            )}
            {entry?.comment !== undefined && <div className="callout">채점 의견 · {entry.comment}</div>}
          </Card>
        );
      })}
    </div>
  );
}
