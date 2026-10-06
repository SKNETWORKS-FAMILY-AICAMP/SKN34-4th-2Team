import { useState, type ReactNode } from 'react';
import { Alert, Platform, ScrollView, Switch, View } from 'react-native';
import type { User } from '@web/domain/types';

import { useTheme } from '../theme/Theme';
import { Callout, Chip, Field, T } from './kit';

/** 되돌릴 수 없는 일 앞에서 한 번 더 묻는다. 웹(react-native-web)의 Alert 는 단추를 못 그려 confirm 으로 대신한다. */
export function confirmAction(title: string, message: string, onConfirm: () => void, label = '삭제'): void {
  if (Platform.OS === 'web') {
    if (globalThis.confirm?.(`${title}\n${message}`)) onConfirm();
    return;
  }
  Alert.alert(title, message, [
    { text: '취소', style: 'cancel' },
    { text: label, style: label === '삭제' || label.includes('취소') ? 'destructive' : 'default', onPress: onConfirm },
  ]);
}

export function errorText(error: unknown, fallback = '처리하지 못했습니다.'): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export type Notice = { tone: 'success' | 'error'; text: string } | null;

/** 저장 · 삭제 같은 서버 일 하나 — 도는 동안 단추를 막고, 끝나면 결과를 한 줄로 알린다 */
export function useJob() {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const run = async (work: () => Promise<unknown>, success?: string): Promise<boolean> => {
    if (busy) return false;
    setBusy(true);
    setNotice(null);
    try {
      await work();
      if (success) setNotice({ tone: 'success', text: success });
      return true;
    } catch (error) {
      setNotice({ tone: 'error', text: errorText(error) });
      return false;
    } finally {
      setBusy(false);
    }
  };
  const fail = (text: string) => setNotice({ tone: 'error', text });
  return { busy, notice, run, fail, clear: () => setNotice(null) };
}

export function JobNotice({ notice }: { notice: Notice }) {
  if (!notice) return null;
  return (
    <Callout tone={notice.tone}>
      <T tone={notice.tone}>{notice.text}</T>
    </Callout>
  );
}

export function ToggleRow({
  label,
  hint,
  value,
  onChange,
  disabled,
}: {
  label: string;
  hint?: string;
  value: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  const { palette } = useTheme();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 44 }}>
      <View style={{ flex: 1, gap: 2 }}>
        <T variant="subtitle" style={{ fontSize: 15 }}>{label}</T>
        {hint ? <T variant="caption" tone="secondary">{hint}</T> : null}
      </View>
      <Switch
        accessibilityLabel={label}
        value={value}
        disabled={disabled}
        onValueChange={onChange}
        trackColor={{ true: palette.primary, false: palette.border }}
        thumbColor="#fff"
      />
    </View>
  );
}

/** 여럿 중 하나를 고르는 칩 줄 — 넘치면 가로로 민다 */
export function ChipRow<K extends string | number>({
  label,
  options,
  value,
  onChange,
}: {
  label?: string;
  options: { key: K; label: string }[];
  value: K;
  onChange: (key: K) => void;
}) {
  return (
    <View style={{ gap: 6 }}>
      {label ? <T variant="label" tone="secondary">{label}</T> : null}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }} keyboardShouldPersistTaps="handled">
        {options.map((option) => (
          <Chip key={String(option.key)} label={option.label} selected={option.key === value} onPress={() => onChange(option.key)} />
        ))}
      </ScrollView>
    </View>
  );
}

export function SectionLabel({ title, right }: { title: string; right?: ReactNode }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: 4, marginHorizontal: 4 }}>
      <T variant="label" tone="secondary" style={{ flex: 1 }}>{title}</T>
      {right}
    </View>
  );
}

/** 이름 · 이메일로 찾아 한 명을 고른다 */
export function PersonPicker({
  label,
  people,
  value,
  onChange,
}: {
  label: string;
  people: User[];
  value: string;
  onChange: (uid: string) => void;
}) {
  const [query, setQuery] = useState('');
  const q = query.trim().toLowerCase();
  const sorted = [...people].sort((a, b) => a.displayName.localeCompare(b.displayName, 'ko'));
  const shown = (q ? sorted.filter((row) => row.displayName.toLowerCase().includes(q) || row.email.toLowerCase().includes(q)) : sorted).slice(0, 40);
  const picked = people.find((row) => row.uid === value);
  return (
    <View style={{ gap: 8 }}>
      <Field label={label} value={query} onChangeText={setQuery} placeholder="이름 또는 이메일로 찾기" />
      {picked ? <T variant="caption" tone="primary">선택: {picked.displayName}</T> : null}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }} keyboardShouldPersistTaps="handled">
        {shown.length === 0 ? <T variant="caption" tone="hint">찾는 사람이 없습니다.</T> : null}
        {shown.map((row) => (
          <Chip key={row.uid} label={row.displayName} selected={row.uid === value} onPress={() => onChange(row.uid === value ? '' : row.uid)} />
        ))}
      </ScrollView>
    </View>
  );
}

export function isDateKey(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [y, m, d] = value.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  return date.getFullYear() === y && date.getMonth() === m - 1 && date.getDate() === d;
}

export function isTime(value: string): boolean {
  return /^([01]\d|2[0-3]):[0-5]\d$/.test(value);
}

/** 'YYYY-MM-DD' → 그날 0시(끝이면 23:59) */
export function dateFromKey(value: string, endOfDay = false): Date {
  const [y, m, d] = value.split('-').map(Number);
  return endOfDay ? new Date(y, m - 1, d, 23, 59, 0) : new Date(y, m - 1, d, 0, 0, 0);
}

export function keyOf(date?: Date | null): string {
  if (!date || Number.isNaN(date.getTime())) return '';
  const p = (v: number) => String(v).padStart(2, '0');
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}`;
}

export function dateLabel(date?: Date | null): string {
  if (!date || Number.isNaN(new Date(date).getTime())) return '-';
  return new Date(date).toLocaleDateString('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' });
}
