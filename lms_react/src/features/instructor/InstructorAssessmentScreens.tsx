import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import {
  RoutePaths,
  instructorAssessmentDetailPath,
  instructorAssessmentEditPath,
  instructorAssessmentSubmissionPath,
} from '../../app/routePaths';
import {
  deleteAssessment,
  gradeAssessmentAnswer,
  setAssessmentPublished,
  upsertAssessment,
  useAssessment,
  useAssessmentQuestions,
  useAssessmentSubmissions,
  useAssessments,
  useCurriculumSheets,
} from '../../data/repository';
import { nextId } from '../../data/store';
import type { Assessment, AssessmentQuestion } from '../../domain/types';
import { InstructorTargets } from '../../tour/targets';
import { useTourTarget } from '../../tour/useTourTarget';
import { Icon } from '../../ui/Icon';
import { MoreMenu } from '../../ui/MoreMenu';
import { windowState } from '../assessments/AssessmentScreens';
import {
  Badge,
  Button,
  Card,
  Checkbox,
  DataTable,
  EmptyState,
  Field,
  PageHeader,
  Row,
  Select,
  Spacer,
  StatTile,
  TextArea,
  TextInput,
} from '../../ui/components';
import { formatDate, formatDateTime } from '../../utils/format';
import { useCurrentUser } from '../auth/session';

const toInputDate = (d: Date) => d.toISOString().slice(0, 10);

/** 성취도평가 목록(강사) — instructor_assessments_screen.dart */
export function InstructorAssessmentsScreen({ readOnly = false }: { readOnly?: boolean }) {
  const assessments = useAssessments();
  const submissions = useAssessmentSubmissions();
  const navigate = useNavigate();
  const createRef = useTourTarget(InstructorTargets.assessmentsCreate);

  const base = readOnly ? '/admin/assessments' : '/instructor/assessments';

  return (
    <div className="assess-page assess-page--manage">
      {assessments.length === 0 ? (
        <div className="list-page__empty">
          <Icon name="quiz" size={44} />
          <p>등록된 평가가 없습니다</p>
        </div>
      ) : (
        assessments.map((a) => {
          const state = windowState(a);
          const closed = state === 'closed';
          return (
            <div key={a.id} className="assess-row assess-row--static">
              <button
                type="button"
                className="assess-row__open"
                onClick={() => navigate(`${base}/${a.id}`)}
              >
                <span className={`assess-row__tile${closed ? ' assess-row__tile--closed' : ''}`}>
                  <span>{closed ? '종료' : state === 'before' ? '예정' : '진행중'}</span>
                  <strong>{a.questionCount}</strong>
                </span>

                <span className="assess-row__body">
                  <span className="assess-row__tags">
                    {a.tags.map((tag) => (
                      <span key={tag} className="assess-row__tag">
                        {tag}
                      </span>
                    ))}
                  </span>
                  <span className="assess-row__title">{a.title}</span>
                  <span className="hint">
                    {a.questionCount}문제 · {a.maxScore}점 ·{' '}
                    {submissions.filter((s) => s.assessmentId === a.id).length}명 응시
                  </span>
                </span>
              </button>

              {readOnly ? (
                <Badge tone={a.published ? 'success' : 'neutral'}>
                  {a.published ? '발행' : '준비중'}
                </Badge>
              ) : (
                <MoreMenu
                  icon="more_vert"
                  items={[
                    { key: 'open', label: '열기', onSelect: () => navigate(`${base}/${a.id}`) },
                    {
                      key: 'publish',
                      label: a.published ? '발행 내리기' : '발행하기',
                      onSelect: () => setAssessmentPublished(a.id, !a.published),
                    },
                  ]}
                />
              )}
            </div>
          );
        })
      )}

      {!readOnly && (
        <Link className="curri-fab" ref={createRef} to={RoutePaths.instructorAssessmentsCreate}>
          <Icon name="add" size={20} />
          평가 만들기
        </Link>
      )}
    </div>
  );
}

/** 평가 상세 — instructor_assessment_detail_screen.dart */
export function InstructorAssessmentDetailScreen({ readOnly = false }: { readOnly?: boolean }) {
  const { assessmentId } = useParams<{ assessmentId: string }>();
  const assessment = useAssessment(assessmentId);
  const questions = useAssessmentQuestions(assessmentId);
  const submissions = useAssessmentSubmissions(assessmentId);
  const navigate = useNavigate();

  if (assessment === undefined) {
    return (
      <div className="screen__inner">
        <Card>
          <EmptyState message="평가를 찾을 수 없습니다" />
        </Card>
      </div>
    );
  }

  const average =
    submissions.length === 0
      ? 0
      : Math.round((submissions.reduce((s, x) => s + x.totalScore, 0) / submissions.length) * 10) / 10;

  return (
    <div className="screen__inner">
      <PageHeader
        title={assessment.title}
        description={`${formatDate(assessment.startAt)} ~ ${formatDate(assessment.endAt)}`}
        actions={
          readOnly ? undefined : (
            <>
              <Button variant="outline" onClick={() => navigate(instructorAssessmentEditPath(assessment.id))}>
                수정
              </Button>
              <Button
                variant="danger"
                onClick={() => {
                  deleteAssessment(assessment.id);
                  navigate(RoutePaths.instructorAssessments);
                }}
              >
                삭제
              </Button>
            </>
          )
        }
      />

      <div className="grid grid--4">
        <StatTile label="문항" value={questions.length} />
        <StatTile label="만점" value={assessment.maxScore} />
        <StatTile label="응시" value={submissions.length} tone="primary" />
        <StatTile label="평균" value={average} tone="success" />
      </div>

      <Card title="문항">
        {questions.length === 0 ? (
          <EmptyState message="문항이 없습니다" />
        ) : (
          questions.map((q, i) => (
            <div key={q.id} className="callout">
              <Row gap={6}>
                <Badge tone="primary">{q.type === 'multipleChoice' ? '객관식' : '단답형'}</Badge>
                <span className="hint">{q.points}점</span>
                {q.origin === 'ai' && <Badge tone="info">AI 생성</Badge>}
              </Row>
              <p style={{ margin: '6px 0 0' }}>
                {i + 1}. {q.prompt}
              </p>
              {q.type === 'multipleChoice' && (
                <ul className="list">
                  {q.choices.map((c, ci) => (
                    <li key={c} className="list__item">
                      {ci === q.correctIndex ? <Badge tone="success">정답</Badge> : <span className="hint">{ci + 1}</span>}
                      <span>{c}</span>
                    </li>
                  ))}
                </ul>
              )}
              {q.type === 'shortAnswer' && <span className="hint">정답: {q.acceptedAnswers.join(' / ')}</span>}
            </div>
          ))
        )}
      </Card>

      <Card padded={false} title="응시 현황">
        <DataTable
          rows={submissions}
          rowKey={(s) => s.id}
          empty="아직 응시한 학생이 없습니다."
          onRowClick={(s) => navigate(instructorAssessmentSubmissionPath(assessment.id, s.id))}
          columns={[
            { key: 'name', header: '학생', render: (s) => s.userDisplayName },
            { key: 'score', header: '점수', render: (s) => `${s.totalScore} / ${assessment.maxScore}` },
            { key: 'auto', header: '자동 채점', render: (s) => s.autoTotalScore },
            { key: 'at', header: '제출', render: (s) => formatDateTime(s.submittedAt) },
            {
              key: 'graded',
              header: '채점',
              render: (s) => (
                <Badge tone={s.gradedAt === undefined ? 'warning' : 'success'}>
                  {s.gradedAt === undefined ? '미확정' : '확정'}
                </Badge>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}

/** 제출 채점 — instructor_assessment_submission_screen.dart */
export function InstructorAssessmentSubmissionScreen({ canEditScores = true }: { canEditScores?: boolean }) {
  const { assessmentId, submissionId } = useParams<{ assessmentId: string; submissionId: string }>();
  const assessment = useAssessment(assessmentId);
  const questions = useAssessmentQuestions(assessmentId);
  const submissions = useAssessmentSubmissions(assessmentId);
  const submission = submissions.find((s) => s.id === submissionId);

  if (assessment === undefined || submission === undefined) {
    return (
      <div className="screen__inner">
        <Card>
          <EmptyState message="제출을 찾을 수 없습니다" />
        </Card>
      </div>
    );
  }

  return (
    <div className="screen__inner">
      <PageHeader
        title={`${submission.userDisplayName} · ${assessment.title}`}
        description={`제출 ${formatDateTime(submission.submittedAt)}`}
        actions={<Badge tone="primary">{submission.totalScore} / {assessment.maxScore}점</Badge>}
      />

      {questions.map((q, i) => {
        const entry = submission.answers[q.id];
        const given =
          q.type === 'multipleChoice'
            ? q.choices[Number(entry?.value ?? -1)] ?? '무응답'
            : String(entry?.value ?? '무응답');
        return (
          <Card key={q.id} title={`${i + 1}. ${q.prompt}`}>
            <Row gap={6}>
              <Badge tone={entry?.isCorrect === true ? 'success' : 'error'}>
                {entry?.isCorrect === true ? '정답' : '오답'}
              </Badge>
              <span className="hint">자동 채점 {entry?.autoScore ?? 0}점</span>
            </Row>
            <p className="muted">학생 답 · {given}</p>

            {canEditScores ? (
              <Row gap={8}>
                <Field label="확정 점수">
                  <TextInput
                    type="number"
                    min={0}
                    max={q.points}
                    defaultValue={entry?.finalScore ?? 0}
                    style={{ width: 100 }}
                    onBlur={(e) =>
                      gradeAssessmentAnswer(submission.id, q.id, Number(e.target.value), entry?.comment)
                    }
                  />
                </Field>
                <Field label="채점 의견">
                  <TextInput
                    defaultValue={entry?.comment ?? ''}
                    onBlur={(e) =>
                      gradeAssessmentAnswer(submission.id, q.id, entry?.finalScore ?? 0, e.target.value)
                    }
                  />
                </Field>
              </Row>
            ) : (
              <span className="hint">확정 점수 {entry?.finalScore ?? 0} / {q.points}</span>
            )}
          </Card>
        );
      })}
    </div>
  );
}

/** 평가 만들기·수정 — instructor_assessment_form_screen.dart */
export function InstructorAssessmentFormScreen() {
  const { assessmentId } = useParams<{ assessmentId: string }>();
  const existing = useAssessment(assessmentId);
  const existingQuestions = useAssessmentQuestions(assessmentId);
  const sheets = useCurriculumSheets();
  const user = useCurrentUser();
  const navigate = useNavigate();

  const [title, setTitle] = useState(existing?.title ?? '');
  const [tags, setTags] = useState((existing?.tags ?? []).join(', '));
  const [startAt, setStartAt] = useState(toInputDate(existing?.startAt ?? new Date()));
  const [endAt, setEndAt] = useState(
    toInputDate(existing?.endAt ?? new Date(Date.now() + 14 * 86400000)),
  );
  const [published, setPublished] = useState(existing?.published ?? false);
  const [questions, setQuestions] = useState<AssessmentQuestion[]>(existingQuestions);
  const [error, setError] = useState<string | null>(null);

  const addQuestion = (type: AssessmentQuestion['type']) =>
    setQuestions((qs) => [
      ...qs,
      {
        id: nextId('q'),
        order: qs.length,
        type,
        prompt: '',
        points: 5,
        choices: type === 'multipleChoice' ? ['', '', '', ''] : [],
        correctIndex: type === 'multipleChoice' ? 0 : undefined,
        acceptedAnswers: [],
        origin: 'manual',
      },
    ]);

  /** 커리큘럼에서 문항 뼈대를 뽑아 온다. 실제 앱은 여기서 LLM을 부른다. */
  const draftFromCurriculum = () => {
    const rows = sheets[0]?.rows ?? [];
    const drafts: AssessmentQuestion[] = rows.slice(0, 3).map((row, i) => ({
      id: nextId('q'),
      order: questions.length + i,
      type: 'shortAnswer',
      prompt: `${row.topic} — ${row.detail} 중 핵심 개념을 한 단어로 쓰시오.`,
      points: 5,
      choices: [],
      acceptedAnswers: [row.topic],
      origin: 'ai',
      sourceDay: row.dayIndex,
      sourceTopic: row.topic,
    }));
    setQuestions((qs) => [...qs, ...drafts]);
  };

  const patch = (id: string, change: Partial<AssessmentQuestion>) =>
    setQuestions((qs) => qs.map((q) => (q.id === id ? { ...q, ...change } : q)));

  const save = () => {
    if (title.trim() === '') {
      setError('제목을 입력해 주세요.');
      return;
    }
    const assessment: Assessment = {
      id: existing?.id ?? nextId('a'),
      title: title.trim(),
      tags: tags.split(',').map((t) => t.trim()).filter((t) => t !== ''),
      questionCount: questions.length,
      maxScore: questions.reduce((s, q) => s + q.points, 0),
      startAt: new Date(startAt),
      endAt: new Date(endAt),
      published,
      createdBy: existing?.createdBy ?? user.uid,
      createdAt: existing?.createdAt ?? new Date(),
    };
    upsertAssessment(assessment, questions.map((q, i) => ({ ...q, order: i })));
    navigate(instructorAssessmentDetailPath(assessment.id));
  };

  return (
    <div className="screen__inner">
      <PageHeader title={existing === undefined ? '평가 만들기' : '평가 수정'} />

      <Card title="기본 정보">
        <Field label="제목" error={error ?? undefined}>
          <TextInput value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label="태그" hint="쉼표로 구분합니다.">
          <TextInput value={tags} onChange={(e) => setTags(e.target.value)} placeholder="Python, 기초" />
        </Field>
        <Row gap={12}>
          <Field label="시작일">
            <TextInput type="date" value={startAt} onChange={(e) => setStartAt(e.target.value)} />
          </Field>
          <Field label="종료일">
            <TextInput type="date" value={endAt} onChange={(e) => setEndAt(e.target.value)} />
          </Field>
        </Row>
        <Checkbox checked={published} onChange={setPublished} label="학생에게 발행합니다" />
      </Card>

      <Card
        title={`문항 (${questions.length})`}
        actions={
          <>
            <Button size="sm" variant="outline" onClick={() => addQuestion('multipleChoice')}>
              객관식 추가
            </Button>
            <Button size="sm" variant="outline" onClick={() => addQuestion('shortAnswer')}>
              단답형 추가
            </Button>
            <Button size="sm" variant="outline" onClick={draftFromCurriculum}>
              커리큘럼에서 초안
            </Button>
          </>
        }
      >
        {questions.length === 0 ? (
          <EmptyState message="문항을 추가해 주세요" />
        ) : (
          questions.map((q, i) => (
            <Card key={q.id} className="nested-card">
              <Row gap={6}>
                <Badge tone="primary">{q.type === 'multipleChoice' ? '객관식' : '단답형'}</Badge>
                {q.origin === 'ai' && <Badge tone="info">AI 초안</Badge>}
                <Spacer />
                <Button
                  size="sm"
                  variant="text"
                  onClick={() => setQuestions((qs) => qs.filter((x) => x.id !== q.id))}
                >
                  삭제
                </Button>
              </Row>

              <Field label={`문항 ${i + 1}`}>
                <TextArea rows={2} value={q.prompt} onChange={(e) => patch(q.id, { prompt: e.target.value })} />
              </Field>

              {q.type === 'multipleChoice' ? (
                <>
                  {q.choices.map((choice, ci) => (
                    <Row key={ci} gap={8} wrap={false}>
                      <TextInput
                        value={choice}
                        placeholder={`보기 ${ci + 1}`}
                        onChange={(e) =>
                          patch(q.id, {
                            choices: q.choices.map((c, x) => (x === ci ? e.target.value : c)),
                          })
                        }
                      />
                      <label className="checkbox">
                        <input
                          type="radio"
                          name={q.id}
                          checked={q.correctIndex === ci}
                          onChange={() => patch(q.id, { correctIndex: ci })}
                        />
                        <span>정답</span>
                      </label>
                    </Row>
                  ))}
                </>
              ) : (
                <Field label="정답" hint="쉼표로 여러 개를 인정할 수 있습니다.">
                  <TextInput
                    value={q.acceptedAnswers.join(', ')}
                    onChange={(e) =>
                      patch(q.id, {
                        acceptedAnswers: e.target.value.split(',').map((a) => a.trim()).filter((a) => a !== ''),
                      })
                    }
                  />
                </Field>
              )}

              <Field label="배점">
                <Select value={q.points} onChange={(e) => patch(q.id, { points: Number(e.target.value) })}>
                  {[1, 2, 5, 10, 20].map((p) => (
                    <option key={p} value={p}>
                      {p}점
                    </option>
                  ))}
                </Select>
              </Field>
            </Card>
          ))
        )}
      </Card>

      <Row>
        <Spacer />
        <Button variant="outline" onClick={() => navigate(RoutePaths.instructorAssessments)}>
          취소
        </Button>
        <Button onClick={save}>저장</Button>
      </Row>
    </div>
  );
}
