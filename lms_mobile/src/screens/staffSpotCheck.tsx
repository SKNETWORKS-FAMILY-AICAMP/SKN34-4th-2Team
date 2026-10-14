import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, Text, View, useWindowDimensions } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ABSENT_REASONS, SpotCheckPeriodLabels } from '@web/features/manager/spotCheckLabels';
import type { SeatingGrid, SeatPresenceState, SpotCheck, SpotCheckItem, SpotCheckPeriod, SpotCheckState, User } from '@web/domain/types';

import { deletePresenceCheck, savePresenceCheck } from '../data/attendance';
import { useTheme } from '../theme/Theme';
import { ChipRow, JobNotice, SectionLabel, confirmAction, isDateKey, isTime, useJob } from '../ui/form';
import { SeatGrid } from '../ui/SeatGrid';
import { Badge, Btn, Callout, Card, Chip, EmptyState, Field, T, fmt, todayKey } from '../ui/kit';

/**
 * 불시 자리 점검 — 웹 `features/manager/SpotCheck.tsx` 와 같은 흐름.
 * 오전 · 오후에 불시에 돌며 학생마다 자리에 있는지(유/무) 적고, 점검 시각 · 점검자와 함께 남긴다.
 */

type Marks = Record<string, { state: SpotCheckState; reason?: string }>;

interface StoredDraft {
  id?: string;
  date: string;
  time: string;
  period: SpotCheckPeriod;
  periodTouched: boolean;
  note: string;
  marks: Marks;
}

export interface SpotSeating {
  grid: SeatingGrid;
  seatUserIds: Record<string, string>;
  seatNames: Record<string, string>;
}

const draftKey = (cohortId: string) => `lms_spot_check_draft:${cohortId}`;
const PERIOD_OPTIONS = (['am', 'pm'] as const).map((key) => ({ key, label: SpotCheckPeriodLabels[key] }));
const CUSTOM = '__custom';
const WIDE_MIN = 700;
const PANE_MIN = 240;
const SEAT_COL = 44;
const TOGGLE_COMPACT = 42;

function clockOf(at: Date): string {
  return `${String(at.getHours()).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')}`;
}

function periodOf(hour: number): SpotCheckPeriod {
  return hour < 13 ? 'am' : 'pm';
}

function freshDraft(): StoredDraft {
  const now = new Date();
  return { date: todayKey(now), time: clockOf(now), period: periodOf(now.getHours()), periodTouched: false, note: '', marks: {} };
}

function draftFrom(check: SpotCheck): StoredDraft {
  const marks: Marks = {};
  for (const item of check.items) marks[item.userId] = { state: item.state, reason: item.reason };
  return {
    id: check.id,
    date: todayKey(check.checkedAt),
    time: clockOf(check.checkedAt),
    period: check.period,
    periodTouched: true,
    note: check.note ?? '',
    marks,
  };
}

function timeOf(draft: StoredDraft): Date | null {
  if (!isDateKey(draft.date) || !isTime(draft.time)) return null;
  const [y, m, d] = draft.date.split('-').map(Number);
  const [hh, mm] = draft.time.split(':').map(Number);
  return new Date(y, m - 1, d, hh, mm);
}

/**
 * 가로로 넓게 들면 웹처럼 배치도 · 명단을 나란히 둔다.
 * 위쪽 입력란을 밀어 올리면 나란한 칸이 화면을 꽉 채우고, 명단은 칸 안에서 따로 민다.
 */
export function useWideLayout() {
  const screen = useWindowDimensions();
  const insets = useSafeAreaInsets();
  return {
    wide: screen.width > screen.height && screen.width >= WIDE_MIN,
    paneHeight: Math.max(PANE_MIN, screen.height - insets.top - insets.bottom - 76),
  };
}

const isPreset = (reason?: string) => ABSENT_REASONS.includes(reason as (typeof ABSENT_REASONS)[number]);

export function SpotCheckRunner({
  cohortId,
  roll,
  seating,
  seatLabelOf,
  width,
  editing,
  onSaved,
  onCancelEdit,
}: {
  cohortId: string;
  /** 이름 차례로 정렬된 학생 */
  roll: User[];
  seating?: SpotSeating;
  seatLabelOf: (uid: string) => string;
  /** 배치도가 쓸 수 있는 폭 */
  width: number;
  /** 이력에서 「수정」으로 연 점검 */
  editing?: SpotCheck;
  onSaved(): void;
  onCancelEdit(): void;
}) {
  const { palette } = useTheme();
  const job = useJob();
  const { wide, paneHeight } = useWideLayout();
  const [mapWidth, setMapWidth] = useState(0);
  const [draft, setDraft] = useState<StoredDraft>(() => (editing ? draftFrom(editing) : freshDraft()));
  // 기기에 적어 둔 새 점검을 다 읽기 전에는 덮어쓰지 않는다
  const [loadedFor, setLoadedFor] = useState<string | null>(null);

  useEffect(() => {
    job.clear();
    if (editing) {
      setDraft(draftFrom(editing));
      setLoadedFor(null);
      return;
    }
    let alive = true;
    setLoadedFor(null);
    AsyncStorage.getItem(draftKey(cohortId))
      .then((raw) => (raw ? (JSON.parse(raw) as StoredDraft) : null))
      .catch(() => null)
      .then((saved) => {
        if (!alive) return;
        setDraft(saved && saved.id === undefined ? saved : freshDraft());
        setLoadedFor(cohortId);
      });
    return () => {
      alive = false;
    };
  }, [cohortId, editing]);

  // 새 점검은 중간에 화면을 떠나도 이어서 할 수 있게 기기에 적어 둔다
  useEffect(() => {
    if (loadedFor !== cohortId || draft.id !== undefined) return;
    void AsyncStorage.setItem(draftKey(cohortId), JSON.stringify(draft)).catch(() => undefined);
  }, [cohortId, draft, loadedFor]);

  const marks = draft.marks;
  const present = roll.filter((s) => marks[s.uid]?.state === 'present').length;
  const absent = roll.filter((s) => marks[s.uid]?.state === 'absent').length;
  const unchecked = roll.length - present - absent;

  const setMark = (uid: string, state: SpotCheckState | null, reason?: string) =>
    setDraft((d) => {
      const next = { ...d.marks };
      if (state === null) delete next[uid];
      else next[uid] = { state, reason: state === 'absent' ? (reason ?? d.marks[uid]?.reason) : undefined };
      return { ...d, marks: next };
    });

  // 배치도 칸을 누르면 미확인 → 유 → 무 → 유 … 로 돈다
  const cycle = (uid: string) => setMark(uid, marks[uid]?.state === 'present' ? 'absent' : 'present');

  const presenceOf = (uid: string): SeatPresenceState =>
    marks[uid]?.state === 'present' ? 'confirmed' : marks[uid]?.state === 'absent' ? 'held' : 'unknown';

  const setWhen = (date: string, time: string) =>
    setDraft((d) => {
      const next = { ...d, date, time };
      const at = timeOf(next);
      return at && !d.periodTouched ? { ...next, period: periodOf(at.getHours()) } : next;
    });

  const now = () => {
    const at = new Date();
    setWhen(todayKey(at), clockOf(at));
  };

  const markRest = () =>
    setDraft((d) => {
      const next = { ...d.marks };
      for (const s of roll) if (next[s.uid] === undefined) next[s.uid] = { state: 'present' };
      return { ...d, marks: next };
    });

  const reset = () =>
    confirmAction('초기화', '이 점검에 적은 유/무를 모두 지울까요?', () => setDraft((d) => (d.id === undefined ? freshDraft() : { ...d, marks: {} })), '초기화');

  const save = () => {
    const at = timeOf(draft);
    if (!at) {
      job.fail('점검 날짜(YYYY-MM-DD)와 시각(HH:MM)을 확인해 주세요.');
      return;
    }
    if (unchecked > 0) {
      job.fail(`아직 확인하지 않은 학생이 ${unchecked}명 있습니다. 「남은 학생 모두 유」를 누르거나 하나씩 표시해 주세요.`);
      return;
    }
    const items: SpotCheckItem[] = roll.map((s) => ({
      userId: s.uid,
      state: marks[s.uid].state,
      reason: marks[s.uid].state === 'absent' ? marks[s.uid].reason?.trim() || undefined : undefined,
    }));
    const isNew = draft.id === undefined;
    void job
      .run(() => savePresenceCheck(cohortId, { id: draft.id, checkedAt: at, period: draft.period, note: draft.note.trim() || undefined, items }))
      .then((ok) => {
        if (!ok) return;
        if (isNew) {
          void AsyncStorage.removeItem(draftKey(cohortId)).catch(() => undefined);
          setDraft(freshDraft());
        }
        onSaved();
      });
  };

  const saveLabel = job.busy ? '저장 중' : draft.id === undefined ? '점검 완료 · 저장' : '수정 저장';

  const editingNotice =
    draft.id !== undefined ? (
      <Callout tone="warning">
        <View style={{ gap: 8 }}>
          <T>{fmt(editing?.checkedAt)} 점검을 고치고 있습니다.</T>
          <View style={{ alignSelf: 'flex-start' }}>
            <Chip label="새 점검으로" onPress={onCancelEdit} />
          </View>
        </View>
      </Callout>
    ) : null;

  const counts = (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
      <Badge label={`유 ${present}`} tone="success" />
      <Badge label={`무 ${absent}`} tone="warning" />
      <Badge label={`미확인 ${unchecked}`} tone="neutral" />
    </View>
  );

  const seatMap = (mapW: number) =>
    seating === undefined ? null : (
      <SeatGrid
        grid={seating.grid}
        seatUserIds={seating.seatUserIds}
        seatNames={seating.seatNames}
        markOf={presenceOf}
        markLabels={{ confirmed: '유', held: '무' }}
        onSeatPress={cycle}
        width={mapW}
      />
    );

  const rosterRow = (s: User, i: number) => {
    const mark = marks[s.uid];
    const custom = mark?.state === 'absent' && mark.reason !== undefined && mark.reason !== '' && !isPreset(mark.reason);
    return (
      <View
        key={s.uid}
        style={{
          gap: 8,
          paddingVertical: wide ? 8 : 10,
          paddingHorizontal: wide ? 12 : 0,
          borderTopWidth: i === 0 ? 0 : 1,
          borderTopColor: palette.divider,
          backgroundColor: wide && mark === undefined ? palette.surfaceVariant : undefined,
        }}
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          {wide ? (
            <>
              <T style={{ flex: 1, fontWeight: mark === undefined ? '700' : '500' }} numberOfLines={1}>{s.displayName}</T>
              <T variant="caption" tone="hint" style={{ width: SEAT_COL }} numberOfLines={1}>{seatLabelOf(s.uid)}</T>
            </>
          ) : (
            <View style={{ flex: 1, gap: 2 }}>
              <T style={{ fontWeight: mark === undefined ? '700' : '500' }} numberOfLines={1}>{s.displayName}</T>
              <T variant="caption" tone="hint">{seatLabelOf(s.uid)}</T>
            </View>
          )}
          <Toggle
            label="유"
            compact={wide}
            on={mark?.state === 'present'}
            color={palette.success}
            onPress={() => setMark(s.uid, mark?.state === 'present' ? null : 'present')}
          />
          <Toggle
            label="무"
            compact={wide}
            on={mark?.state === 'absent'}
            color={palette.warning}
            onPress={() => setMark(s.uid, mark?.state === 'absent' ? null : 'absent')}
          />
        </View>
        {mark?.state === 'absent' ? (
          <View style={{ gap: 8 }}>
            <ChipRow
              options={[
                { key: '', label: '사유 없음' },
                ...ABSENT_REASONS.map((r) => ({ key: r as string, label: r })),
                { key: CUSTOM, label: '직접 입력' },
              ]}
              value={custom ? CUSTOM : (mark.reason ?? '')}
              onChange={(key) => setMark(s.uid, 'absent', key === CUSTOM ? ' ' : key)}
            />
            {custom ? (
              <Field
                label="사유"
                value={mark.reason?.trimStart() ?? ''}
                placeholder="사유"
                onChangeText={(value) => setMark(s.uid, 'absent', value.slice(0, 100) || ' ')}
              />
            ) : null}
          </View>
        ) : null}
      </View>
    );
  };

  if (wide) {
    return (
      <>
        {editingNotice}

        <Card style={{ paddingVertical: 12 }}>
          <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 10 }}>
            <View style={{ width: 132 }}>
              <Field label="점검 날짜" value={draft.date} placeholder="YYYY-MM-DD" onChangeText={(value) => setWhen(value, draft.time)} />
            </View>
            <View style={{ width: 84 }}>
              <Field label="시각" value={draft.time} placeholder="HH:MM" onChangeText={(value) => setWhen(draft.date, value)} />
            </View>
            <View style={{ paddingBottom: 6 }}>
              <Chip label="지금" onPress={now} />
            </View>
            <View style={{ gap: 6 }}>
              <T variant="label" tone="secondary">구분</T>
              <View style={{ flexDirection: 'row', gap: 6, paddingBottom: 6 }}>
                {PERIOD_OPTIONS.map((option) => (
                  <Chip
                    key={option.key}
                    label={option.label}
                    selected={draft.period === option.key}
                    onPress={() => setDraft((d) => ({ ...d, period: option.key, periodTouched: true }))}
                  />
                ))}
              </View>
            </View>
            <View style={{ flex: 1, minWidth: 140 }}>
              <Field label="메모" value={draft.note} placeholder="예: 3교시 중 · 특강 진행 중" onChangeText={(note) => setDraft((d) => ({ ...d, note }))} />
            </View>
          </View>
        </Card>

        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View style={{ flex: 1 }}>{counts}</View>
          <Btn label="남은 학생 모두 유" tone="soft" disabled={unchecked === 0} onPress={markRest} />
          <Btn label="초기화" tone="ghost" onPress={reset} />
          <Btn label={saveLabel} icon="check" disabled={job.busy || roll.length === 0} onPress={save} />
        </View>
        <JobNotice notice={job.notice} />

        <View style={{ flexDirection: 'row', gap: 12, height: paneHeight }}>
          <Card style={{ flex: 11, padding: 0, gap: 0, overflow: 'hidden' }}>
            <PaneHead title="좌석 배치" hint="칸을 누를 때마다 유 → 무" />
            {seating === undefined ? (
              <EmptyState icon="event-seat" text="확정된 좌석 배치가 없습니다. 오른쪽 명단에서 표시해 주세요." />
            ) : (
              <ScrollView
                nestedScrollEnabled
                contentContainerStyle={{ paddingHorizontal: 8, paddingVertical: 12 }}
                onLayout={(e) => setMapWidth(e.nativeEvent.layout.width)}
              >
                {mapWidth > 0 ? seatMap(mapWidth - 16) : null}
              </ScrollView>
            )}
          </Card>

          <Card style={{ flex: 9, padding: 0, gap: 0, overflow: 'hidden' }}>
            <View
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                gap: 10,
                paddingHorizontal: 12,
                paddingVertical: 10,
                borderBottomWidth: 1,
                borderBottomColor: palette.divider,
              }}
            >
              <T variant="label" tone="secondary" style={{ flex: 1 }}>이름</T>
              <T variant="label" tone="secondary" style={{ width: SEAT_COL }}>좌석</T>
              <T variant="label" tone="secondary" style={{ width: TOGGLE_COMPACT * 2 + 10, textAlign: 'center' }}>유/무</T>
            </View>
            {roll.length === 0 ? (
              <EmptyState icon="groups" text="이 기수에 학생이 없습니다." />
            ) : (
              <ScrollView nestedScrollEnabled keyboardShouldPersistTaps="handled">
                {roll.map(rosterRow)}
              </ScrollView>
            )}
          </Card>
        </View>
      </>
    );
  }

  return (
    <>
      {editingNotice}

      <Card style={{ gap: 12 }}>
        <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 8 }}>
          <View style={{ flex: 3 }}>
            <Field label="점검 날짜" value={draft.date} placeholder="YYYY-MM-DD" onChangeText={(value) => setWhen(value, draft.time)} />
          </View>
          <View style={{ flex: 2 }}>
            <Field label="시각" value={draft.time} placeholder="HH:MM" onChangeText={(value) => setWhen(draft.date, value)} />
          </View>
          <View style={{ paddingBottom: 6 }}>
            <Chip label="지금" onPress={now} />
          </View>
        </View>
        <ChipRow
          label="구분"
          options={PERIOD_OPTIONS}
          value={draft.period}
          onChange={(period) => setDraft((d) => ({ ...d, period, periodTouched: true }))}
        />
        <Field label="메모" value={draft.note} placeholder="예: 3교시 중 · 특강 진행 중" onChangeText={(note) => setDraft((d) => ({ ...d, note }))} />
      </Card>

      {counts}
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <View style={{ flex: 1 }}>
          <Btn label="남은 학생 모두 유" tone="soft" disabled={unchecked === 0} onPress={markRest} />
        </View>
        <View style={{ flex: 1 }}>
          <Btn label="초기화" tone="ghost" onPress={reset} />
        </View>
      </View>
      <Btn label={saveLabel} icon="check" disabled={job.busy || roll.length === 0} onPress={save} />
      <JobNotice notice={job.notice} />

      <SectionLabel title="좌석 배치" right={<T variant="caption" tone="hint">칸을 누를 때마다 유 → 무</T>} />
      {seating === undefined ? (
        <Card><EmptyState icon="event-seat" text="확정된 좌석 배치가 없습니다. 아래 명단에서 표시해 주세요." /></Card>
      ) : (
        <Card style={{ paddingHorizontal: 8, paddingVertical: 16 }}>{seatMap(width)}</Card>
      )}

      <SectionLabel title="명단" />
      {roll.length === 0 ? (
        <Card><EmptyState icon="groups" text="이 기수에 학생이 없습니다." /></Card>
      ) : (
        <Card style={{ paddingVertical: 4, gap: 0 }}>{roll.map(rosterRow)}</Card>
      )}
    </>
  );
}

export function PaneHead({ title, hint }: { title: string; hint?: string }) {
  const { palette } = useTheme();
  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        paddingHorizontal: 12,
        paddingVertical: 10,
        borderBottomWidth: 1,
        borderBottomColor: palette.divider,
      }}
    >
      <T variant="subtitle" style={{ flex: 1 }}>{title}</T>
      {hint ? <T variant="caption" tone="hint" numberOfLines={1}>{hint}</T> : null}
    </View>
  );
}

export function Toggle({
  label,
  on,
  color,
  compact,
  onPress,
}: {
  label: string;
  on: boolean;
  color: string;
  compact?: boolean;
  onPress: () => void;
}) {
  const { palette } = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: on }}
      accessibilityLabel={label}
      hitSlop={4}
      onPress={onPress}
      style={({ pressed }) => ({
        width: compact ? TOGGLE_COMPACT : 48,
        height: compact ? 34 : 40,
        borderRadius: 10,
        borderWidth: 1.5,
        alignItems: 'center',
        justifyContent: 'center',
        borderColor: on ? color : palette.border,
        backgroundColor: on ? color : palette.surface,
        opacity: pressed ? 0.75 : 1,
      })}
    >
      <Text style={{ fontSize: 15, fontWeight: '700', color: on ? '#fff' : palette.textSecondary }}>{label}</Text>
    </Pressable>
  );
}

export function SpotCheckHistory({
  checks,
  students,
  onEdit,
}: {
  /** 이 기수의 점검 */
  checks: SpotCheck[];
  students: User[];
  onEdit(check: SpotCheck): void;
}) {
  const job = useJob();
  const nameOf = useMemo(() => new Map(students.map((s) => [s.uid, s.displayName])), [students]);
  const [to, setTo] = useState(() => todayKey());
  const [from, setFrom] = useState(() => todayKey(new Date(Date.now() - 6 * 86_400_000)));
  const valid = isDateKey(from) && isDateKey(to);

  const shown = checks
    .filter((c) => {
      if (!valid) return true;
      const key = todayKey(c.checkedAt);
      return key >= from && key <= to;
    })
    .sort((a, b) => b.checkedAt.getTime() - a.checkedAt.getTime());

  const remove = (check: SpotCheck) =>
    confirmAction('점검 기록 삭제', `${fmt(check.checkedAt)} 점검 기록을 지울까요? 되돌릴 수 없습니다.`, () => {
      void job.run(() => deletePresenceCheck(check.id));
    });

  return (
    <>
      <Card style={{ gap: 8 }}>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <View style={{ flex: 1 }}>
            <Field label="시작일" value={from} placeholder="YYYY-MM-DD" onChangeText={setFrom} />
          </View>
          <View style={{ flex: 1 }}>
            <Field label="종료일" value={to} placeholder="YYYY-MM-DD" onChangeText={setTo} />
          </View>
        </View>
        {!valid ? <T variant="caption" tone="error">날짜는 YYYY-MM-DD 로 적어 주세요. 그동안은 모든 점검을 보여 줍니다.</T> : null}
        <T variant="caption" tone="hint">Excel · Word · PDF 내려받기는 웹에서 할 수 있습니다.</T>
      </Card>
      <JobNotice notice={job.notice} />

      {shown.length === 0 ? (
        <Card><EmptyState icon="fact-check" text="이 기간에 저장된 점검이 없습니다." /></Card>
      ) : (
        shown.map((check) => {
          const absentItems = check.items.filter((item) => item.state === 'absent');
          return (
            <Card key={check.id} style={{ gap: 8 }}>
              <T variant="subtitle">{fmt(check.checkedAt)}</T>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
                <Badge label={SpotCheckPeriodLabels[check.period]} tone="info" />
                <Badge label={`유 ${check.items.length - absentItems.length}`} tone="success" />
                <Badge label={`무 ${absentItems.length}`} tone="warning" />
                {check.checkedByName ? <T variant="caption" tone="secondary">점검 {check.checkedByName}</T> : null}
              </View>
              {check.note ? <T variant="caption" tone="secondary">메모: {check.note}</T> : null}
              {absentItems.length > 0 ? (
                <T tone="warning">
                  {absentItems.map((item) => `${nameOf.get(item.userId) ?? '(퇴소)'}${item.reason ? `(${item.reason})` : ''}`).join(' · ')}
                </T>
              ) : (
                <T variant="caption" tone="hint">모두 자리에 있었습니다.</T>
              )}
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <View style={{ flex: 1 }}>
                  <Btn label="수정" tone="ghost" icon="edit" onPress={() => onEdit(check)} />
                </View>
                <View style={{ flex: 1 }}>
                  <Btn label="삭제" tone="danger" icon="delete-outline" disabled={job.busy} onPress={() => remove(check)} />
                </View>
              </View>
            </Card>
          );
        })
      )}
    </>
  );
}
