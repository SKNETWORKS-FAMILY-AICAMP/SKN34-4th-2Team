import { MaterialIcons } from '@expo/vector-icons';
import DateTimePicker, { DateTimePickerAndroid } from '@react-native-community/datetimepicker';
import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import { router } from 'expo-router';
import { useState, type ReactNode } from 'react';
import { Alert, Image, Linking, Platform, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { CertKinds, RecordTypeDescriptions, RecordTypeLabels, SubmissionStatusLabels } from '@web/domain/constants';
import { MissionRules, buildMissionGuidance, missionProgressOf } from '@web/domain/missions';
import type { RecordType, Submission } from '@web/domain/types';

import { useSession } from '../auth/session';
import { absoluteFileUrl } from '../data/http';
import { useCohorts } from '../data/people';
import { queryClient, queryKeys } from '../data/query';
import { createSubmission, reviewSubmission, uploadEvidence, useSubmissions } from '../data/records';
import { useTheme } from '../theme/Theme';
import { Badge, Btn, Callout, Card, Chip, EmptyState, Field, ListGroup, ListItem, Screen, T, fmt, todayKey, type IconName, type Tone } from '../ui/kit';

const EVIDENCE_LIMIT = 5;
const EVIDENCE_MAX_BYTES = 10 * 1024 * 1024;

/** 단위기간을 서버가 모르는 미션 — 승인할 때 관리자가 금액을 확인한다 */
const MANUAL_REWARD: Partial<Record<RecordType, number>> = {
  blog: MissionRules.blogUnitReward,
  study: MissionRules.studyTeamReward,
};

const FILTER_TYPES: RecordType[] = ['certification', 'study', 'blog', 'studyCert', 'precourseQuiz'];

const RECORD_TYPE_ORDER: { type: RecordType; icon: IconName }[] = [
  { type: 'studyCert', icon: 'menu-book' },
  { type: 'precourseQuiz', icon: 'quiz' },
  { type: 'certification', icon: 'workspace-premium' },
  { type: 'study', icon: 'groups' },
  { type: 'blog', icon: 'article' },
];

const STATUS_FILTERS = [
  ['pending', '대기'],
  ['approved', '승인'],
  ['rejected', '반려'],
] as const;

function statusTone(status: string): Tone {
  return status === 'approved' ? 'success' : status === 'pending' ? 'warning' : 'error';
}

function refresh() {
  void queryClient.invalidateQueries({ queryKey: queryKeys.bootstrap });
}

function go(path: string) {
  router.push(path as never);
}

function detailPath(id: string, reviewer: boolean) {
  return reviewer ? `/(admin)/records/${encodeURIComponent(id)}` : `/(student)/records/view/${encodeURIComponent(id)}`;
}

// ── 목록 ────────────────────────────────────────

export function RecordsBoard({ reviewer }: { reviewer: boolean }) {
  const { user } = useSession();
  const { palette } = useTheme();
  const everyone = useSubmissions();
  const submissions = reviewer ? everyone : everyone.filter((row) => row.userId === user?.uid);
  const [query, setQuery] = useState('');
  const [type, setType] = useState<RecordType | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const q = query.trim().toLowerCase();
  const filtered = submissions
    .filter((s) => {
      if (type !== null && s.type !== type) return false;
      if (status !== null && s.status !== status) return false;
      if (q === '') return true;
      return (
        s.title.toLowerCase().includes(q) ||
        s.userDisplayName.toLowerCase().includes(q) ||
        (s.certType ?? '').toLowerCase().includes(q)
      );
    })
    .sort((a, b) => (b.submittedAt?.getTime() ?? 0) - (a.submittedAt?.getTime() ?? 0));
  const pendingCount = submissions.filter((s) => s.status === 'pending').length;

  return (
    <Screen title="기록실" onRefresh={refresh}>
      <T tone="secondary">
        {reviewer
          ? `제출된 기록을 확인하고 승인 · 반려하세요.${pendingCount > 0 ? ` 대기 ${pendingCount}건` : ''}`
          : '블로그, 스터디, 자격증 기록을 제출하고 관리하세요.'}
      </T>

      <View style={[styles.search, { borderColor: palette.border, backgroundColor: palette.surface }]}>
        <MaterialIcons name="search" size={20} color={palette.textHint} />
        <TextInput
          accessibilityLabel="제목·이름 검색"
          value={query}
          onChangeText={setQuery}
          placeholder="제목·이름 검색"
          placeholderTextColor={palette.textHint}
          style={[styles.searchInput, { color: palette.text }]}
        />
        {query !== '' ? (
          <Pressable onPress={() => setQuery('')} hitSlop={8} accessibilityLabel="검색어 지우기">
            <MaterialIcons name="close" size={18} color={palette.textSecondary} />
          </Pressable>
        ) : null}
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
        <Chip label={type === null ? '✓ 전체' : '전체'} selected={type === null} onPress={() => setType(null)} />
        {FILTER_TYPES.map((t) => (
          <Chip key={t} label={type === t ? `✓ ${RecordTypeLabels[t]}` : RecordTypeLabels[t]} selected={type === t} onPress={() => setType(t)} />
        ))}
      </ScrollView>
      <View style={styles.chips}>
        {STATUS_FILTERS.map(([id, label]) => (
          <Chip key={id} label={status === id ? `✓ ${label}` : label} selected={status === id} onPress={() => setStatus(status === id ? null : id)} />
        ))}
      </View>

      {!reviewer ? (
        <>
          <Btn label="새로운 기록 추가" icon="add" onPress={() => go('/(student)/records/new')} />
          <MissionGuidancePanel submissions={submissions} />
          <ListGroup>
            <ListItem
              title="퀘스트"
              subtitle="진행 중인 퀘스트를 인증하고 마일리지를 받으세요"
              left={<MaterialIcons name="flag" size={22} color={palette.primary} />}
              onPress={() => go('/(student)/quests')}
            />
          </ListGroup>
        </>
      ) : null}

      {filtered.length === 0 ? (
        <Card>
          <EmptyState icon="folder-open" text={reviewer ? '제출된 기록이 없습니다' : '아직 제출한 기록이 없습니다'} />
        </Card>
      ) : (
        filtered.map((s) => <RecordCard key={s.id} submission={s} reviewer={reviewer} />)
      )}
    </Screen>
  );
}

export function MissionGuidancePanel({ submissions }: { submissions: Submission[] }) {
  const { palette } = useTheme();
  const [open, setOpen] = useState(true);
  const items = buildMissionGuidance(missionProgressOf(submissions));
  return (
    <Card style={{ gap: 12 }}>
      <Pressable onPress={() => setOpen((v) => !v)} style={styles.line} accessibilityRole="button" accessibilityState={{ expanded: open }}>
        <MaterialIcons name="emoji-events" size={20} color={palette.warning} />
        <T variant="subtitle" style={{ flex: 1 }}>마일리지 미션</T>
        <MaterialIcons name={open ? 'expand-less' : 'expand-more'} size={22} color={palette.textSecondary} />
      </Pressable>
      {open ? (
        <View style={{ gap: 10 }}>
          <T variant="caption" tone="hint">기록실에 제출하고 관리자가 승인하면 규칙에 따라 마일리지가 자동으로 지급됩니다.</T>
          {items.map((item) => (
            <View key={item.id} style={[styles.missionTile, { backgroundColor: palette.surfaceVariant }]}>
              <T variant="subtitle">{item.title}</T>
              <T variant="caption" tone="secondary">{item.progressLabel}</T>
              <T variant="caption" tone="primary" style={{ fontWeight: '700' }}>{item.statusText}</T>
              <T variant="caption" tone="hint">{item.hint}</T>
            </View>
          ))}
        </View>
      ) : null}
    </Card>
  );
}

function RecordCard({ submission, reviewer }: { submission: Submission; reviewer: boolean }) {
  const { palette } = useTheme();
  const meta = [
    reviewer ? submission.userDisplayName : null,
    submission.certType,
    submission.submittedAt === undefined ? null : `제출 ${fmt(submission.submittedAt)}`,
  ].filter((v): v is string => typeof v === 'string' && v !== '');
  const open = () => go(detailPath(submission.id, reviewer));
  const approve = () =>
    Alert.alert('승인', `「${submission.title}」을(를) 승인할까요? 미션 단계에 맞는 마일리지가 자동으로 지급됩니다.`, [
      { text: '닫기', style: 'cancel' },
      {
        text: '승인',
        onPress: () =>
          void reviewSubmission(submission.id, 'approved').catch((err: unknown) =>
            Alert.alert('승인하지 못했습니다', err instanceof Error ? err.message : ''),
          ),
      },
    ]);

  return (
    <Card onPress={open} style={{ gap: 8 }}>
      <View style={styles.line}>
        <T variant="caption" tone="primary" style={{ fontWeight: '700' }}>{RecordTypeLabels[submission.type]}</T>
        {submission.link ? <MaterialIcons name="link" size={14} color={palette.textSecondary} /> : null}
        {submission.fileUrls.length > 0 ? (
          <View style={[styles.line, { gap: 2 }]}>
            <MaterialIcons name="attach-file" size={14} color={palette.textSecondary} />
            <T variant="caption" tone="secondary">{submission.fileUrls.length}</T>
          </View>
        ) : null}
        <View style={{ flex: 1 }} />
        <Badge label={SubmissionStatusLabels[submission.status] ?? '대기'} tone={statusTone(submission.status)} />
      </View>
      <T variant="subtitle">{submission.title}</T>
      {meta.length > 0 ? <T variant="caption" tone="hint">{meta.join(' · ')}</T> : null}
      {submission.learningContent ? <T tone="secondary" numberOfLines={3}>{submission.learningContent}</T> : null}
      {submission.quizScore !== undefined ? <T variant="caption" tone="secondary">점수 {submission.quizScore}점</T> : null}
      {submission.reviewComment ? (
        <Callout tone="error"><T>반려 사유 · {submission.reviewComment}</T></Callout>
      ) : null}
      {submission.mileageGranted ? (
        <Callout tone="success"><T>마일리지 {submission.mileageAmount.toLocaleString('ko-KR')}M 적립</T></Callout>
      ) : null}
      {reviewer && submission.status === 'pending' ? (
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <View style={{ flex: 1 }}><Btn label="반려" tone="ghost" onPress={open} /></View>
          <View style={{ flex: 1 }}>
            <Btn label="승인" onPress={MANUAL_REWARD[submission.type] === undefined ? approve : open} />
          </View>
        </View>
      ) : (
        <T variant="caption" tone="primary" style={{ fontWeight: '600' }}>상세 보기 ›</T>
      )}
    </Card>
  );
}

// ── 상세 ────────────────────────────────────────

export function RecordDetailPage({ id, reviewer }: { id: string; reviewer: boolean }) {
  const { palette } = useTheme();
  const submission = useSubmissions().find((row) => row.id === id);
  const manualDefault = submission ? MANUAL_REWARD[submission.type] : undefined;
  const [amount, setAmount] = useState(String(manualDefault ?? ''));
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!submission) return <Screen title="제출 상세" empty emptyText="기록을 찾지 못했습니다." onRefresh={refresh} />;

  const review = (status: 'approved' | 'rejected' | 'pending') => {
    const granted = Number(amount);
    if (status === 'approved' && manualDefault !== undefined && (!Number.isFinite(granted) || granted < 0)) {
      setError('지급할 마일리지를 0 이상의 숫자로 적어 주세요.');
      return;
    }
    setBusy(true);
    setError(null);
    void reviewSubmission(
      submission.id,
      status,
      status === 'rejected' ? comment.trim() || undefined : undefined,
      status === 'approved' && manualDefault !== undefined ? granted : undefined,
    )
      .then(() => router.back())
      .catch((err: unknown) => setError(err instanceof Error ? err.message : '처리하지 못했습니다.'))
      .finally(() => setBusy(false));
  };
  const revoke = () => {
    const message =
      submission.mileageAmount > 0
        ? `승인을 취소하면 지급한 ${submission.mileageAmount.toLocaleString('ko-KR')}M 이 회수됩니다. 계속할까요?`
        : '승인을 취소하고 대기로 되돌릴까요?';
    Alert.alert('승인 취소', message, [
      { text: '닫기', style: 'cancel' },
      { text: '승인 취소', style: 'destructive', onPress: () => review('pending') },
    ]);
  };

  const rows: [string, string | undefined][] = [
    ['제출자', submission.userDisplayName],
    ['제출 시각', submission.submittedAt ? fmt(submission.submittedAt) : undefined],
    ['자격 종류', submission.certType],
    ['점수', submission.quizScore === undefined ? undefined : `${submission.quizScore}점`],
    ['학습일자', submission.learningDate ? todayKey(submission.learningDate) : undefined],
    ['학습 내용', submission.learningContent],
    ['스터디 기간', submission.startAt && submission.endAt ? `${todayKey(submission.startAt)} ~ ${todayKey(submission.endAt)}` : undefined],
    ['팀 스터디', submission.isTeamStudy === undefined ? undefined : submission.isTeamStudy ? '예' : '아니오 (개인)'],
    ['주차', submission.weekLabel],
    ['적립', submission.mileageAmount > 0 ? `${submission.mileageAmount.toLocaleString('ko-KR')}M` : undefined],
    ['반려 사유', submission.reviewComment],
  ];

  return (
    <Screen title="제출 상세" onRefresh={refresh}>
      <Card style={{ gap: 12 }}>
        <View style={styles.line}>
          <T variant="caption" tone="primary" style={{ fontWeight: '700', flex: 1 }}>{RecordTypeLabels[submission.type]}</T>
          <Badge label={SubmissionStatusLabels[submission.status] ?? '대기'} tone={statusTone(submission.status)} />
        </View>
        <T variant="title">{submission.title}</T>
        <View style={{ gap: 8 }}>
          {rows.map(([label, value]) =>
            value === undefined || value === '' ? null : (
              <View key={label} style={styles.detailRow}>
                <T variant="caption" tone="secondary" style={{ width: 76 }}>{label}</T>
                <T style={{ flex: 1 }}>{value}</T>
              </View>
            ),
          )}
        </View>
      </Card>

      {submission.link ? (
        <Card style={{ gap: 8 }}>
          <T variant="subtitle">링크</T>
          <Pressable onPress={() => void Linking.openURL(submission.link!)} style={styles.line}>
            <T tone="primary" style={{ flex: 1 }} numberOfLines={2}>{submission.link}</T>
            <MaterialIcons name="open-in-new" size={16} color={palette.primary} />
          </Pressable>
        </Card>
      ) : null}

      <Card style={{ gap: 8 }}>
        <T variant="subtitle">증빙 파일 ({submission.fileUrls.length})</T>
        {submission.fileUrls.length === 0 ? (
          <T variant="caption" tone="hint">첨부된 증빙이 없습니다.</T>
        ) : (
          submission.fileUrls.map((url, index) =>
            url.startsWith('demo://') ? (
              <View key={url} style={styles.line}>
                <MaterialIcons name="image" size={18} color={palette.textSecondary} />
                <T tone="secondary">데모 파일 {index + 1}</T>
              </View>
            ) : (
              <Pressable key={url} onPress={() => void Linking.openURL(absoluteFileUrl(url))} style={[styles.fileRow, { borderColor: palette.border }]}>
                <MaterialIcons name="attach-file" size={18} color={palette.primary} />
                <T tone="primary" style={{ flex: 1 }}>파일 {index + 1}</T>
                <MaterialIcons name="open-in-new" size={16} color={palette.primary} />
              </Pressable>
            ),
          )
        )}
      </Card>

      {reviewer && submission.status === 'pending' ? (
        <Card style={{ gap: 12 }}>
          <T variant="subtitle">검토</T>
          {manualDefault !== undefined ? (
            <View style={{ gap: 4 }}>
              <Field label="지급할 마일리지" value={amount} onChangeText={(v) => setAmount(v.replace(/[^\d]/g, ''))} keyboard="numeric" />
              <T variant="caption" tone="hint">
                기본 {manualDefault.toLocaleString('ko-KR')}M · 승인하면 바로 지급됩니다(미션 상한을 넘으면 남은 만큼만).
              </T>
            </View>
          ) : (
            <T variant="caption" tone="hint">승인하면 미션 단계에 맞는 마일리지가 자동으로 지급됩니다.</T>
          )}
          <Field label="반려 사유 (반려할 때)" value={comment} onChangeText={setComment} placeholder="예: 날짜가 보이는 사진으로 다시 올려 주세요." multiline />
          {error ? <T tone="error">{error}</T> : null}
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <View style={{ flex: 1 }}><Btn label="반려" tone="ghost" disabled={busy} onPress={() => review('rejected')} /></View>
            <View style={{ flex: 1 }}><Btn label={busy ? '처리 중…' : '승인'} disabled={busy} onPress={() => review('approved')} /></View>
          </View>
        </Card>
      ) : null}
      {reviewer && submission.status === 'approved' ? (
        <View style={{ gap: 8 }}>
          {error ? <T tone="error">{error}</T> : null}
          <Btn label={busy ? '처리 중…' : '승인 취소'} icon="undo" tone="ghost" disabled={busy} onPress={revoke} />
        </View>
      ) : null}
    </Screen>
  );
}

// ── 종류 고르기 ────────────────────────────────────

export function RecordNewPage() {
  const { palette } = useTheme();
  return (
    <Screen title="새로운 기록 추가">
      <T tone="secondary">제출할 기록의 종류를 고르세요.</T>
      <ListGroup>
        {RECORD_TYPE_ORDER.map(({ type, icon }) => (
          <ListItem
            key={type}
            title={RecordTypeLabels[type]}
            subtitle={RecordTypeDescriptions[type]}
            left={
              <View style={[styles.typeIcon, { backgroundColor: palette.primaryLight }]}>
                <MaterialIcons name={icon} size={22} color={palette.primary} />
              </View>
            }
            onPress={() => go(`/(student)/records/form/${type}`)}
          />
        ))}
      </ListGroup>
    </Screen>
  );
}

// ── 제출 폼 ────────────────────────────────────────

interface BlogWeek {
  weekNumber: number;
  label: string;
}

/** 블로그 주차 — 기수 시작일부터 7일씩 12주 */
function blogWeeks(campStart: Date | undefined, count = 12): BlogWeek[] {
  const start = campStart ?? new Date(new Date().getFullYear(), 5, 1);
  return Array.from({ length: count }, (_, i) => {
    const from = new Date(start);
    from.setDate(from.getDate() + i * 7);
    const to = new Date(from);
    to.setDate(to.getDate() + 6);
    return {
      weekNumber: i + 1,
      label: `${i + 1}주차 ${from.getMonth() + 1}/${from.getDate()}~${to.getMonth() + 1}/${to.getDate()}`,
    };
  });
}

export type PickedFile = { uri: string; name: string; type: string; size?: number };

function guessType(name: string, fallback?: string | null): string {
  if (fallback) return fallback;
  const ext = name.split('.').pop()?.toLowerCase();
  if (ext === 'pdf') return 'application/pdf';
  if (ext === 'png') return 'image/png';
  if (ext === 'gif') return 'image/gif';
  if (ext === 'webp') return 'image/webp';
  if (ext === 'heic' || ext === 'heif') return 'image/heic';
  return 'image/jpeg';
}

export function RecordFormPage({ type }: { type: RecordType }) {
  const { user } = useSession();
  const { palette } = useTheme();
  const cohort = useCohorts().find((c) => c.cohortId === user?.cohortId);
  const myRecords = useSubmissions().filter((row) => row.userId === user?.uid);

  const [title, setTitle] = useState('');
  const [certType, setCertType] = useState<string>(CertKinds[0]);
  const [link, setLink] = useState('');
  const [weekNumber, setWeekNumber] = useState<number | undefined>(undefined);
  const [isTeamStudy, setTeamStudy] = useState(true);
  const [learningDate, setLearningDate] = useState('');
  const [learningContent, setLearningContent] = useState('');
  const [startAt, setStartAt] = useState('');
  const [endAt, setEndAt] = useState('');
  const [quizScore, setQuizScore] = useState('');
  const [files, setFiles] = useState<PickedFile[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const weeks = blogWeeks(cohort?.startDate);
  const approvedWeeks = new Set(
    myRecords.filter((s) => s.type === 'blog' && s.status === 'approved' && s.weekNumber !== undefined).map((s) => s.weekNumber),
  );

  // 증빙을 먼저 올리고(서버가 키를 준다) 그 키를 붙여 제출한다. 하나라도 실패하면 제출하지 않는다
  const send = async (record: Omit<Submission, 'id' | 'submittedAt' | 'fileUrls'>, withFiles: boolean) => {
    if (!user) return;
    setSending(true);
    setError(null);
    try {
      const evidence = withFiles ? await Promise.all(files.map((file) => uploadEvidence(file))) : [];
      await createSubmission(record, evidence, user.cohortId);
      Alert.alert('제출했습니다', '관리자가 확인하면 기록실에서 결과를 볼 수 있습니다.');
      router.dismissTo('/(student)/records' as never);
    } catch (err) {
      setError(`제출하지 못했습니다 · ${err instanceof Error ? err.message : '다시 시도해 주세요.'}`);
    } finally {
      setSending(false);
    }
  };

  const submit = () => {
    if (!user) return;
    const fail = (message: string) => setError(message);
    const base = {
      userId: user.uid,
      userDisplayName: user.displayName,
      type,
      status: 'pending' as const,
      mileageGranted: false,
      mileageAmount: 0,
    };

    if (type === 'studyCert') {
      if (learningDate === '') return fail('학습일자를 선택해 주세요.');
      if (learningContent.trim() === '') return fail('학습한 내용을 입력해 주세요.');
      if (files.length === 0) return fail('날짜·시간이 보이는 인증 사진을 첨부해 주세요.');
      return void send(
        { ...base, title: `학습인증 ${learningDate}`, learningDate: new Date(learningDate), learningContent: learningContent.trim() },
        true,
      );
    }
    if (type === 'precourseQuiz') {
      const score = Number(quizScore.trim());
      if (title.trim() === '') return fail('회차 / 제목을 입력해 주세요.');
      if (quizScore.trim() === '' || !Number.isFinite(score) || score < 0 || score > 100) return fail('점수는 0~100 사이로 입력해 주세요.');
      if (files.length === 0) return fail('점수 화면 캡처 등 증빙을 첨부해 주세요.');
      return void send({ ...base, title: title.trim(), quizScore: score }, true);
    }
    if (type === 'certification') {
      if (title.trim() === '') return fail('자격증 제목을 입력해 주세요.');
      if (files.length === 0) return fail('증빙 이미지를 첨부해 주세요.');
      return void send({ ...base, title: title.trim(), certType }, true);
    }
    if (type === 'study') {
      if (title.trim() === '') return fail('스터디 제목을 입력해 주세요.');
      if (startAt === '' || endAt === '') return fail('시작일과 종료일을 선택해 주세요.');
      if (endAt < startAt) return fail('종료일은 시작일과 같거나 뒤여야 합니다.');
      if (files.length === 0) return fail('증빙 이미지를 1개 이상 첨부해 주세요.');
      if (!isTeamStudy) return fail('개인 스터디는 마일리지 미션 대상이 아닙니다. 팀 스터디만 인정됩니다.');
      return void send(
        { ...base, title: title.trim(), startAt: new Date(startAt), endAt: new Date(endAt), isTeamStudy: true },
        true,
      );
    }
    const week = weeks.find((w) => w.weekNumber === weekNumber);
    if (week === undefined) return fail('주차를 선택해 주세요.');
    const url = link.trim();
    if (url === '') return fail('블로그 URL을 입력해 주세요.');
    if (!url.startsWith('http://') && !url.startsWith('https://')) return fail('http:// 또는 https:// 로 시작하는 URL을 입력해 주세요.');
    return void send(
      { ...base, title: `${week.label} 블로그`, weekNumber: week.weekNumber, weekLabel: week.label, link: url },
      false,
    );
  };

  const evidence = (label: string, hint: string, multiple: boolean) => (
    <EvidencePicker
      label={label}
      hint={hint}
      multiple={multiple}
      files={files}
      onChange={(next) => {
        setFiles(next);
        setError(null);
      }}
      onError={setError}
    />
  );

  return (
    <Screen title={`${RecordTypeLabels[type]} 제출`}>
      <Callout tone="info"><T>{RecordTypeDescriptions[type]}</T></Callout>
      <Card style={{ gap: 16 }}>
        {type === 'studyCert' ? (
          <>
            <DateField label="학습일자" value={learningDate} onChange={setLearningDate} />
            <Field label="학습한 내용" value={learningContent} onChangeText={setLearningContent} placeholder="오늘 학습한 주제 및 키워드" multiline />
            {evidence('학습 인증 사진', '날짜·시간이 보이도록 교재/화면/필기 사진 첨부', true)}
          </>
        ) : null}

        {type === 'precourseQuiz' ? (
          <>
            <Field label="회차 / 제목" value={title} onChangeText={setTitle} placeholder="예: 프리코스 1차 쪽지시험" />
            <View style={{ gap: 4 }}>
              <Field label="점수 (0~100)" value={quizScore} onChangeText={(v) => setQuizScore(v.replace(/[^\d]/g, '').slice(0, 3))} placeholder="예: 80" keyboard="numeric" />
              <T variant="caption" tone="hint">{MissionRules.quizPassScore}점 이상이면 미션 통과로 인정됩니다.</T>
            </View>
            {evidence('증빙', '점수 화면 캡처 등을 첨부해 주세요', true)}
          </>
        ) : null}

        {type === 'certification' ? (
          <>
            <Block label="자격증 종류">
              <View style={styles.wrap}>
                {CertKinds.map((kind) => (
                  <Chip key={kind} label={kind} selected={certType === kind} onPress={() => setCertType(kind)} />
                ))}
              </View>
            </Block>
            <Field label="제목" value={title} onChangeText={setTitle} placeholder="예: Python Certified Entry Programmer" />
            {evidence('증빙 이미지', '합격 화면 · 자격증 사진을 첨부해 주세요', false)}
          </>
        ) : null}

        {type === 'study' ? (
          <>
            <Pressable
              accessibilityRole="checkbox"
              accessibilityState={{ checked: isTeamStudy }}
              onPress={() => setTeamStudy((v) => !v)}
              style={styles.line}
            >
              <MaterialIcons name={isTeamStudy ? 'check-box' : 'check-box-outline-blank'} size={22} color={isTeamStudy ? palette.primary : palette.textSecondary} />
              <T style={{ flex: 1 }}>팀 스터디입니다 (개인 스터디는 미션 적립 대상이 아닙니다)</T>
            </Pressable>
            <Field label="스터디 제목" value={title} onChangeText={setTitle} placeholder="예: 알고리즘 스터디" />
            <View style={{ flexDirection: 'row', gap: 12 }}>
              <View style={{ flex: 1 }}><DateField label="시작일" value={startAt} onChange={setStartAt} /></View>
              <View style={{ flex: 1 }}><DateField label="종료일" value={endAt} onChange={setEndAt} minimum={startAt} /></View>
            </View>
            {evidence('증빙 이미지', '오프라인 스터디 사진(날짜·시간 확인 가능)을 첨부해 주세요', true)}
          </>
        ) : null}

        {type === 'blog' ? (
          <>
            <Block label="주차 선택" hint="승인된 주차는 다시 작성할 수 없습니다.">
              <View style={styles.weekGrid}>
                {weeks.map((w) => {
                  const done = approvedWeeks.has(w.weekNumber);
                  const on = weekNumber === w.weekNumber;
                  return (
                    <Pressable
                      key={w.weekNumber}
                      accessibilityRole="radio"
                      accessibilityState={{ selected: on, disabled: done }}
                      disabled={done}
                      onPress={() => {
                        setWeekNumber(w.weekNumber);
                        setError(null);
                      }}
                      style={[
                        styles.weekChip,
                        {
                          borderColor: on ? palette.primary : palette.border,
                          backgroundColor: on ? palette.primaryLight : palette.surface,
                          opacity: done ? 0.45 : 1,
                        },
                      ]}
                    >
                      <T variant="subtitle" tone={on ? 'primary' : 'default'}>{w.weekNumber}주차</T>
                      <T variant="caption" tone="secondary">{w.label.replace(`${w.weekNumber}주차 `, '')}</T>
                      {done ? <T variant="caption" tone="success">승인됨</T> : null}
                    </Pressable>
                  );
                })}
              </View>
            </Block>
            <Field label="링크" value={link} onChangeText={setLink} placeholder="https://" keyboard="url" />
          </>
        ) : null}

        {error ? <Callout tone="error"><T>{error}</T></Callout> : null}

        <Btn label={sending ? '올리는 중…' : '제출'} icon="send" disabled={sending} onPress={submit} />
      </Card>
    </Screen>
  );
}

function Block({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <View style={{ gap: 8 }}>
      <T variant="label" tone="secondary">{label}</T>
      {children}
      {hint ? <T variant="caption" tone="hint">{hint}</T> : null}
    </View>
  );
}

function keyToDate(key: string): Date {
  const [y, m, d] = key.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function DateField({ label, value, onChange, minimum }: { label: string; value: string; onChange: (key: string) => void; minimum?: string }) {
  const { palette } = useTheme();
  const [iosOpen, setIosOpen] = useState(false);
  const current = value ? keyToDate(value) : minimum ? keyToDate(minimum) : new Date();
  const minDate = minimum ? keyToDate(minimum) : undefined;

  const open = () => {
    if (Platform.OS === 'android') {
      DateTimePickerAndroid.open({
        value: current,
        mode: 'date',
        minimumDate: minDate,
        onChange: (event, date) => {
          if (event.type === 'set' && date) onChange(todayKey(date));
        },
      });
    } else {
      setIosOpen((v) => !v);
    }
  };

  return (
    <View style={{ gap: 6 }}>
      <T variant="label" tone="secondary">{label}</T>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${label} 선택`}
        onPress={open}
        style={[styles.dateBox, { borderColor: iosOpen ? palette.primary : palette.border, backgroundColor: palette.surface }]}
      >
        <MaterialIcons name="event" size={18} color={palette.textSecondary} />
        <T tone={value ? 'default' : 'hint'} style={{ flex: 1 }}>{value || '날짜 선택'}</T>
      </Pressable>
      {Platform.OS === 'ios' && iosOpen ? (
        <DateTimePicker
          value={current}
          mode="date"
          display="inline"
          locale="ko-KR"
          minimumDate={minDate}
          onChange={(_, date) => {
            if (date) onChange(todayKey(date));
            setIosOpen(false);
          }}
        />
      ) : null}
    </View>
  );
}

export function EvidencePicker({
  label,
  hint,
  multiple,
  files,
  onChange,
  onError,
}: {
  label: string;
  hint: string;
  multiple: boolean;
  files: PickedFile[];
  onChange: (files: PickedFile[]) => void;
  onError: (message: string | null) => void;
}) {
  const { palette } = useTheme();
  const limit = multiple ? EVIDENCE_LIMIT : 1;
  const remaining = limit - files.length;

  const add = (picked: PickedFile[]) => {
    if (picked.length === 0) return;
    const tooBig = picked.find((file) => file.size !== undefined && file.size > EVIDENCE_MAX_BYTES);
    if (tooBig) {
      onError(`${tooBig.name} — 파일은 10MB 이하만 올릴 수 있습니다.`);
      return;
    }
    const next = multiple ? [...files, ...picked].slice(0, limit) : picked.slice(0, 1);
    if (multiple && files.length + picked.length > limit) onError(`증빙은 ${limit}개까지 붙일 수 있어 앞의 ${limit}개만 남겼습니다.`);
    else onError(null);
    onChange(next);
  };

  const fromImages = (assets: ImagePicker.ImagePickerAsset[]) =>
    assets.map((asset, index) => {
      const name = asset.fileName ?? `photo-${Date.now()}-${index}.jpg`;
      return { uri: asset.uri, name, type: guessType(name, asset.mimeType), size: asset.fileSize };
    });

  const camera = async () => {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) {
      onError('카메라 권한이 없어 사진을 찍을 수 없습니다. 설정에서 권한을 허용해 주세요.');
      return;
    }
    const result = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.8 });
    if (!result.canceled) add(fromImages(result.assets));
  };

  const album = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.8,
      allowsMultipleSelection: multiple,
      selectionLimit: multiple ? Math.max(remaining, 1) : 1,
    });
    if (!result.canceled) add(fromImages(result.assets));
  };

  const document = async () => {
    const result = await DocumentPicker.getDocumentAsync({ type: ['image/*', 'application/pdf'], multiple, copyToCacheDirectory: true });
    if (result.canceled) return;
    add(result.assets.map((asset) => ({ uri: asset.uri, name: asset.name, type: guessType(asset.name, asset.mimeType), size: asset.size })));
  };

  const full = multiple && remaining <= 0;
  const sources: { icon: IconName; label: string; run: () => Promise<void> }[] = [
    { icon: 'photo-camera', label: '사진 찍기', run: camera },
    { icon: 'photo-library', label: '앨범', run: album },
    { icon: 'attach-file', label: '파일', run: document },
  ];

  return (
    <Block label={`${label} (${files.length}/${limit})`} hint={`${hint} · 이미지나 PDF, 한 개 10MB 까지`}>
      <View style={{ flexDirection: 'row', gap: 8 }}>
        {sources.map((source) => (
          <Pressable
            key={source.label}
            accessibilityRole="button"
            accessibilityLabel={source.label}
            disabled={full}
            onPress={() => void source.run().catch((err: unknown) => onError(err instanceof Error ? err.message : '파일을 고르지 못했습니다.'))}
            style={({ pressed }) => [
              styles.source,
              { borderColor: palette.border, backgroundColor: pressed ? palette.primaryLight : palette.surface, opacity: full ? 0.4 : 1 },
            ]}
          >
            <MaterialIcons name={source.icon} size={22} color={palette.primary} />
            <T variant="caption" style={{ fontWeight: '600' }}>{source.label}</T>
          </Pressable>
        ))}
      </View>
      {files.length > 0 ? (
        <View style={styles.wrap}>
          {files.map((file, index) => (
            <View key={`${file.uri}-${index}`} style={[styles.thumb, { borderColor: palette.border, backgroundColor: palette.surfaceVariant }]}>
              {file.type.startsWith('image/') ? (
                <Image source={{ uri: file.uri }} style={StyleSheet.absoluteFill} resizeMode="cover" />
              ) : (
                <View style={styles.pdf}>
                  <MaterialIcons name="picture-as-pdf" size={28} color={palette.error} />
                  <T variant="caption" numberOfLines={2} style={{ textAlign: 'center', fontSize: 10 }}>{file.name}</T>
                </View>
              )}
              <Pressable
                accessibilityLabel={`${file.name} 빼기`}
                onPress={() => onChange(files.filter((_, i) => i !== index))}
                hitSlop={6}
                style={styles.remove}
              >
                <MaterialIcons name="close" size={14} color="#fff" />
              </Pressable>
            </View>
          ))}
        </View>
      ) : null}
    </Block>
  );
}

const styles = StyleSheet.create({
  line: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chips: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  search: { flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderRadius: 12, paddingHorizontal: 12, minHeight: 44 },
  searchInput: { flex: 1, fontSize: 16, paddingVertical: 8 },
  missionTile: { borderRadius: 12, padding: 12, gap: 2 },
  detailRow: { flexDirection: 'row', gap: 8 },
  fileRow: { flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, minHeight: 44 },
  typeIcon: { width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  weekGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  weekChip: { width: '31%', flexGrow: 1, borderWidth: 1, borderRadius: 12, paddingVertical: 10, paddingHorizontal: 8, alignItems: 'center', gap: 2 },
  dateBox: { flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderRadius: 12, paddingHorizontal: 14, minHeight: 44 },
  source: { flex: 1, minHeight: 64, borderWidth: 1, borderRadius: 12, alignItems: 'center', justifyContent: 'center', gap: 4 },
  thumb: { width: 76, height: 76, borderRadius: 10, borderWidth: 1, overflow: 'hidden' },
  pdf: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 4, gap: 2 },
  remove: { position: 'absolute', top: 4, right: 4, width: 22, height: 22, borderRadius: 11, backgroundColor: 'rgba(0,0,0,0.6)', alignItems: 'center', justifyContent: 'center' },
});
