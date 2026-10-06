import { MaterialIcons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useState, type ReactNode } from 'react';
import { Pressable, View } from 'react-native';
import { RoutePaths } from '@web/app/routePaths';
import type { Assessment, AssessmentQuestion, AssessmentQuestionType, AssessmentSubmission } from '@web/domain/types';

import { useSession } from '../auth/session';
import { deleteAssessment, gradeAnswer, saveAssessment, setPublished, useAssessments, useQuestions, useSubmissions } from '../data/assessments';
import { useUsers } from '../data/people';
import { refreshBootstrap, useDb } from '../data/query';
import { navLabel } from '../nav/webNav';
import { useTheme } from '../theme/Theme';
import { ChipRow, JobNotice, SectionLabel, ToggleRow, confirmAction, dateFromKey, dateLabel, isDateKey, keyOf, useJob } from '../ui/form';
import { Badge, Btn, Callout, Card, EmptyState, Field, ListGroup, ListItem, Muted, Screen, T, fmt, goBack } from '../ui/kit';

function push(path: string) {
  router.push(path as never);
}

function Actions({ children }: { children: ReactNode }) {
  return <View style={{ flexDirection: 'row', gap: 8 }}>{children}</View>;
}

function Half({ children }: { children: ReactNode }) {
  return <View style={{ flex: 1 }}>{children}</View>;
}

const TYPE_LABEL: Record<AssessmentQuestionType, string> = { multipleChoice: '객관식', shortAnswer: '단답형' };

function phaseOf(exam: Assessment): { label: string; tone: 'success' | 'info' | 'neutral' } {
  const now = Date.now();
  if (exam.startAt.getTime() > now) return { label: '예정', tone: 'info' };
  if (exam.endAt.getTime() < now) return { label: '종료', tone: 'neutral' };
  return { label: '진행 중', tone: 'success' };
}

/** 단답형인데 아직 사람이 점수를 매기지 않은 답이 있는가 */
function needsGrading(submission: AssessmentSubmission, questions: AssessmentQuestion[]): boolean {
  return questions.some((question) => {
    if (question.type !== 'shortAnswer') return false;
    const entry = submission.answers[question.id];
    return entry !== undefined && entry.finalScore == null;
  });
}

export function ExamsAdminPage({ readOnly = false }: { readOnly?: boolean }) {
  const exams = [...useAssessments()].sort((a, b) => b.startAt.getTime() - a.startAt.getTime());
  const submissions = useSubmissions();
  const base = readOnly ? '/(admin)' : '/(instructor)';
  const title = readOnly ? navLabel(RoutePaths.adminAssessments, '성취도 평가') : navLabel(RoutePaths.instructorAssessments, '성취도평가');
  return (
    <Screen title={title} onRefresh={refreshBootstrap}>
      {readOnly ? <Muted>관리자는 결과를 조회만 합니다. 출제 · 채점은 강사가 합니다.</Muted> : <Btn label="새 평가" icon="add" onPress={() => push(`${base}/exams/new`)} />}
      {exams.length === 0 ? <Card><EmptyState icon="quiz" text="등록된 평가가 없습니다." /></Card> : null}
      {exams.map((exam) => {
        const phase = phaseOf(exam);
        const count = submissions.filter((row) => row.assessmentId === exam.id).length;
        return (
          <Card key={exam.id} onPress={() => push(`${base}/exams/${exam.id}`)} style={{ gap: 6 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <T variant="subtitle" style={{ flex: 1 }} numberOfLines={2}>{exam.title}</T>
              <Badge label={phase.label} tone={phase.tone} />
              <Badge label={exam.published ? '공개' : '비공개'} tone={exam.published ? 'primary' : 'neutral'} />
            </View>
            <T variant="caption" tone="secondary">
              {dateLabel(exam.startAt)} ~ {dateLabel(exam.endAt)} · {exam.questionCount}문항 · {exam.maxScore}점 · 제출 {count}명
            </T>
            {exam.tags.length > 0 ? <T variant="caption" tone="hint">#{exam.tags.join(' #')}</T> : null}
          </Card>
        );
      })}
    </Screen>
  );
}

type Draft = {
  key: string;
  id: string;
  type: AssessmentQuestionType;
  prompt: string;
  points: string;
  choices: string;
  correctIndex: number;
  accepted: string;
  explanation: string;
  origin: string;
  sourceDay?: number;
  sourceTopic?: string;
};

function newId(): string {
  return `q${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}

function toDraft(question: AssessmentQuestion): Draft {
  return {
    key: question.id,
    id: question.id,
    type: question.type,
    prompt: question.prompt,
    points: String(question.points),
    choices: question.choices.join('\n'),
    correctIndex: question.correctIndex ?? -1,
    accepted: question.acceptedAnswers.join(', '),
    explanation: question.explanation ?? '',
    origin: question.origin || 'manual',
    sourceDay: question.sourceDay,
    sourceTopic: question.sourceTopic,
  };
}

function blank(type: AssessmentQuestionType): Draft {
  const id = newId();
  return { key: id, id, type, prompt: '', points: '10', choices: '', correctIndex: -1, accepted: '', explanation: '', origin: 'manual' };
}

function choicesOf(draft: Draft): string[] {
  return draft.choices.split('\n').map((line) => line.trim()).filter(Boolean);
}

export function ExamEditPage({ id }: { id?: string }) {
  const db = useDb();
  const exam = useAssessments().find((row) => row.id === id);
  const questions = useQuestions(id);
  const submitted = useSubmissions(id).length;
  if (id && !db) return <Screen title="평가 수정" loading />;
  if (id && !exam) return <Screen title="평가 수정" empty emptyText="평가를 찾지 못했습니다." />;
  return <ExamEditor key={exam?.id ?? 'new'} exam={exam} questions={questions} locked={submitted > 0} submitted={submitted} />;
}

function ExamEditor({ exam, questions, locked, submitted }: { exam?: Assessment; questions: AssessmentQuestion[]; locked: boolean; submitted: number }) {
  const { user } = useSession();
  const { palette } = useTheme();
  const job = useJob();
  const [title, setTitle] = useState(exam?.title ?? '');
  const [tags, setTags] = useState(exam?.tags.join(', ') ?? '');
  const [start, setStart] = useState(keyOf(exam?.startAt) || keyOf(new Date()));
  const [end, setEnd] = useState(keyOf(exam?.endAt) || keyOf(new Date(Date.now() + 7 * 86400000)));
  const [drafts, setDrafts] = useState<Draft[]>(() => questions.map(toDraft));

  const total = drafts.reduce((sum, draft) => sum + (Number(draft.points) || 0), 0);
  const patch = (key: string, change: Partial<Draft>) => setDrafts((prev) => prev.map((row) => (row.key === key ? { ...row, ...change } : row)));
  const move = (index: number, delta: number) =>
    setDrafts((prev) => {
      const next = [...prev];
      const target = index + delta;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });

  const validate = (): string | null => {
    if (!title.trim()) return '제목을 입력해 주세요.';
    if (!isDateKey(start) || !isDateKey(end)) return '기간을 YYYY-MM-DD 형식으로 입력해 주세요.';
    if (dateFromKey(end, true) < dateFromKey(start)) return '종료일이 시작일보다 빠릅니다.';
    if (locked) return null;
    if (drafts.length === 0) return '문항을 하나 이상 추가해 주세요.';
    for (const [index, draft] of drafts.entries()) {
      const no = `${index + 1}번`;
      const points = Number(draft.points);
      if (!draft.prompt.trim()) return `${no} 문제를 입력해 주세요.`;
      if (!Number.isInteger(points) || points < 1) return `${no} 배점은 1 이상의 숫자로 입력해 주세요.`;
      if (draft.type === 'multipleChoice') {
        const choices = choicesOf(draft);
        if (choices.length < 2) return `${no} 보기를 두 개 이상 입력해 주세요(한 줄에 하나).`;
        if (draft.correctIndex < 0 || draft.correctIndex >= choices.length) return `${no} 정답 보기를 골라 주세요.`;
      } else if (!draft.accepted.trim()) {
        return `${no} 인정할 정답을 입력해 주세요.`;
      }
    }
    return null;
  };

  const save = () => {
    if (!user) return;
    const problem = validate();
    if (problem) return job.fail(problem);
    const payload: AssessmentQuestion[] = drafts.map((draft, index) => ({
      id: draft.id,
      order: index + 1,
      type: draft.type,
      prompt: draft.prompt.trim(),
      points: Number(draft.points),
      choices: draft.type === 'multipleChoice' ? choicesOf(draft) : [],
      correctIndex: draft.type === 'multipleChoice' ? draft.correctIndex : undefined,
      acceptedAnswers: draft.type === 'shortAnswer' ? draft.accepted.split(',').map((text) => text.trim()).filter(Boolean) : [],
      explanation: draft.explanation.trim() || undefined,
      origin: draft.origin,
      sourceDay: draft.sourceDay,
      sourceTopic: draft.sourceTopic,
    }));
    void job.run(async () => {
      await saveAssessment(
        {
          id: exam?.id ?? '',
          title: title.trim(),
          tags: tags.split(',').map((tag) => tag.trim()).filter(Boolean),
          questionCount: locked ? (exam?.questionCount ?? 0) : payload.length,
          maxScore: locked ? (exam?.maxScore ?? 0) : total,
          startAt: dateFromKey(start),
          endAt: dateFromKey(end, true),
          published: exam?.published ?? false,
        },
        locked ? null : payload,
        user.cohortId,
      );
      goBack();
    });
  };

  return (
    <Screen title={exam ? '평가 수정' : '평가 만들기'}>
      <Card style={{ gap: 12 }}>
        <Field label="제목 *" value={title} onChangeText={setTitle} />
        <Field label="태그" value={tags} onChangeText={setTags} placeholder="쉼표로 구분 (예: 파이썬, 1주차)" />
        <Actions>
          <Half><Field label="시작일" value={start} onChangeText={setStart} placeholder="YYYY-MM-DD" /></Half>
          <Half><Field label="종료일" value={end} onChangeText={setEnd} placeholder="YYYY-MM-DD" /></Half>
        </Actions>
      </Card>

      {locked ? (
        <Callout tone="warning">
          <T variant="caption">이미 {submitted}명이 제출해 문항은 바꿀 수 없습니다. 제목 · 태그 · 기간만 저장됩니다.</T>
        </Callout>
      ) : null}

      <SectionLabel title={`문항 ${drafts.length}개 · 총 ${total}점`} />
      {drafts.map((draft, index) => {
        const choices = choicesOf(draft);
        return (
          <Card key={draft.key} style={{ gap: 10 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <T variant="subtitle" style={{ flex: 1 }}>{index + 1}번 · {TYPE_LABEL[draft.type]}</T>
              {!locked ? (
                <>
                  <Pressable accessibilityLabel="위로" hitSlop={8} onPress={() => move(index, -1)}>
                    <MaterialIcons name="arrow-upward" size={20} color={palette.textSecondary} />
                  </Pressable>
                  <Pressable accessibilityLabel="아래로" hitSlop={8} onPress={() => move(index, 1)}>
                    <MaterialIcons name="arrow-downward" size={20} color={palette.textSecondary} />
                  </Pressable>
                  <Pressable
                    accessibilityLabel="문항 삭제"
                    hitSlop={8}
                    onPress={() => confirmAction('문항 삭제', `${index + 1}번 문항을 지울까요?`, () => setDrafts((prev) => prev.filter((row) => row.key !== draft.key)))}
                  >
                    <MaterialIcons name="delete-outline" size={20} color={palette.error} />
                  </Pressable>
                </>
              ) : null}
            </View>
            {locked ? (
              <>
                <T>{draft.prompt}</T>
                <T variant="caption" tone="secondary">{draft.points}점</T>
              </>
            ) : (
              <>
                <ChipRow
                  options={(Object.keys(TYPE_LABEL) as AssessmentQuestionType[]).map((key) => ({ key, label: TYPE_LABEL[key] }))}
                  value={draft.type}
                  onChange={(type) => patch(draft.key, { type })}
                />
                <Field label="문제" value={draft.prompt} onChangeText={(prompt) => patch(draft.key, { prompt })} multiline />
                <Field label="배점" value={draft.points} onChangeText={(points) => patch(draft.key, { points })} keyboard="numeric" />
                {draft.type === 'multipleChoice' ? (
                  <>
                    <Field label="보기 (한 줄에 하나)" value={draft.choices} onChangeText={(text) => patch(draft.key, { choices: text })} multiline />
                    {choices.length > 0 ? (
                      <ChipRow
                        label="정답"
                        options={choices.map((choice, i) => ({ key: i, label: `${i + 1}. ${choice.length > 14 ? `${choice.slice(0, 14)}…` : choice}` }))}
                        value={draft.correctIndex}
                        onChange={(correctIndex) => patch(draft.key, { correctIndex })}
                      />
                    ) : null}
                  </>
                ) : (
                  <Field label="인정할 정답 (쉼표로 여러 개)" value={draft.accepted} onChangeText={(accepted) => patch(draft.key, { accepted })} />
                )}
                <Field label="해설" value={draft.explanation} onChangeText={(explanation) => patch(draft.key, { explanation })} multiline placeholder="선택" />
              </>
            )}
          </Card>
        );
      })}
      {!locked ? (
        <Actions>
          <Half><Btn label="객관식 추가" icon="add" tone="soft" onPress={() => setDrafts((prev) => [...prev, blank('multipleChoice')])} /></Half>
          <Half><Btn label="단답형 추가" icon="add" tone="soft" onPress={() => setDrafts((prev) => [...prev, blank('shortAnswer')])} /></Half>
        </Actions>
      ) : null}

      <JobNotice notice={job.notice} />
      <Btn label={job.busy ? '저장 중…' : '저장'} icon="save" disabled={job.busy} onPress={save} />
      {exam ? (
        <Btn
          label="평가 삭제"
          tone="danger"
          disabled={job.busy}
          onPress={() =>
            confirmAction('평가 삭제', `「${exam.title}」과 제출 기록을 모두 삭제할까요? 되돌릴 수 없습니다.`, () =>
              void job.run(async () => {
                await deleteAssessment(exam.id);
                router.replace('/(instructor)/exams' as never);
              }),
            )
          }
        />
      ) : null}
    </Screen>
  );
}

export function ExamDetailPage({ id, readOnly = false }: { id: string; readOnly?: boolean }) {
  const { user } = useSession();
  const exam = useAssessments().find((row) => row.id === id);
  const questions = useQuestions(id);
  const submissions = [...useSubmissions(id)].sort((a, b) => a.userDisplayName.localeCompare(b.userDisplayName, 'ko'));
  const students = useUsers().filter((row) => row.role === 'student' && row.cohortId === user?.cohortId && row.isActive !== false);
  const job = useJob();
  const base = readOnly ? '/(admin)' : '/(instructor)';
  if (!exam) return <Screen title="평가" empty emptyText="평가를 찾지 못했습니다." />;

  const phase = phaseOf(exam);
  const submittedIds = new Set(submissions.map((row) => row.userId));
  const missing = students.filter((row) => !submittedIds.has(row.uid));
  const average = submissions.length ? Math.round((submissions.reduce((sum, row) => sum + row.totalScore, 0) / submissions.length) * 10) / 10 : 0;
  const pending = submissions.filter((row) => needsGrading(row, questions)).length;

  return (
    <Screen title={exam.title} onRefresh={refreshBootstrap}>
      <Card style={{ gap: 8 }}>
        <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
          <Badge label={phase.label} tone={phase.tone} />
          <Badge label={exam.published ? '공개' : '비공개'} tone={exam.published ? 'primary' : 'neutral'} />
          {pending > 0 ? <Badge label={`채점 필요 ${pending}명`} tone="warning" /> : null}
        </View>
        <T variant="caption" tone="secondary">{fmt(exam.startAt)} ~ {fmt(exam.endAt)}</T>
        <T>{exam.questionCount}문항 · 만점 {exam.maxScore}점</T>
        <T>제출 {submissions.length} / {students.length}명 · 평균 {average}점</T>
      </Card>
      {!readOnly ? (
        <Card style={{ gap: 10 }}>
          <ToggleRow
            label="학생에게 공개"
            hint="공개해야 학생이 응시할 수 있습니다."
            value={exam.published}
            disabled={job.busy}
            onChange={(value) => void job.run(() => setPublished(exam.id, value))}
          />
          <Btn label="평가 수정" icon="edit" tone="ghost" onPress={() => push(`${base}/exams/${exam.id}/edit`)} />
        </Card>
      ) : null}
      <JobNotice notice={job.notice} />

      <SectionLabel title={`제출 ${submissions.length}명`} />
      {submissions.length === 0 ? (
        <Card><EmptyState icon="assignment" text="아직 제출한 학생이 없습니다." /></Card>
      ) : (
        <ListGroup>
          {submissions.map((row) => (
            <ListItem
              key={row.id}
              title={row.userDisplayName}
              subtitle={`${row.totalScore} / ${exam.maxScore}점${row.submittedAt ? ` · ${fmt(row.submittedAt)}` : ''}`}
              right={needsGrading(row, questions) ? <Badge label="채점 필요" tone="warning" /> : undefined}
              onPress={() => push(`${base}/exams/${id}/sub/${row.id}`)}
            />
          ))}
        </ListGroup>
      )}
      {missing.length > 0 ? (
        <>
          <SectionLabel title={`미제출 ${missing.length}명`} />
          <Card><T tone="secondary">{missing.map((row) => row.displayName).join(', ')}</T></Card>
        </>
      ) : null}

      <SectionLabel title={`문항 ${questions.length}개`} />
      {questions.length > 0 ? (
        <ListGroup>
          {questions.map((question, index) => (
            <ListItem key={question.id} title={`${index + 1}. ${question.prompt}`} subtitle={`${TYPE_LABEL[question.type]} · ${question.points}점`} />
          ))}
        </ListGroup>
      ) : (
        <Muted>문항 정보가 없습니다.</Muted>
      )}
    </Screen>
  );
}

function answerText(question: AssessmentQuestion | undefined, value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '(무응답)';
  if (question?.type === 'multipleChoice' && typeof value === 'number') {
    const choice = question.choices[value];
    return choice !== undefined ? `${value + 1}. ${choice}` : `${value + 1}번`;
  }
  return String(value);
}

export function GradePage({ submissionId, readOnly = false }: { submissionId: string; readOnly?: boolean }) {
  const submission = useSubmissions().find((row) => row.id === submissionId);
  const exam = useAssessments().find((row) => row.id === submission?.assessmentId);
  const questions = useQuestions(submission?.assessmentId);
  const job = useJob();
  const [scores, setScores] = useState<Record<string, string>>({});
  if (!submission) return <Screen title="채점" empty emptyText="제출 기록을 찾지 못했습니다." />;

  // 문항 정보가 없으면 제출된 답만이라도 보여 준다
  const rows: { id: string; question?: AssessmentQuestion }[] =
    questions.length > 0 ? questions.map((question) => ({ id: question.id, question })) : Object.keys(submission.answers).map((id) => ({ id }));

  const save = (question: AssessmentQuestion, raw: string) => {
    const score = Number(raw);
    if (raw.trim() === '' || !Number.isInteger(score) || score < 0 || score > question.points) {
      return job.fail(`0 ~ ${question.points} 사이의 정수로 입력해 주세요.`);
    }
    void job.run(() => gradeAnswer(submission.id, question.id, score), '점수를 저장했습니다.');
  };

  return (
    <Screen title={submission.userDisplayName} onRefresh={refreshBootstrap}>
      <Card style={{ gap: 4 }}>
        <T variant="caption" tone="secondary">{exam?.title ?? '평가'}</T>
        <T variant="hero">{submission.totalScore}<T tone="secondary"> / {exam?.maxScore ?? '-'}점</T></T>
        <T variant="caption" tone="secondary">자동 채점 {submission.autoTotalScore}점{submission.submittedAt ? ` · 제출 ${fmt(submission.submittedAt)}` : ''}</T>
      </Card>
      <JobNotice notice={job.notice} />
      {rows.map(({ id, question }, index) => {
        const entry = submission.answers[id];
        const current = entry?.finalScore ?? entry?.autoScore;
        const value = scores[id] ?? (current !== undefined && current !== null ? String(current) : '');
        const correct =
          question?.type === 'multipleChoice'
            ? question.correctIndex !== undefined ? `${question.correctIndex + 1}. ${question.choices[question.correctIndex] ?? ''}` : '-'
            : question?.acceptedAnswers.join(', ') || '-';
        const gradable = !readOnly && question?.type === 'shortAnswer' && entry !== undefined;
        return (
          <Card key={id} style={{ gap: 8 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <T variant="subtitle" style={{ flex: 1 }}>
                {index + 1}번{question ? ` · ${TYPE_LABEL[question.type]} · ${question.points}점` : ''}
              </T>
              {entry?.isCorrect === true ? <Badge label="정답" tone="success" /> : entry?.isCorrect === false ? <Badge label="오답" tone="error" /> : null}
              {question?.type === 'shortAnswer' && entry && entry.finalScore == null ? <Badge label="채점 전" tone="warning" /> : null}
            </View>
            {question ? <T>{question.prompt}</T> : null}
            <T variant="label" tone="secondary">학생 답</T>
            <T>{answerText(question, entry?.value)}</T>
            {question ? (
              <>
                <T variant="label" tone="secondary">정답</T>
                <T tone="success">{correct}</T>
              </>
            ) : null}
            <T variant="caption" tone="secondary">현재 점수 {current ?? 0}점</T>
            {gradable && question ? (
              <View style={{ gap: 8 }}>
                <Field label={`점수 (0 ~ ${question.points})`} value={value} onChangeText={(text) => setScores((prev) => ({ ...prev, [id]: text }))} keyboard="numeric" />
                <Actions>
                  <Half><Btn label="0점" tone="ghost" disabled={job.busy} onPress={() => { setScores((prev) => ({ ...prev, [id]: '0' })); save(question, '0'); }} /></Half>
                  <Half><Btn label="만점" tone="soft" disabled={job.busy} onPress={() => { setScores((prev) => ({ ...prev, [id]: String(question.points) })); save(question, String(question.points)); }} /></Half>
                  <Half><Btn label="저장" disabled={job.busy} onPress={() => save(question, value)} /></Half>
                </Actions>
              </View>
            ) : null}
          </Card>
        );
      })}
      {rows.length === 0 ? <Card><EmptyState icon="assignment" text="제출된 답이 없습니다." /></Card> : null}
    </Screen>
  );
}
