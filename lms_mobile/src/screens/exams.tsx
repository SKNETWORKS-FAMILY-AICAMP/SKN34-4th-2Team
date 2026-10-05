import { MaterialIcons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Alert, Pressable, StyleSheet, TextInput, View } from 'react-native';
import type { Assessment, AssessmentQuestion } from '@web/domain/types';
import { toTime } from '@web/utils/format';

import { useSession } from '../auth/session';
import { fetchReview, fetchTake, submitAssessment, useAssessments, useSubmissions } from '../data/assessments';
import { queryClient, queryKeys } from '../data/query';
import { useTheme } from '../theme/Theme';
import { Badge, Btn, Callout, Card, EmptyState, Field, Screen, StatTile, T, fmt, goBack } from '../ui/kit';

type WindowState = 'before' | 'open' | 'closed';

function windowState(assessment: Assessment): WindowState {
  const now = Date.now();
  if (now < toTime(assessment.startAt)) return 'before';
  if (now > toTime(assessment.endAt)) return 'closed';
  return 'open';
}

function refresh() {
  return queryClient.invalidateQueries({ queryKey: queryKeys.bootstrap });
}

function go(path: string, replace = false) {
  if (replace) router.replace(path as never);
  else router.push(path as never);
}

// ── 목록 ────────────────────────────────────────

export function ExamsPage() {
  const { user } = useSession();
  const { palette } = useTheme();
  const exams = useAssessments().filter((exam) => exam.published);
  const mine = useSubmissions().filter((row) => row.userId === user?.uid);
  const [query, setQuery] = useState('');
  const [notice, setNotice] = useState<Record<string, string>>({});
  const q = query.trim().toLowerCase();
  const rows = q === '' ? exams : exams.filter((exam) => exam.title.toLowerCase().includes(q));

  return (
    <Screen title="성취도평가" onRefresh={refresh}>
      <T tone="secondary">공개된 평가를 기간 안에 응시하고 결과를 확인하세요.</T>
      <View style={[styles.search, { borderColor: palette.border, backgroundColor: palette.surface }]}>
        <MaterialIcons name="search" size={20} color={palette.textHint} />
        <TextInput
          accessibilityLabel="제목 검색"
          value={query}
          onChangeText={setQuery}
          placeholder="제목 검색"
          placeholderTextColor={palette.textHint}
          style={{ flex: 1, fontSize: 16, paddingVertical: 8, color: palette.text }}
        />
      </View>

      {rows.length === 0 ? (
        <Card><EmptyState icon="assignment" text="공개된 평가가 없습니다" /></Card>
      ) : (
        rows.map((exam) => {
          const submission = mine.find((row) => row.assessmentId === exam.id);
          const state = windowState(exam);
          const done = submission !== undefined;
          const blocked = state === 'before' ? '아직 응시 기간이 아닙니다.' : state === 'closed' && !done ? '종료된 평가이며 응시 기록이 없습니다.' : '';
          const tileColor = state === 'closed' ? palette.textHint : state === 'before' ? palette.warning : palette.primary;
          return (
            <Card
              key={exam.id}
              onPress={() => {
                if (blocked) setNotice((prev) => ({ ...prev, [exam.id]: blocked }));
                else go(done ? `/(student)/exams/${exam.id}/result` : `/(student)/exams/${exam.id}/take`);
              }}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}
            >
              <View style={[styles.tile, { backgroundColor: `${tileColor}1f` }]}>
                <T variant="caption" style={{ color: tileColor, fontWeight: '700' }}>
                  {state === 'closed' ? '종료' : state === 'before' ? '예정' : '진행중'}
                </T>
                <T variant="title" style={{ color: tileColor }}>{exam.questionCount}</T>
              </View>
              <View style={{ flex: 1, gap: 3 }}>
                {exam.tags.length > 0 ? (
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>
                    {exam.tags.map((tag) => <Badge key={tag} label={tag} tone="neutral" />)}
                  </View>
                ) : null}
                <T variant="subtitle" numberOfLines={2}>{exam.title}</T>
                <T variant="caption" tone="hint">{exam.questionCount}문제 · {exam.maxScore}점 · {fmt(exam.startAt)} ~ {fmt(exam.endAt)}</T>
                {notice[exam.id] ? <T variant="caption" tone="error">{notice[exam.id]}</T> : null}
              </View>
              {done ? (
                <View style={{ alignItems: 'flex-end', gap: 4 }}>
                  <T variant="subtitle">{submission.totalScore}점</T>
                  <Badge label="완료" tone="success" />
                </View>
              ) : null}
            </Card>
          );
        })
      )}
    </Screen>
  );
}

// ── 응시 ────────────────────────────────────────

export function ExamTakePage({ id }: { id: string }) {
  const { user } = useSession();
  const { palette } = useTheme();
  const exam = useAssessments().find((row) => row.id === id);
  const submission = useSubmissions(id).find((row) => row.userId === user?.uid);
  const [questions, setQuestions] = useState<AssessmentQuestion[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, number | string | null>>({});
  const [index, setIndex] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const canTake = exam !== undefined && submission === undefined && exam.published && windowState(exam) === 'open';

  useEffect(() => {
    if (!canTake) return;
    let alive = true;
    fetchTake(id)
      .then((rows) => alive && setQuestions(rows))
      .catch((err: unknown) => alive && setLoadError(err instanceof Error ? err.message : '문항을 불러오지 못했습니다.'));
    return () => {
      alive = false;
    };
  }, [id, canTake]);

  if (!exam) return <Screen title="응시" empty emptyText="평가를 찾을 수 없습니다" />;
  if (submission) {
    return (
      <Screen title={exam.title}>
        <Card style={{ alignItems: 'center' }}>
          <EmptyState icon="task-alt" text="이미 응시한 평가입니다." />
          <Btn label="결과 보기" onPress={() => go(`/(student)/exams/${id}/result`, true)} />
        </Card>
      </Screen>
    );
  }
  const state = windowState(exam);
  if (!exam.published || state !== 'open') {
    const message = !exam.published ? '공개되지 않은 평가입니다.' : state === 'before' ? '아직 응시 기간이 아닙니다.' : '종료된 평가이며 응시 기록이 없습니다.';
    return (
      <Screen title={exam.title}>
        <Card style={{ alignItems: 'center' }}>
          <EmptyState icon="schedule" text={message} />
          <Btn label="목록으로" tone="ghost" onPress={goBack} />
        </Card>
      </Screen>
    );
  }
  if (questions === null) return <Screen title={exam.title} loading={!loadError} error={loadError} />;

  const question = questions[index];
  const answered = questions.filter((q) => answers[q.id] !== undefined && answers[q.id] !== '' && answers[q.id] !== null).length;
  const last = index >= questions.length - 1;

  const submit = () => {
    const raw: Record<string, number | string | null> = {};
    for (const q of questions) raw[q.id] = answers[q.id] ?? (q.type === 'multipleChoice' ? null : '');
    setSubmitting(true);
    setSubmitError(null);
    void submitAssessment(id, raw)
      .then(() => go(`/(student)/exams/${id}/result`, true))
      .catch((err: unknown) => setSubmitError(err instanceof Error ? err.message : '제출하지 못했습니다.'))
      .finally(() => setSubmitting(false));
  };
  const finish = () => {
    if (answered < questions.length) {
      Alert.alert('미응답 문항 확인', `${questions.length - answered}문항이 비어 있습니다. 그대로 제출할까요?`, [
        { text: '계속 풀기', style: 'cancel' },
        { text: '그대로 제출', onPress: submit },
      ]);
      return;
    }
    Alert.alert('제출', '제출하면 다시 고칠 수 없습니다. 제출할까요?', [
      { text: '닫기', style: 'cancel' },
      { text: '제출', onPress: submit },
    ]);
  };

  return (
    <Screen title={exam.title}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <T tone="secondary" style={{ flex: 1 }}>{questions.length}문항 · {exam.maxScore}점</T>
        <Badge label={`${answered} / ${questions.length} 응답`} tone="primary" />
      </View>
      <View style={[styles.progress, { backgroundColor: palette.surfaceVariant }]}>
        <View style={{ width: `${questions.length ? (answered / questions.length) * 100 : 0}%`, height: '100%', backgroundColor: palette.primary, borderRadius: 3 }} />
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
        {questions.map((q, i) => {
          const filled = answers[q.id] !== undefined && answers[q.id] !== '' && answers[q.id] !== null;
          const on = i === index;
          return (
            <Pressable
              key={q.id}
              accessibilityLabel={`${i + 1}번 문항`}
              onPress={() => setIndex(i)}
              style={[
                styles.qdot,
                {
                  borderColor: on ? palette.primary : palette.border,
                  backgroundColor: filled ? palette.primaryLight : palette.surface,
                },
              ]}
            >
              <T variant="caption" tone={on ? 'primary' : 'default'} style={{ fontWeight: '700' }}>{i + 1}</T>
            </Pressable>
          );
        })}
      </View>

      {question === undefined ? (
        <Card><EmptyState text="문항이 없습니다" /></Card>
      ) : (
        <Card style={{ gap: 12 }}>
          <T variant="subtitle">{index + 1}. {question.prompt}</T>
          <T variant="caption" tone="hint">배점 {question.points}점</T>
          {question.type === 'multipleChoice' ? (
            <View style={{ gap: 8 }}>
              {question.choices.map((choice, i) => {
                const on = answers[question.id] === i;
                return (
                  <Pressable
                    key={`${choice}-${i}`}
                    accessibilityRole="radio"
                    accessibilityState={{ selected: on }}
                    onPress={() => setAnswers((prev) => ({ ...prev, [question.id]: i }))}
                    style={[styles.choice, { borderColor: on ? palette.primary : palette.border, backgroundColor: on ? palette.primaryLight : palette.surface }]}
                  >
                    <MaterialIcons name={on ? 'radio-button-checked' : 'radio-button-unchecked'} size={20} color={on ? palette.primary : palette.textHint} />
                    <T style={{ flex: 1 }}>{choice}</T>
                  </Pressable>
                );
              })}
            </View>
          ) : (
            <Field
              label="답"
              value={String(answers[question.id] ?? '')}
              onChangeText={(value) => setAnswers((prev) => ({ ...prev, [question.id]: value }))}
              placeholder="답을 입력하세요"
            />
          )}
          {submitError ? <Callout tone="error"><T>제출하지 못했습니다 · {submitError}</T></Callout> : null}
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <View style={{ flex: 1 }}><Btn label="이전" tone="ghost" disabled={index === 0} onPress={() => setIndex((i) => i - 1)} /></View>
            <View style={{ flex: 1 }}>
              {last ? (
                <Btn label={submitting ? '제출 중…' : '제출하기'} disabled={submitting} onPress={finish} />
              ) : (
                <Btn label="다음" onPress={() => setIndex((i) => i + 1)} />
              )}
            </View>
          </View>
        </Card>
      )}
    </Screen>
  );
}

// ── 결과 ────────────────────────────────────────

type Review = Awaited<ReturnType<typeof fetchReview>>;

export function ExamResultPage({ id }: { id: string }) {
  const { user } = useSession();
  const { palette } = useTheme();
  const exam = useAssessments().find((row) => row.id === id);
  const mine = useSubmissions(id).find((row) => row.userId === user?.uid);
  const [review, setReview] = useState<Review | undefined>(undefined);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!user || mine === undefined) return;
    let alive = true;
    fetchReview(id, user)
      .then((r) => alive && setReview(r))
      .catch((err: unknown) => alive && setLoadError(err instanceof Error ? err.message : '결과를 불러오지 못했습니다.'));
    return () => {
      alive = false;
    };
  }, [id, mine?.id, mine?.totalScore]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!exam || !mine) return <Screen title="결과" empty emptyText="응시 기록이 없습니다" onRefresh={refresh} />;
  if (!review) return <Screen title={`${exam.title} 결과`} loading={!loadError} error={loadError ? `결과를 불러오지 못했습니다 · ${loadError}` : null} />;

  const { questions, submission } = review;
  const correct = questions.filter((q) => submission.answers[q.id]?.isCorrect === true).length;
  const maxScore = exam.maxScore || questions.reduce((sum, q) => sum + q.points, 0);
  const rate = questions.length ? Math.round((correct / questions.length) * 100) : 0;

  return (
    <Screen title={`${exam.title} 결과`}>
      <T tone="secondary">{questions.length}문항 · {fmt(submission.submittedAt)} 제출</T>
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <StatTile icon="emoji-events" label={`점수 (${maxScore}점 만점)`} value={`${submission.totalScore}점`} />
        <StatTile icon="check-circle" label="맞힌 문항" value={`${correct} / ${questions.length}`} tone={correct === questions.length ? 'success' : 'warning'} />
      </View>
      <StatTile icon="percent" label="정답률" value={`${rate}%`} tone="info" />

      {questions.map((q, i) => {
        const entry = submission.answers[q.id];
        const isCorrect = entry?.isCorrect === true;
        const given = q.type === 'multipleChoice' ? q.choices[Number(entry?.value ?? -1)] ?? '무응답' : String(entry?.value ?? '') || '무응답';
        const answer = q.type === 'multipleChoice' ? q.choices[q.correctIndex ?? 0] : q.acceptedAnswers.join(' / ');
        return (
          <Card key={q.id} style={{ gap: 8 }}>
            <T variant="subtitle">{i + 1}. {q.prompt}</T>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Badge label={isCorrect ? '정답' : '오답'} tone={isCorrect ? 'success' : 'error'} />
              <T variant="caption" tone="hint">{entry?.finalScore ?? 0} / {q.points}점</T>
            </View>
            <View style={{ gap: 4 }}>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <T variant="caption" tone="secondary" style={{ width: 40 }}>내 답</T>
                <T style={{ flex: 1, color: isCorrect ? palette.success : palette.error }}>{given}</T>
              </View>
              {!isCorrect && answer ? (
                <View style={{ flexDirection: 'row', gap: 8 }}>
                  <T variant="caption" tone="secondary" style={{ width: 40 }}>정답</T>
                  <T style={{ flex: 1, color: palette.success }}>{answer}</T>
                </View>
              ) : null}
            </View>
            {q.explanation ? <Callout tone="info"><T>{q.explanation}</T></Callout> : null}
            {!isCorrect && q.sourceDay !== undefined ? (
              <T variant="caption" tone="hint">근거 수업 · {q.sourceDay}일차{q.sourceTopic ? ` · ${q.sourceTopic}` : ''} — 학습실에서 복습하세요</T>
            ) : null}
            {entry?.comment ? <Callout tone="info"><T>채점 의견 · {entry.comment}</T></Callout> : null}
          </Card>
        );
      })}
      <Btn label="목록으로" tone="ghost" onPress={() => go('/(student)/exams', true)} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  search: { flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderRadius: 12, paddingHorizontal: 12, minHeight: 44 },
  tile: { width: 60, height: 60, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  progress: { height: 6, borderRadius: 3, overflow: 'hidden' },
  qdot: { width: 36, height: 36, borderRadius: 10, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  choice: { flexDirection: 'row', alignItems: 'center', gap: 10, borderWidth: 1, borderRadius: 12, padding: 12, minHeight: 48 },
});
