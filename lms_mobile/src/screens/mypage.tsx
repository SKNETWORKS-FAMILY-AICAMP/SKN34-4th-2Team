import { MaterialIcons } from '@expo/vector-icons';
import { useState, type ReactNode } from 'react';
import { Pressable, Text, TextInput, View } from 'react-native';
import { JobPreferencePresets } from '@web/domain/constants';
import type { User } from '@web/domain/types';

import { useSession } from '../auth/session';
import { updateProfile } from '../data/people';
import { useTheme } from '../theme/Theme';
import { Btn, Card, Chip, Field, Screen, T, fmt, todayKey, type IconName } from '../ui/kit';

/**
 * 마이페이지 — 웹 `features/mypage/MyPageScreen.tsx` 와 같은 구성.
 * 카드 넷이 쌓인다: 프로필 요약, 개인 정보, 취업 희망 조건, 비밀번호.
 * (기술 스택은 앱에서 빼고 이용 안내 · PDF 매뉴얼은 설정으로 옮겼다)
 * 항목은 「아이콘 · 라벨 · 값 · 연필」 한 줄이고, 연필을 누르면 그 자리에서 고친다.
 */
export function MyPage() {
  const { user } = useSession();
  if (!user) return <Screen title="마이페이지">{null}</Screen>;
  return (
    <Screen title="마이페이지">
      <T variant="caption" tone="secondary" style={{ marginTop: -4 }}>
        프로필 · 연락처 · 취업 희망 조건 · 비밀번호를 관리합니다.
      </T>
      <ProfileOverviewCard user={user} />
      <PersonalInfoCard user={user} />
      <JobPreferencesCard user={user} />
      <PasswordCard />

    </Screen>
  );
}


/** 「SK네트웍스 Family AI 캠프 34기」를 과정 이름과 기수로 나눈다 */
function splitCohort(name: string): { course: string; term: string } {
  const match = /^(.*)\s+(\d+기)$/.exec((name ?? '').trim());
  return match === null ? { course: name || '-', term: '-' } : { course: match[1].trim(), term: match[2] };
}

/** 저장 → 서버가 bootstrap 을 다시 보내 화면이 따라간다. 실패하면 카드 아래에 이유를 적는다 */
function useSave() {
  const [error, setError] = useState<string | null>(null);
  const save = (uid: string, patch: Partial<User>) => {
    setError(null);
    void updateProfile(uid, patch).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : '저장하지 못했습니다.'));
  };
  return { error, save };
}

function CardTitle({ title, right }: { title: string; right?: ReactNode }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', minHeight: 28 }}>
      <T variant="subtitle" style={{ flex: 1 }}>{title}</T>
      {right}
    </View>
  );
}

function Rule() {
  const { palette } = useTheme();
  return <View style={{ height: 1, backgroundColor: palette.border, marginVertical: 4 }} />;
}

function IconBtn({ icon, label, onPress }: { icon: IconName; label: string; onPress: () => void }) {
  const { palette } = useTheme();
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} hitSlop={8} onPress={onPress} style={({ pressed }) => ({ padding: 6, opacity: pressed ? 0.5 : 1 })}>
      <MaterialIcons name={icon} size={20} color={palette.textSecondary} />
    </Pressable>
  );
}


function ProfileOverviewCard({ user }: { user: User }) {
  const { palette } = useTheme();
  const { course, term } = splitCohort(user.cohortName);
  const rows: [string, string][] = [
    ['교육과정', course],
    ['기수', term],
    ['계정 생성일', user.createdAt ? fmt(user.createdAt) : '-'],
    ['마지막 로그인', user.lastLoginAt ? fmt(user.lastLoginAt) : '-'],
  ];
  return (
    <Card style={{ gap: 16 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
        <View>
          <View style={{ width: 60, height: 60, borderRadius: 30, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.primaryLight }}>
            <MaterialIcons name="person" size={34} color={palette.primary} />
          </View>
          <View
            style={{
              position: 'absolute',
              right: -2,
              bottom: -2,
              width: 22,
              height: 22,
              borderRadius: 11,
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: palette.surface,
              borderWidth: 1,
              borderColor: palette.border,
            }}
          >
            <MaterialIcons name="photo-camera" size={12} color={palette.textSecondary} />
          </View>
        </View>
        <View style={{ flex: 1, gap: 2 }}>
          <T variant="title">{user.displayName}님</T>
          <T variant="caption" tone="secondary" numberOfLines={1}>{user.cohortName}</T>
        </View>
      </View>
      <View style={{ gap: 10 }}>
        {rows.map(([label, value]) => (
          <View key={label} style={{ flexDirection: 'row', gap: 12 }}>
            <T variant="caption" tone="secondary" style={{ width: 84 }}>{label}</T>
            <T variant="caption" style={{ flex: 1 }}>{value}</T>
          </View>
        ))}
      </View>
    </Card>
  );
}

function PersonalInfoCard({ user }: { user: User }) {
  const { palette } = useTheme();
  const { error, save } = useSave();
  const links = user.socialLinks ?? {};
  const hasPersonalEmail = Boolean(user.personalEmail);
  return (
    <Card style={{ gap: 8 }}>
      <CardTitle title="개인 정보" />
      {!hasPersonalEmail ? (
        <View style={{ padding: 10, borderRadius: 10, backgroundColor: `${palette.warning}1f` }}>
          <T variant="caption" style={{ color: palette.warning }}>개인 이메일이 등록되지 않았습니다. 구글폼 제출 연동을 위해 등록해 주세요.</T>
        </View>
      ) : null}
      <EditableRow
        icon="mail"
        label="개인 이메일 (구글폼)"
        value={user.personalEmail}
        empty="등록된 이메일 없음"
        keyboard="email-address"
        onSave={(v) => save(user.uid, { personalEmail: v })}
      />
      <Rule />
      <EditableRow
        icon="calendar-today"
        label="생년월일"
        value={user.birthDate}
        empty="미입력"
        placeholder="1998-03-15"
        validate={(v) => (v === '' || isBirthDate(v) ? null : 'YYYY-MM-DD 형식으로 입력해 주세요.')}
        onSave={(v) => save(user.uid, { birthDate: v })}
      />
      <Rule />
      <EditableRow
        icon="code"
        label="GitHub"
        value={links.github}
        keyboard="url"
        onSave={(v) => save(user.uid, { socialLinks: { ...links, github: v } })}
      />
      <Rule />
      <EditableRow
        icon="article"
        label="블로그"
        value={links.blog}
        keyboard="url"
        onSave={(v) => save(user.uid, { socialLinks: { ...links, blog: v } })}
      />
      {error ? <T variant="caption" tone="error">{error}</T> : null}
    </Card>
  );
}

function isBirthDate(text: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(text) && text >= '1900-01-01' && text <= todayKey();
}

/** 아이콘 · 라벨 · 값 · 연필 한 줄. 연필을 누르면 그 자리가 입력칸이 된다 */
function EditableRow({
  icon,
  label,
  value,
  empty = '등록된 링크 없음',
  placeholder,
  keyboard,
  validate,
  onSave,
}: {
  icon: IconName;
  label: string;
  value?: string;
  empty?: string;
  placeholder?: string;
  keyboard?: 'default' | 'email-address' | 'url';
  validate?: (value: string) => string | null;
  onSave: (next: string) => void;
}) {
  const { palette } = useTheme();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? '');
  const [problem, setProblem] = useState<string | null>(null);
  const filled = Boolean(value);
  return (
    <View style={{ flexDirection: 'row', alignItems: editing ? 'flex-start' : 'center', gap: 12, paddingVertical: 4 }}>
      <MaterialIcons name={icon} size={18} color={palette.textSecondary} style={{ marginTop: editing ? 2 : 0 }} />
      <View style={{ flex: 1, gap: 4 }}>
        <T variant="label">{label}</T>
        {editing ? (
          <View style={{ gap: 8 }}>
            <TextInput
              value={draft}
              onChangeText={(text) => {
                setDraft(text);
                setProblem(null);
              }}
              autoFocus
              autoCapitalize="none"
              keyboardType={keyboard}
              placeholder={placeholder}
              placeholderTextColor={palette.textHint}
              style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8, fontSize: 15, color: palette.text, backgroundColor: palette.surface }}
            />
            {problem ? <T variant="caption" tone="error">{problem}</T> : null}
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <View style={{ flex: 1 }}>
                <Btn
                  label="저장"
                  onPress={() => {
                    const next = draft.trim();
                    const reason = validate?.(next) ?? null;
                    if (reason) {
                      setProblem(reason);
                      return;
                    }
                    onSave(next);
                    setEditing(false);
                  }}
                />
              </View>
              <View style={{ flex: 1 }}>
                <Btn
                  label="취소"
                  tone="ghost"
                  onPress={() => {
                    setDraft(value ?? '');
                    setProblem(null);
                    setEditing(false);
                  }}
                />
              </View>
            </View>
          </View>
        ) : filled ? (
          <T tone="secondary" numberOfLines={1}>{value}</T>
        ) : (
          <T tone="hint">{empty}</T>
        )}
      </View>
      {!editing ? (
        <IconBtn
          icon="edit"
          label={`${label} 수정`}
          onPress={() => {
            setDraft(value ?? '');
            setEditing(true);
          }}
        />
      ) : null}
    </View>
  );
}

type PrefKey = 'targetRoles' | 'regions' | 'employmentTypes';

function JobPreferencesCard({ user }: { user: User }) {
  const { palette } = useTheme();
  const { error, save } = useSave();
  const [editing, setEditing] = useState(false);
  const [typed, setTyped] = useState<Record<PrefKey, string>>({ targetRoles: '', regions: '', employmentTypes: '' });
  const p = user.jobPreferences;
  const rows: [string, PrefKey][] = [
    ['희망 직무', 'targetRoles'],
    ['희망 근무지역', 'regions'],
    ['희망 고용형태', 'employmentTypes'],
  ];
  const same = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase();
  const setValues = (key: PrefKey, next: string[]) => save(user.uid, { jobPreferences: { ...p, [key]: next } });

  return (
    <Card style={{ gap: 10 }}>
      <CardTitle title="취업 희망 조건" right={<IconBtn icon={editing ? 'close' : 'edit'} label={editing ? '수정 닫기' : '수정'} onPress={() => setEditing((v) => !v)} />} />
      <T variant="caption" tone="secondary">이력서에는 표시되지 않고 커리어 코치의 맞춤 공고 추천에만 쓰입니다.</T>

      {rows.map(([label, key]) => {
        const values = p[key] ?? [];
        const presets: readonly string[] = JobPreferencePresets[key];
        const custom = values.filter((v) => !presets.some((x) => same(x, v)));
        const options = [...presets, ...custom];
        return (
          <View key={key} style={{ gap: 6, paddingTop: 4 }}>
            <T variant="label">{label}</T>
            {editing ? (
              <>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                  {options.map((option) => {
                    const on = values.some((v) => same(v, option));
                    return (
                      <Chip
                        key={option}
                        label={option}
                        selected={on}
                        onPress={() => setValues(key, on ? values.filter((v) => !same(v, option)) : [...values, option])}
                      />
                    );
                  })}
                </View>
                <TextInput
                  value={typed[key]}
                  onChangeText={(text) => setTyped((prev) => ({ ...prev, [key]: text }))}
                  onSubmitEditing={() => {
                    const text = typed[key].trim();
                    setTyped((prev) => ({ ...prev, [key]: '' }));
                    if (!text || values.some((v) => same(v, text))) return;
                    setValues(key, [...values, presets.find((x) => same(x, text)) ?? text]);
                  }}
                  placeholder={`${label.replace('희망 ', '')} 직접 입력 후 완료`}
                  placeholderTextColor={palette.textHint}
                  returnKeyType="done"
                  style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8, fontSize: 14, color: palette.text, backgroundColor: palette.surface }}
                />
              </>
            ) : values.length === 0 ? (
              <T tone="hint">미입력</T>
            ) : (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                {values.map((v) => (
                  <View key={v} style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, backgroundColor: palette.primaryLight }}>
                    <Text style={{ color: palette.primary, fontSize: 13, fontWeight: '600' }}>{v}</Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        );
      })}
      {error ? <T variant="caption" tone="error">{error}</T> : null}
    </Card>
  );
}

function PasswordCard() {
  const { palette } = useTheme();
  const { changePassword } = useSession();
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [saving, setSaving] = useState(false);

  const touch = (setter: (v: string) => void) => (value: string) => {
    setter(value);
    setError(null);
    setDone(false);
  };

  const submit = () => {
    setDone(false);
    if (next.length < 8) return setError('비밀번호는 8자 이상이어야 합니다.');
    if (next !== confirm) return setError('두 번 입력한 비밀번호가 다릅니다.');
    setSaving(true);
    void changePassword(next, current).then((result) => {
      setSaving(false);
      if (!result.ok) return setError(result.message);
      setError(null);
      setCurrent('');
      setNext('');
      setConfirm('');
      setDone(true);
    });
  };

  return (
    <Card style={{ gap: 12 }}>
      <Pressable accessibilityRole="button" accessibilityState={{ expanded: open }} onPress={() => setOpen((v) => !v)} style={{ flexDirection: 'row', alignItems: 'center', minHeight: 28 }}>
        <T variant="subtitle" style={{ flex: 1 }}>비밀번호 변경</T>
        <MaterialIcons name={open ? 'expand-less' : 'expand-more'} size={22} color={palette.textSecondary} />
      </Pressable>
      {open ? (
        <>
          <T variant="caption" tone="secondary">현재 비밀번호를 확인한 뒤 새 비밀번호로 바꿉니다.</T>
          <Field label="현재 비밀번호" value={current} onChangeText={touch(setCurrent)} secure />
          <Field label="새 비밀번호" value={next} onChangeText={touch(setNext)} secure />
          <Field label="새 비밀번호 확인" value={confirm} onChangeText={touch(setConfirm)} secure />
          {error ? <T variant="caption" tone="error">{error}</T> : null}
          {done ? <T variant="caption" tone="success">비밀번호를 바꿨습니다. 다음 로그인부터 새 비밀번호를 쓰세요.</T> : null}
          <Btn label={saving ? '변경 중' : '변경'} tone="ghost" onPress={submit} disabled={saving} />
        </>
      ) : null}
    </Card>
  );
}
