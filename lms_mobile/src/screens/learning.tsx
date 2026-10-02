import { MaterialIcons } from '@expo/vector-icons';
import { useState } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';
import type { PracticeProblem, PracticeSet, QualExamSchedule } from '@web/domain/types';
import { KIND_LABEL } from '@web/features/practice/practiceLabels';
import { isHidden } from '@web/features/practice/reports';
import { isLessonSet, shortDate, wrongNoteDays, type WrongNoteDay } from '@web/features/practice/review';
import { formatYmd, parseYmd } from '@web/utils/format';

import { useSession } from '../auth/session';
import { useDb, queryClient, queryKeys } from '../data/query';
import { useTheme } from '../theme/Theme';
import { Badge, Callout, Card, EmptyState, Screen, T } from '../ui/kit';

function refresh() {
  void queryClient.invalidateQueries({ queryKey: queryKeys.bootstrap });
}

const WEEKDAY = ['일', '월', '화', '수', '목', '금', '토'];

function dayText(date: string): string {
  const d = new Date(`${date}T00:00:00`);
  return `${date.slice(5).replace('-', '/')} (${WEEKDAY[d.getDay()]})`;
}

// ── 자격 시험 일정 ──────────────────────────────────

/** 이 시험이 언제인지 — 필기 시험일이 있으면 그날, 없으면 실기 시험일 */
const examDayOf = (e: QualExamSchedule) => e.docExamStartDt ?? e.pracExamStartDt;
const haystack = (e: QualExamSchedule) => [e.description, e.qualgbNm, e.qualgbCd, String(e.implSeq), e.implYy].join(' ').toLowerCase();

export function QualPage() {
  const db = useDb();
  const { palette } = useTheme();
  const [query, setQuery] = useState('');
  const exams = db?.qualExams ?? [];
  const syncedAt = db?.qualExamsSyncedAt;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const q = query.trim().toLowerCase();

  const upcoming = exams
    .filter((e) => {
      const day = parseYmd(examDayOf(e));
      return day !== null && day.getTime() >= today.getTime();
    })
    .filter((e) => q === '' || haystack(e).includes(q))
    .sort((a, b) => (parseYmd(examDayOf(a))?.getTime() ?? Infinity) - (parseYmd(examDayOf(b))?.getTime() ?? Infinity));

  const months = new Map<string, QualExamSchedule[]>();
  for (const exam of upcoming) {
    const day = parseYmd(examDayOf(exam));
    const label = day === null ? '일정 미정' : `${day.getFullYear()}년 ${day.getMonth() + 1}월`;
    months.set(label, [...(months.get(label) ?? []), exam]);
  }

  return (
    <Screen title="자격 시험 일정" onRefresh={refresh}>
      <T tone="secondary">다가오는 국가기술자격 시험의 접수 · 시험 · 발표 일정을 확인하세요.</T>
      <View style={[styles.search, { borderColor: palette.border, backgroundColor: palette.surface }]}>
        <MaterialIcons name="search" size={20} color={palette.textHint} />
        <TextInput
          accessibilityLabel="자격명·회차 검색"
          value={query}
          onChangeText={setQuery}
          placeholder="자격명·회차 검색 (예: 정보처리, 기능사)"
          placeholderTextColor={palette.textHint}
          style={{ flex: 1, fontSize: 16, paddingVertical: 8, color: palette.text }}
        />
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center' }}>
        <T variant="subtitle" style={{ flex: 1 }}>{today.getFullYear()}년 · 다가오는 {upcoming.length}건</T>
        {syncedAt ? (
          <T variant="caption" tone="hint">
            {syncedAt.getMonth() + 1}/{syncedAt.getDate()} {String(syncedAt.getHours()).padStart(2, '0')}:{String(syncedAt.getMinutes()).padStart(2, '0')} 기준
          </T>
        ) : null}
      </View>

      {upcoming.length === 0 ? (
        <Card><EmptyState icon="event-busy" text="조건에 맞는 시험 일정이 없습니다" /></Card>
      ) : (
        [...months.entries()].map(([month, items]) => (
          <View key={month} style={{ gap: 8 }}>
            <T variant="title">{month}</T>
            {items.map((exam) => <ExamTimeline key={`${exam.qualgbNm}-${exam.implYy}-${exam.implSeq}`} exam={exam} />)}
          </View>
        ))
      )}
      <T variant="caption" tone="hint" style={{ textAlign: 'center' }}>출처: 한국산업인력공단 공공데이터</T>
    </Screen>
  );
}

function ExamTimeline({ exam }: { exam: QualExamSchedule }) {
  const { palette } = useTheme();
  const stages = [
    { label: '필기 접수', from: exam.docRegStartDt, to: exam.docRegEndDt },
    { label: '필기 시험', from: exam.docExamStartDt, to: exam.docExamEndDt },
    { label: '필기 발표', from: exam.docPassDt, to: exam.docPassDt },
    { label: '실기 접수', from: exam.pracRegStartDt, to: exam.pracRegEndDt },
    { label: '실기 시험', from: exam.pracExamStartDt, to: exam.pracExamEndDt },
    { label: '실기 발표', from: exam.pracPassDt, to: exam.pracPassDt },
  ].filter((s) => s.from !== undefined);
  const day = parseYmd(examDayOf(exam));
  const days = day === null ? null : Math.round((day.getTime() - Date.now()) / 86_400_000);
  const dday = days === null ? '—' : days <= 0 ? 'D-DAY' : `D-${days}`;

  return (
    <Card style={{ gap: 10 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <T variant="subtitle" style={{ flexShrink: 1 }}>{exam.qualgbNm}</T>
        <T variant="caption" tone="secondary">{exam.implYy}년 {exam.implSeq}회</T>
        <Badge label={dday} tone={days !== null && days <= 7 ? 'error' : 'primary'} />
      </View>
      {exam.description ? <T variant="caption" tone="hint">{exam.description}</T> : null}
      <View style={{ gap: 0 }}>
        {stages.map((stage, i) => {
          const start = parseYmd(stage.from);
          const done = start !== null && start.getTime() < Date.now();
          const color = done ? palette.textHint : palette.primary;
          return (
            <View key={stage.label} style={{ flexDirection: 'row', gap: 10 }}>
              <View style={{ alignItems: 'center', width: 12 }}>
                <View style={[styles.dot, { backgroundColor: done ? palette.border : palette.primary }]} />
                {i < stages.length - 1 ? <View style={[styles.rail, { backgroundColor: palette.border }]} /> : null}
              </View>
              <View style={{ flex: 1, paddingBottom: 10, flexDirection: 'row', gap: 8 }}>
                <T variant="caption" style={{ width: 60, fontWeight: '700', color }}>{stage.label}</T>
                <T variant="caption" tone={done ? 'hint' : 'default'} style={{ flex: 1 }}>
                  {formatYmd(stage.from)}
                  {stage.to !== stage.from && stage.to !== undefined ? ` ~ ${formatYmd(stage.to)}` : ''}
                </T>
              </View>
            </View>
          );
        })}
      </View>
    </Card>
  );
}

// ── 오답노트 ────────────────────────────────────────

function setLabel(set: PracticeSet): string {
  return [set.dayLabel, set.title].filter(Boolean).join(' · ');
}

function kindText(problem: PracticeProblem): string {
  const js = problem.packages?.includes('js') ? ' · JS' : '';
  return `${KIND_LABEL[problem.kind] ?? problem.kind}${js}`;
}

export function WrongPage() {
  const { user } = useSession();
  const db = useDb();
  const [showSolved, setShowSolved] = useState(false);
  const sets = (db?.practiceSets ?? []).filter((s) => s.cohortId === user?.cohortId);
  const attempts = (db?.practiceAttempts ?? []).filter((a) => a.uid === user?.uid);
  const reports = db?.practiceReports ?? [];
  const reviews = db?.practiceReviews ?? [];
  const days = wrongNoteDays(sets, attempts, (setId, index) => isHidden(reports, reviews, setId, index));
  const wrongCount = days.reduce((n, d) => n + d.wrong.length, 0);
  const solvedCount = days.reduce((n, d) => n + d.solved.length, 0);
  const shown = days.filter((d) => d.wrong.length > 0 || (showSolved && d.solved.length > 0));

  return (
    <Screen title="오답노트" onRefresh={refresh}>
      <T tone="secondary">복습에서 틀린 문제를 수업 날짜별로 모았어요. 다시 풀어 통과하면 「해결한 문제」로 옮겨져요.</T>
      <Callout tone="info"><T>문제 풀이(연습장)는 PC 웹에서 이어서 할 수 있어요.</T></Callout>

      {days.length === 0 ? (
        <Card><EmptyState icon="task-alt" text="틀린 복습 문제가 없어요. 복습 문제를 풀다 틀리면 여기에 수업 날짜별로 모여요." /></Card>
      ) : (
        <>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <Badge label={`못 푼 문제 ${wrongCount}`} tone="warning" />
            <Badge label={`해결한 문제 ${solvedCount}`} tone="success" />
            <View style={{ flex: 1 }} />
            <SolvedToggle on={showSolved} onToggle={() => setShowSolved((v) => !v)} />
          </View>
          {shown.length === 0 ? (
            <Card><EmptyState icon="celebration" text="틀렸던 문제를 모두 다시 풀었어요. 「해결한 문제도 보기」를 켜면 다시 풀어 맞힌 문제를 볼 수 있어요." /></Card>
          ) : (
            shown.map((day) => <WrongDay key={day.date} day={day} showSolved={showSolved} />)
          )}
        </>
      )}
    </Screen>
  );
}

function SolvedToggle({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  const { palette } = useTheme();
  return (
    <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: on }} onPress={onToggle} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
      <MaterialIcons name={on ? 'check-box' : 'check-box-outline-blank'} size={20} color={on ? palette.primary : palette.textSecondary} />
      <T variant="caption">해결한 문제도 보기</T>
    </Pressable>
  );
}

function WrongDay({ day, showSolved }: { day: WrongNoteDay; showSolved: boolean }) {
  const { palette } = useTheme();
  const solved = showSolved ? day.solved : [];
  return (
    <Card style={{ gap: 10 }}>
      <View style={{ gap: 2 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <T variant="caption" tone="primary" style={{ fontWeight: '700' }}>{dayText(day.date)}</T>
          <View style={{ flex: 1 }} />
          {day.wrong.length > 0 ? <T variant="caption" tone="error">못 푼 {day.wrong.length}</T> : null}
          {day.solved.length > 0 ? <T variant="caption" tone="secondary">해결 {day.solved.length}</T> : null}
        </View>
        <T variant="subtitle">{day.sets.map(setLabel).join(' / ')}</T>
      </View>
      {day.wrong.map((item) => {
        const problem = item.set.problems[item.index];
        return (
          <View key={`${item.set.id}:${item.index}`} style={[styles.item, { borderColor: palette.border }]}>
            <MaterialIcons name="close" size={16} color={palette.error} />
            <View style={{ flex: 1, gap: 2 }}>
              <T variant="caption" tone="secondary">문제 {item.index + 1} · {problem ? kindText(problem) : ''}</T>
              <T numberOfLines={2}>
                {problem?.topic || problem?.prompt || ''}
                {!isLessonSet(item.set) ? <T tone="hint"> · 내가 만든 문제</T> : null}
              </T>
              <T variant="caption" tone="hint">{item.tries}번 틀림 · {shortDate(item.lastTried)}</T>
            </View>
          </View>
        );
      })}
      {solved.map((s) => {
        const problem = s.set.problems[s.index];
        return (
          <View key={`${s.set.id}:${s.index}`} style={[styles.item, { borderColor: palette.border, opacity: 0.75 }]}>
            <MaterialIcons name="check" size={16} color={palette.success} />
            <View style={{ flex: 1, gap: 2 }}>
              <T variant="caption" tone="secondary">문제 {s.index + 1} · {problem ? kindText(problem) : ''}</T>
              <T numberOfLines={2}>{problem?.topic || problem?.prompt || ''}</T>
              <T variant="caption" tone="hint">{s.tries}번 만에 해결</T>
            </View>
          </View>
        );
      })}
    </Card>
  );
}

const styles = StyleSheet.create({
  search: { flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderRadius: 12, paddingHorizontal: 12, minHeight: 44 },
  dot: { width: 10, height: 10, borderRadius: 5, marginTop: 3 },
  rail: { width: 2, flex: 1, marginTop: 2 },
  item: { flexDirection: 'row', gap: 10, borderWidth: 1, borderRadius: 10, padding: 10 },
});
