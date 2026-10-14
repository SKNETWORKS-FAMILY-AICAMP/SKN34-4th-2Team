import * as ImagePicker from 'expo-image-picker';
import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';
import { router, useNavigation } from 'expo-router';
import { Children, useEffect, useRef, useState, type ReactNode } from 'react';
import { MaterialIcons } from '@expo/vector-icons';
import { Alert, Linking, Modal, Pressable, ScrollView, StyleSheet, View, useWindowDimensions } from 'react-native';
import { formatPostingText, type PostingBlock } from '@web/features/jobs/postingText';
import { COMMON_QUESTIONS } from '@web/features/jobApply/companyQuestions';
import { ResumeSectionKeys, ResumeStatusLabels, computeSections } from '@web/domain/constants';
import { groupResumes, isApplyCopy, isTailored, withoutPromotedWorkCopies } from '@web/features/resume/resumeGroups';
import type { Resume, ResumeContent } from '@web/domain/types';

import { useSession } from '../auth/session';
import { refreshBootstrap } from '../data/query';
import { useDismissedToday, useSeenAlerts, visibleAlerts } from '../data/alertSeen';
import { featuredPostings, fetchApplyLink, fetchPosting, type Posting } from '../data/jobs';
import { updateResume, useFeedbacks, useResumes, createResume, setBaseResume, deleteResume } from '../data/resumes';
import { useAlerts, dismissAlertToday, markAlertRead } from '../data/notices';
import { Badge, Btn, Card, Chip, EmptyState, Field, Muted, Row, Screen, T, goBack, todayKey } from '../ui/kit';
import { ChipRow, confirmAction } from '../ui/form';
import { useTheme } from '../theme/Theme';
import { elevation } from '../theme/tokens';

function section(body: string) {
  return { subtitle: '', body };
}

function emptyContent(name: string): ResumeContent {
  return {
    basicInfo: { name, phone: '', email: '', birthDate: '', githubUrl: '', blogUrl: '' },
    coreCompetencies: { text: '' },
    experience: [],
    education: [],
    techStack: [],
    certifications: [],
    awards: [],
    trainingExperience: [],
    otherActivities: [],
    projects: [],
    selfIntroduction: {
      intro: section(''),
      motivation: section(''),
      challenge: section(''),
      growth: section(''),
      strengthsWeaknesses: section(''),
      aspiration: section(''),
    },
  };
}

const STATUS_TONE: Record<string, 'warning' | 'info' | 'success'> = { draft: 'warning', feedbackRequested: 'info', approved: 'success' };

/** 웹 이력서 관리의 「채운 섹션」 — 내용 모양이 조금 달라도 빈 값으로 채워 센다 */
function filledCount(resume: Resume): number {
  const c = (resume.content ?? {}) as Partial<ResumeContent>;
  const base = emptyContent('');
  const list = <K extends keyof ResumeContent>(key: K) => (Array.isArray(c[key]) ? c[key] : base[key]) as ResumeContent[K];
  try {
    const done = computeSections({
      ...base,
      basicInfo: { ...base.basicInfo, ...(c.basicInfo ?? {}) },
      coreCompetencies: { ...base.coreCompetencies, ...(c.coreCompetencies ?? {}) },
      experience: list('experience'),
      education: list('education'),
      techStack: list('techStack'),
      certifications: list('certifications'),
      awards: list('awards'),
      trainingExperience: list('trainingExperience'),
      otherActivities: list('otherActivities'),
      projects: list('projects'),
      selfIntroduction: { ...base.selfIntroduction, ...(c.selfIntroduction ?? {}) },
    });
    return ResumeSectionKeys.filter((key) => done[key] === true).length;
  } catch {
    return 0;
  }
}

function dateOf(value?: Date | string | null): string {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
}

function SectionBar({ filled, total, thin }: { filled: number; total: number; thin?: boolean }) {
  const { palette } = useTheme();
  const h = thin ? 4 : 6;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
      <View style={{ flex: 1, height: h, borderRadius: h / 2, backgroundColor: palette.surfaceVariant, overflow: 'hidden' }}>
        <View style={{ width: `${(filled / total) * 100}%`, height: h, borderRadius: h / 2, backgroundColor: palette.success }} />
      </View>
      <T variant="caption" tone="secondary">
        <T variant="caption" style={{ fontWeight: '700' }}>{filled}</T>/{total}
      </T>
    </View>
  );
}

function openResume(id: string) {
  router.push(`/(student)/resume/${encodeURIComponent(id)}` as never);
}

/** 바탕 이력서 카드 — 맞춤 이력서는 카드 안 아래쪽에 작은 줄로 펼친다 */
function ResumeCard({ resume, isBase, tailored }: { resume: Resume; isBase?: boolean; tailored: Resume[] }) {
  const { palette } = useTheme();
  const [open, setOpen] = useState(false);
  const total = ResumeSectionKeys.length;
  const meta = [
    dateOf(resume.updatedAt) ? `수정 ${dateOf(resume.updatedAt)}` : '',
    resume.feedbackCount > 0 ? `피드백 ${resume.feedbackCount}` : '피드백 없음',
  ].filter(Boolean).join(' · ');
  return (
    <Card style={[{ padding: 0, overflow: 'hidden' }, isBase ? { borderColor: palette.primary, borderWidth: 1.5 } : null]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${resume.title} 열기`}
        onPress={() => openResume(resume.id)}
        style={({ pressed }) => ({ paddingHorizontal: 20, paddingVertical: 18, gap: 14, opacity: pressed ? 0.85 : 1 })}
      >
        <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 12 }}>
          <View style={{ flex: 1, gap: 6 }}>
            {isBase ? (
              <T variant="label" tone="primary">기본 이력서</T>
            ) : null}
            <T variant="subtitle" numberOfLines={2}>{resume.title}</T>
          </View>
          <Badge label={ResumeStatusLabels[resume.status] ?? '작성 중'} tone={STATUS_TONE[resume.status] ?? 'warning'} />
        </View>
        <SectionBar filled={filledCount(resume)} total={total} />
        <T variant="caption" tone="secondary">{meta}</T>
      </Pressable>
      {tailored.length > 0 ? (
        <View style={{ borderTopWidth: 1, borderTopColor: palette.divider }}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`맞춤 이력서 ${tailored.length}개 ${open ? '접기' : '펼치기'}`}
            onPress={() => setOpen((prev) => !prev)}
            style={({ pressed }) => ({
              minHeight: 52,
              paddingHorizontal: 20,
              flexDirection: 'row',
              alignItems: 'center',
              gap: 6,
              backgroundColor: pressed ? palette.surfaceVariant : 'transparent',
            })}
          >
            <MaterialIcons name="subdirectory-arrow-right" size={18} color={palette.success} />
            <T variant="body" tone="success" style={{ flex: 1, fontWeight: '600' }}>맞춤 이력서 {tailored.length}개</T>
            <MaterialIcons name={open ? 'expand-less' : 'expand-more'} size={22} color={palette.textSecondary} />
          </Pressable>
          {open ? (
            <View style={{ paddingHorizontal: 16, paddingBottom: 16, gap: 10 }}>
              {tailored.map((child) => (
                <Pressable
                  key={child.id}
                  accessibilityRole="button"
                  accessibilityLabel={`${child.title} 열기`}
                  onPress={() => openResume(child.id)}
                  style={({ pressed }) => ({
                    paddingHorizontal: 16,
                    paddingVertical: 14,
                    gap: 10,
                    borderRadius: 12,
                    backgroundColor: palette.surfaceVariant,
                    opacity: pressed ? 0.85 : 1,
                  })}
                >
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <T variant="body" style={{ flex: 1, fontWeight: '600' }} numberOfLines={1}>{child.title}</T>
                    <Badge label={ResumeStatusLabels[child.status] ?? '작성 중'} tone={STATUS_TONE[child.status] ?? 'warning'} />
                  </View>
                  <SectionBar filled={filledCount(child)} total={total} thin />
                </Pressable>
              ))}
            </View>
          ) : null}
        </View>
      ) : null}
    </Card>
  );
}

/** 학생 이력서 목록 — 바탕 이력서만 카드로, 그걸로 만든 맞춤 이력서는 「맞춤 N」을 누르면 밑에 작은 카드로 */
function MyResumeList() {
  const { user } = useSession();
  const { palette } = useTheme();
  const all = useResumes().filter((resume) => resume.userId === user?.uid);
  const resumes = withoutPromotedWorkCopies(all.filter((resume) => !isApplyCopy(resume)));
  const base = resumes.find((resume) => resume.isBaseResume) ?? resumes.find((resume) => !isTailored(resume)) ?? resumes[0];
  const grouped = groupResumes(resumes, base);
  const cards = [
    ...(base ? [{ resume: base, children: grouped.baseTailored, isBase: true }] : []),
    ...grouped.rows.map((row) => ({ ...row, isBase: false })),
  ];
  return (
    <Screen
      title="이력서"
      onRefresh={refreshBootstrap}
      right={
        <Pressable accessibilityRole="button" accessibilityLabel="새 이력서" hitSlop={8} onPress={() => router.push('/(student)/resume/new' as never)}>
          <MaterialIcons name="add" size={26} color={palette.primary} />
        </Pressable>
      }
    >
      {cards.length === 0 ? (
        <Card style={{ gap: 12 }}>
          <EmptyState icon="description" text="작성한 이력서가 없습니다." />
          <Btn label="새 이력서 만들기" icon="add" onPress={() => router.push('/(student)/resume/new' as never)} />
        </Card>
      ) : null}
      <View style={{ gap: 16 }}>
        {cards.map((row) => (
          <ResumeCard key={row.resume.id} resume={row.resume} isBase={row.isBase} tailored={row.children} />
        ))}
      </View>
    </Screen>
  );
}

export function ResumeListPage({ canApprove = false }: { canApprove?: boolean }) {
  if (!canApprove) return <MyResumeList />;
  return <ReviewerResumeList />;
}

function ReviewerResumeList() {
  const resumes = useResumes();
  const { user } = useSession();
  const base = user?.role === 'instructor' ? '/(instructor)/resume' : '/(admin)/resume';
  return (
    <Screen title="이력서">
      {resumes.map((resume) => (
        <Row
          key={resume.id}
          title={resume.title}
          subtitle={`${resume.userDisplayName ?? ''} · ${ResumeStatusLabels[resume.status] ?? '작성 중'}`}
          onPress={() => router.push(`${base}/${encodeURIComponent(resume.id)}` as never)}
        />
      ))}
    </Screen>
  );
}

type IntroKey = keyof ResumeContent['selfIntroduction'];

const INTRO_FIELDS: { key: IntroKey; label: string }[] = [
  { key: 'growth', label: '성장 과정' },
  { key: 'motivation', label: '지원 동기' },
  { key: 'intro', label: '자기소개' },
  { key: 'challenge', label: '도전 경험' },
  { key: 'strengthsWeaknesses', label: '성격의 장단점' },
  { key: 'aspiration', label: '입사 후 포부' },
];

const EDU_STATUS = [
  { key: '졸업', label: '졸업' },
  { key: '재학', label: '재학' },
  { key: '수료', label: '수료' },
];

function newId(): string {
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

/** 넓은 화면(아이패드)에서는 칸을 두 줄로 나란히 놓는다 */
function Pair({ wide, children }: { wide: boolean; children: ReactNode }) {
  if (!wide) return <View style={{ gap: 12 }}>{children}</View>;
  return <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>{Children.map(children, (child) => <View style={{ flexBasis: '48%', flexGrow: 1 }}>{child}</View>)}</View>;
}

function SectionCard({ title, onAdd, children }: { title: string; onAdd?: () => void; children: ReactNode }) {
  return (
    <Card style={{ gap: 12 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <T variant="subtitle">{title}</T>
        {onAdd ? (
          <View style={{ minWidth: 92 }}>
            <Btn label="추가" icon="add" tone="soft" onPress={onAdd} />
          </View>
        ) : null}
      </View>
      {children}
    </Card>
  );
}

function ItemBox({ onRemove, children }: { onRemove: () => void; children: ReactNode }) {
  const { palette } = useTheme();
  return (
    <View style={{ gap: 10, padding: 12, borderRadius: 12, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.surfaceVariant }}>
      {children}
      <Pressable accessibilityRole="button" accessibilityLabel="이 항목 삭제" onPress={onRemove} style={{ alignSelf: 'flex-end', paddingVertical: 6, paddingHorizontal: 4 }}>
        <T variant="caption" tone="error">이 항목 삭제</T>
      </Pressable>
    </View>
  );
}

export function ResumeEditPage({ id }: { id: string }) {
  const { user } = useSession();
  const { width } = useWindowDimensions();
  const wide = width >= 700;
  const resumes = useResumes();
  const existing = resumes.find((resume) => resume.id === id);
  const mine = resumes.filter((resume) => resume.userId === user?.uid);
  const feedbacks = useFeedbacks(existing?.id ?? '');
  const [title, setTitle] = useState(existing?.title ?? '새 이력서');
  const [draft, setDraft] = useState<ResumeContent>(() => existing?.content ?? emptyContent(user?.displayName ?? ''));
  const [tech, setTech] = useState('');
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);

  // 마지막으로 저장(또는 불러온) 내용 — 이것과 다르면 「저장 안 된 변경」이다
  const snap = (t: string, c: ResumeContent) => JSON.stringify([t, c]);
  const savedSnap = useRef<string | null>(null);
  // 처음 연 상태를 기준으로 삼는다 — 아무것도 안 고친 새 이력서는 「저장 안 됨」이 아니다
  if (savedSnap.current === null) savedSnap.current = snap(title, draft);
  // 새 이력서는 처음 저장할 때 만들어지고, 그 뒤로는 그 id 를 고친다
  const [createdId, setCreatedId] = useState('');
  const targetId = existing?.id ?? createdId;
  const dirty = snap(title, draft) !== savedSnap.current;

  // 처음 열 때 아직 목록이 안 와 있었으면, 도착한 내용으로 채운다
  const [loadedId, setLoadedId] = useState(existing?.id ?? '');
  useEffect(() => {
    if (existing && loadedId !== existing.id) {
      setLoadedId(existing.id);
      setTitle(existing.title);
      setDraft(existing.content);
      savedSnap.current = snap(existing.title, existing.content);
    }
  }, [existing, loadedId]);

  const patch = (change: Partial<ResumeContent>) => setDraft((prev) => ({ ...prev, ...change }));
  const basic = (key: keyof ResumeContent['basicInfo'], value: string) => patch({ basicInfo: { ...draft.basicInfo, [key]: value } });
  const intro = (key: IntroKey, body: string) =>
    patch({ selfIntroduction: { ...draft.selfIntroduction, [key]: { ...(draft.selfIntroduction[key] ?? section('')), body } } });
  function editList<K extends 'experience' | 'education' | 'projects'>(key: K, index: number, change: Partial<ResumeContent[K][number]>) {
    patch({ [key]: draft[key].map((row, i) => (i === index ? { ...row, ...change } : row)) } as Partial<ResumeContent>);
  }
  function removeFrom<K extends 'experience' | 'education' | 'projects' | 'techStack'>(key: K, index: number) {
    patch({ [key]: draft[key].filter((_, i) => i !== index) } as Partial<ResumeContent>);
  }

  /** 웹과 같다 — 비어 있는 칸만 마이페이지 값으로 채우고, 이력서에 없는 기술 스택을 숙련도째 더한다 */
  const fillFromMyPage = () => {
    if (!user) return;
    const info = draft.basicInfo;
    const next = {
      ...info,
      name: info.name || user.displayName || '',
      email: info.email || user.personalEmail || user.email || '',
      birthDate: info.birthDate || (user.birthDate ?? '').replace(/-/g, '.'),
      githubUrl: info.githubUrl || (user.socialLinks?.github ?? ''),
      blogUrl: info.blogUrl || (user.socialLinks?.blog ?? ''),
    };
    const filledFields = (Object.keys(next) as (keyof typeof next)[]).filter((key) => next[key] !== info[key]).length;
    const norm = (name: string) => name.replace(/\s+/g, '').toLowerCase();
    const have = new Set(draft.techStack.map((row) => norm(row.name)));
    const freshTech = (user.techStack ?? []).filter((row) => row.name.trim() && !have.has(norm(row.name)));
    patch({
      basicInfo: next,
      techStack: [...draft.techStack, ...freshTech.map((row) => ({ id: newId(), name: row.name.trim(), level: row.level ?? '' }))],
    });
    const parts = [filledFields > 0 ? `기본 정보 ${filledFields}칸` : '', freshTech.length > 0 ? `기술 ${freshTech.length}개` : ''].filter(Boolean);
    setMessage(parts.length > 0 ? `마이페이지에서 ${parts.join(' · ')}를 채웠어요. 저장을 눌러 주세요.` : '채울 마이페이지 정보가 없어요.');
  };

  const clock = () => new Date().toLocaleTimeString('ko-KR', { hour: 'numeric', minute: '2-digit' });

  /** 지금 내용을 저장한다. auto 면 조용히(자동 저장), 실패해도 다음에 다시 시도한다 */
  const persist = async (auto = false): Promise<boolean> => {
    if (!user) return false;
    const current = snap(title, draft);
    if (current === savedSnap.current) return true;
    setSaving(true);
    if (!auto) setMessage('');
    try {
      if (targetId) {
        await updateResume(targetId, { title, content: draft });
      } else {
        const newId = await createResume(
          { title, content: draft, userId: user.uid, userDisplayName: user.displayName, status: 'draft', sections: {}, isBaseResume: false, feedbackCount: 0, lastSeenFeedbackCount: 0, readFeedbackIds: [], revisionCount: 0 } as Omit<Resume, 'id' | 'updatedAt'>,
          user.cohortId,
        );
        setCreatedId(newId);
      }
      savedSnap.current = current;
      setMessage(auto ? `자동 저장됨 · ${clock()}` : `저장했습니다 · ${clock()}`);
      return true;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '저장하지 못했습니다.');
      return false;
    } finally {
      setSaving(false);
    }
  };
  const save = () => {
    if (!saving) void persist(false);
  };

  // 자동 저장 — 이미 만들어진 이력서는 입력을 멈추고 2.5초 뒤 저장한다(새 이력서는 처음 한 번은 직접 저장)
  useEffect(() => {
    if (!dirty || !targetId || saving) return;
    const timer = setTimeout(() => void persist(true), 2500);
    return () => clearTimeout(timer);
  }, [title, draft, targetId, saving]);

  // 저장 안 된 내용이 있는데 뒤로 가면 묻는다
  const navigation = useNavigation();
  const leaveGuard = useRef({ dirty, persist });
  leaveGuard.current = { dirty, persist };
  useEffect(() => {
    return navigation.addListener('beforeRemove', (event) => {
      if (!leaveGuard.current.dirty) return;
      event.preventDefault();
      Alert.alert('저장하지 않은 내용이 있어요', '이대로 나가면 고친 내용이 사라져요.', [
        { text: '계속 쓰기', style: 'cancel' },
        { text: '저장하지 않고 나가기', style: 'destructive', onPress: () => navigation.dispatch(event.data.action) },
        {
          text: '저장하고 나가기',
          onPress: () => {
            void leaveGuard.current.persist(false).then((ok) => {
              if (ok) navigation.dispatch(event.data.action);
            });
          },
        },
      ]);
    });
  }, [navigation]);

  return (
    <Screen
      title="이력서 편집"
      footer={
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingTop: 10, paddingBottom: 18 }}>
          <T variant="caption" tone={dirty && !saving ? 'warning' : 'secondary'} style={{ flex: 1 }} numberOfLines={2}>
            {saving ? '저장 중…' : dirty ? (targetId ? '고친 내용이 있어요 · 곧 자동 저장돼요' : '아직 저장하지 않았어요') : message || (existing ? ResumeStatusLabels[existing.status] ?? '작성 중' : '아직 저장하지 않았어요')}
          </T>
          <View style={{ minWidth: 120 }}>
            <Btn label={saving ? '저장 중…' : '저장'} icon="save" disabled={saving || !dirty} onPress={save} />
          </View>
        </View>
      }
    >
      <Field label="이력서 제목" value={title} onChangeText={setTitle} />

      <SectionCard title="기본 정보">
        {!existing || existing.userId === user?.uid ? (
          <Btn label="마이페이지 정보로 빈 칸 채우기" icon="person" tone="soft" onPress={fillFromMyPage} />
        ) : null}
        <Pair wide={wide}>
          <Field label="이름" value={draft.basicInfo.name} onChangeText={(v) => basic('name', v)} />
          <Field label="생년월일" value={draft.basicInfo.birthDate} onChangeText={(v) => basic('birthDate', v)} placeholder="YYYY-MM-DD" />
          <Field label="전화" value={draft.basicInfo.phone} onChangeText={(v) => basic('phone', v)} placeholder="010-0000-0000" />
          <Field label="이메일" value={draft.basicInfo.email} onChangeText={(v) => basic('email', v)} keyboard="email-address" />
          <Field label="GitHub" value={draft.basicInfo.githubUrl} onChangeText={(v) => basic('githubUrl', v)} keyboard="url" />
          <Field label="블로그" value={draft.basicInfo.blogUrl} onChangeText={(v) => basic('blogUrl', v)} keyboard="url" />
        </Pair>
      </SectionCard>

      <SectionCard title="핵심 역량">
        <Field label="한 문단 소개" value={draft.coreCompetencies?.text ?? ''} onChangeText={(text) => patch({ coreCompetencies: { text } })} multiline />
      </SectionCard>

      <SectionCard
        title="경력"
        onAdd={() => patch({ experience: [...draft.experience, { id: newId(), company: '', role: '', startDate: '', endDate: '', isCurrent: false, description: '' }] })}
      >
        {draft.experience.length === 0 ? <Muted>추가 버튼으로 경력을 넣어 주세요.</Muted> : null}
        {draft.experience.map((row, i) => (
          <ItemBox key={row.id} onRemove={() => removeFrom('experience', i)}>
            <Pair wide={wide}>
              <Field label="회사" value={row.company} onChangeText={(v) => editList('experience', i, { company: v })} />
              <Field label="직무" value={row.role} onChangeText={(v) => editList('experience', i, { role: v })} />
              <Field label="시작" value={row.startDate} onChangeText={(v) => editList('experience', i, { startDate: v })} placeholder="YYYY-MM" />
              <Field label="종료" value={row.endDate} onChangeText={(v) => editList('experience', i, { endDate: v })} placeholder="YYYY-MM 또는 재직 중" />
            </Pair>
            <Field label="한 일" value={row.description} onChangeText={(v) => editList('experience', i, { description: v })} multiline />
          </ItemBox>
        ))}
      </SectionCard>

      <SectionCard
        title="학력"
        onAdd={() => patch({ education: [...draft.education, { id: newId(), school: '', major: '', startDate: '', endDate: '', status: '졸업' }] })}
      >
        {draft.education.length === 0 ? <Muted>추가 버튼으로 학력을 넣어 주세요.</Muted> : null}
        {draft.education.map((row, i) => (
          <ItemBox key={row.id} onRemove={() => removeFrom('education', i)}>
            <Pair wide={wide}>
              <Field label="학교" value={row.school} onChangeText={(v) => editList('education', i, { school: v })} />
              <Field label="전공" value={row.major} onChangeText={(v) => editList('education', i, { major: v })} />
              <Field label="입학" value={row.startDate} onChangeText={(v) => editList('education', i, { startDate: v })} placeholder="YYYY-MM" />
              <Field label="졸업" value={row.endDate} onChangeText={(v) => editList('education', i, { endDate: v })} placeholder="YYYY-MM" />
            </Pair>
            <ChipRow label="상태" options={EDU_STATUS} value={row.status || '졸업'} onChange={(status) => editList('education', i, { status })} />
          </ItemBox>
        ))}
      </SectionCard>

      <SectionCard title="기술 스택">
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {draft.techStack.map((row, i) => (
            <Chip key={row.id} label={`${row.name}  ✕`} onPress={() => removeFrom('techStack', i)} />
          ))}
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 8 }}>
          <View style={{ flex: 1 }}>
            <Field label="기술 이름" value={tech} onChangeText={setTech} placeholder="예: Python" />
          </View>
          <View style={{ minWidth: 92 }}>
            <Btn
              label="추가"
              tone="soft"
              disabled={!tech.trim()}
              onPress={() => {
                patch({ techStack: [...draft.techStack, { id: newId(), name: tech.trim(), level: '' }] });
                setTech('');
              }}
            />
          </View>
        </View>
      </SectionCard>

      <SectionCard
        title="프로젝트"
        onAdd={() => patch({ projects: [...draft.projects, { id: newId(), name: '', startDate: '', endDate: '', role: '', techStack: '', description: '', url: '' }] })}
      >
        {draft.projects.length === 0 ? <Muted>추가 버튼으로 프로젝트를 넣어 주세요.</Muted> : null}
        {draft.projects.map((row, i) => (
          <ItemBox key={row.id} onRemove={() => removeFrom('projects', i)}>
            <Pair wide={wide}>
              <Field label="프로젝트 이름" value={row.name} onChangeText={(v) => editList('projects', i, { name: v })} />
              <Field label="역할" value={row.role} onChangeText={(v) => editList('projects', i, { role: v })} />
              <Field label="사용 기술" value={row.techStack} onChangeText={(v) => editList('projects', i, { techStack: v })} />
              <Field label="링크" value={row.url} onChangeText={(v) => editList('projects', i, { url: v })} keyboard="url" />
              <Field label="시작" value={row.startDate} onChangeText={(v) => editList('projects', i, { startDate: v })} placeholder="YYYY-MM" />
              <Field label="종료" value={row.endDate} onChangeText={(v) => editList('projects', i, { endDate: v })} placeholder="YYYY-MM" />
            </Pair>
            <Field label="설명" value={row.description} onChangeText={(v) => editList('projects', i, { description: v })} multiline />
          </ItemBox>
        ))}
      </SectionCard>

      <SectionCard title="자기소개서">
        <Pair wide={wide}>
          {INTRO_FIELDS.map((field) => {
            const body = draft.selfIntroduction[field.key]?.body ?? '';
            return <Field key={field.key} label={`${field.label} · ${body.length}자`} value={body} onChangeText={(v) => intro(field.key, v)} multiline />;
          })}
        </Pair>
      </SectionCard>

      {existing ? (
        <View style={{ gap: 8 }}>
          <Btn label="기본 이력서로 지정" tone="ghost" onPress={() => void setBaseResume(existing.id, mine)} />
          <Btn label="PDF로 공유" tone="ghost" onPress={() => void printResume({ ...existing, title, content: draft })} />
          <Btn label="이력서 삭제" tone="danger" onPress={() => confirmAction('이력서 삭제', `'${existing.title}' 이력서를 삭제할까요?`, () => {
            void deleteResume(existing.id).then(() => {
              leaveGuard.current.dirty = false; // 지운 이력서는 저장할 것도 없다
              goBack();
            }).catch((error: unknown) => setMessage(error instanceof Error ? error.message : '삭제에 실패했습니다.'));
          })} />
        </View>
      ) : null}
      {feedbacks.length > 0 ? <Muted>강사 피드백</Muted> : null}
      {feedbacks.map((row) => <Row key={row.id} title={row.authorName} subtitle={row.content} />)}
    </Screen>
  );
}

function esc(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
}

async function printResume(resume: Resume): Promise<void> {
  const c = resume.content;
  const block = (heading: string, body: string) => (body.trim() ? `<h3>${esc(heading)}</h3><p>${esc(body)}</p>` : '');
  const html = [
    `<html><head><meta charset="utf-8"><style>body{font-family:-apple-system,sans-serif;padding:24px;color:#111}h1{margin:0 0 4px}h2{margin:24px 0 8px;border-bottom:1px solid #ddd;padding-bottom:4px}h3{margin:14px 0 4px}p{margin:0;line-height:1.6}</style></head><body>`,
    `<h1>${esc(resume.title)}</h1>`,
    `<p>${esc([c.basicInfo.name, c.basicInfo.phone, c.basicInfo.email, c.basicInfo.githubUrl, c.basicInfo.blogUrl].filter(Boolean).join(' · '))}</p>`,
    c.coreCompetencies?.text ? `<h2>핵심 역량</h2><p>${esc(c.coreCompetencies.text)}</p>` : '',
    c.experience.length ? `<h2>경력</h2>${c.experience.map((r) => block(`${r.company} · ${r.role} (${r.startDate}~${r.endDate})`, r.description || ' ')).join('')}` : '',
    c.education.length ? `<h2>학력</h2>${c.education.map((r) => `<p>${esc(`${r.school} ${r.major} · ${r.status} (${r.startDate}~${r.endDate})`)}</p>`).join('')}` : '',
    c.techStack.length ? `<h2>기술 스택</h2><p>${esc(c.techStack.map((t) => t.name).join(', '))}</p>` : '',
    c.projects.length ? `<h2>프로젝트</h2>${c.projects.map((r) => block(`${r.name} · ${r.role} (${r.startDate}~${r.endDate})`, [r.techStack, r.description, r.url].filter(Boolean).join('\n') || ' ')).join('')}` : '',
    `<h2>자기소개서</h2>${INTRO_FIELDS.map((f) => block(f.label, c.selfIntroduction[f.key]?.body ?? '')).join('')}`,
    '</body></html>',
  ].join('');
  const file = await Print.printToFileAsync({ html });
  if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(file.uri);
}

export function ApplyPage() {
  const [jobId, setJobId] = useState('');
  const [posting, setPosting] = useState('');
  const [capture, setCapture] = useState('');
  const [message, setMessage] = useState('');
  return (
    <Screen title="공고 맞춤 지원">
      <Btn label="추천 공고" tone="ghost" onPress={() => router.push('/(student)/jobs' as never)} />
      <Field label="공고 번호" value={jobId} onChangeText={setJobId} />
      <Btn label="공고 불러오기" onPress={() => {
        void fetchPosting(jobId).then((raw) => {
          const text = String(raw.description ?? raw.content ?? raw.title ?? '');
          setPosting(plain(text) || text);
        }).catch((error: unknown) => setMessage(error instanceof Error ? error.message : '공고를 찾지 못했습니다.'));
      }} />
      {posting ? <Card><T>{posting}</T></Card> : null}
      <Muted>자주 나오는 문항</Muted>
      {COMMON_QUESTIONS.map((question) => <Row key={question.key} title={question.question} subtitle={`${question.limit}자`} />)}
      <Btn label="지원 화면 캡처" tone="ghost" onPress={() => {
        void ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'] }).then((result) => {
          if (!result.canceled) setCapture(result.assets[0]?.uri ?? '');
        });
      }} />
      {capture ? <Muted>첨부함 {capture.split('/').pop()}</Muted> : null}
      <Btn label="지원 사이트로" onPress={() => {
        void fetchApplyLink(jobId).then((url) => (url ? Linking.openURL(url) : setMessage('지원 링크가 없습니다.')));
      }} />
      {message ? <T tone="secondary">{message}</T> : null}
    </Screen>
  );
}

export function JobsPage() {
  const [rows, setRows] = useState<Posting[]>([]);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    void featuredPostings().then(setRows).catch(() => setRows([])).finally(() => setLoaded(true));
  }, []);
  return (
    <Screen title="채용 공고" loading={!loaded}>
      {rows.map((job) => (
        <Row key={job.jobId} title={`${job.company} · ${job.title}`} subtitle={job.region} onPress={() => router.push(`/(student)/jobs/${job.jobId}` as never)} />
      ))}
    </Screen>
  );
}

export function JobPage({ id }: { id: string }) {
  const [text, setText] = useState('');
  const [url, setUrl] = useState('');
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    void fetchPosting(id).then((raw) => {
      const body = String(raw.description ?? raw.content ?? '');
      setText(plain(body) || body);
      setUrl(String(raw.url ?? raw.applyUrl ?? ''));
    }).finally(() => setLoaded(true));
  }, [id]);
  return (
    <Screen title="공고" loading={!loaded && !text}>
      <Card><T>{text || '본문이 없습니다.'}</T></Card>
      {url ? <Btn label="지원 사이트" onPress={() => void Linking.openURL(url)} /> : null}
    </Screen>
  );
}

function plain(text: string): string {
  return formatPostingText(text).map((block: PostingBlock) => {
    if (block.type === 'form') {
      return block.rows.map((row) => ('value' in row ? `${row.label} ${row.value}` : row.label)).join('\n');
    }
    if (block.type === 'image') return block.lines.join('\n');
    return block.text;
  }).join('\n');
}

export function AlertHost() {
  const { user } = useSession();
  const { palette } = useTheme();
  const seen = useSeenAlerts();
  const dismissed = useDismissedToday(user?.uid ?? '', todayKey());
  const alerts = visibleAlerts(useAlerts());
  const [hidden, setHidden] = useState<string[]>([]);
  // 이 계정이 이미 확인한 알림 · 오늘 하루 닫은 알림은 다시 띄우지 않는다 — 종 아이콘(알림 목록)에서 다시 볼 수 있다
  const queue = alerts.filter((popup) => !hidden.includes(popup.id) && !seen.has(popup.id) && !dismissed.has(popup.id));
  const current = queue[0];
  if (!user) return null;

  const close = (dismissToday: boolean) => {
    if (!current) return;
    if (dismissToday) void dismissAlertToday(current.id, todayKey(), user?.uid).catch(() => undefined);
    else markAlertRead(current.id);
    setHidden((prev) => [...prev, current.id]);
  };

  return (
    <Modal visible={Boolean(current)} transparent animationType="fade" statusBarTranslucent onRequestClose={() => close(false)}>
      <View style={alertStyles.backdrop}>
        <View style={[alertStyles.sheet, elevation, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          <View style={[alertStyles.icon, { backgroundColor: palette.primaryLight }]}>
            <MaterialIcons name="campaign" size={30} color={palette.primary} />
          </View>
          {queue.length > 1 ? (
            <T variant="label" tone="primary">알림 1 / {queue.length}</T>
          ) : null}
          <T variant="title" style={{ textAlign: 'center', fontSize: 19 }}>{current?.title}</T>
          <ScrollView style={alertStyles.body} contentContainerStyle={{ paddingVertical: 2 }}>
            <T tone="secondary" style={{ textAlign: 'center', lineHeight: 22 }}>{current?.content}</T>
          </ScrollView>
          <View style={alertStyles.actions}>
            <Btn label="확인" onPress={() => close(false)} />
            <Pressable accessibilityRole="button" onPress={() => close(true)} hitSlop={8} style={alertStyles.later}>
              <T variant="caption" tone="secondary">오늘 하루 보지 않기</T>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

/** 종 아이콘에서 여는 알림 목록 — 확인한 알림 팝업도 다시 볼 수 있다 */
export function AlertsPage() {
  const { user } = useSession();
  const { palette } = useTheme();
  const seen = useSeenAlerts();
  const alerts = [...visibleAlerts(useAlerts())].sort(
    (a, b) => new Date(b.createdAt ?? 0).getTime() - new Date(a.createdAt ?? 0).getTime(),
  );
  const [openId, setOpenId] = useState<string | null>(null);
  const toggle = (id: string) => {
    setOpenId((prev) => (prev === id ? null : id));
    if (!seen.has(id)) markAlertRead(id);
  };
  return (
    <Screen title="알림" onRefresh={refreshBootstrap}>
      {alerts.length === 0 ? <Card><EmptyState icon="notifications-none" text="지금 받은 알림이 없습니다." /></Card> : null}
      {alerts.map((popup) => {
        const unread = !seen.has(popup.id);
        const open = openId === popup.id;
        return (
          <Card key={popup.id} onPress={() => toggle(popup.id)} style={{ gap: 10 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: unread ? palette.error : 'transparent' }} />
              <View style={{ flex: 1, gap: 2 }}>
                <T variant="subtitle" numberOfLines={open ? undefined : 1} style={{ fontWeight: unread ? '700' : '500' }}>{popup.title}</T>
                <T variant="caption" tone="secondary">
                  {[popup.authorName, dateOf(popup.createdAt)].filter(Boolean).join(' · ')}
                </T>
              </View>
              <MaterialIcons name={open ? 'expand-less' : 'expand-more'} size={22} color={palette.textSecondary} />
            </View>
            {open ? (
              <View style={{ gap: 10, paddingLeft: 18 }}>
                <T style={{ lineHeight: 22 }}>{popup.content}</T>
                {popup.linkUrl ? <Btn label="링크 열기" icon="open-in-new" tone="ghost" onPress={() => void Linking.openURL(popup.linkUrl ?? '')} /> : null}
              </View>
            ) : null}
          </Card>
        );
      })}
    </Screen>
  );
}

/** 대시보드 위의 종 — 안 읽은 알림 수를 빨간 점으로 */
export function AlertBell() {
  const { palette } = useTheme();
  const seen = useSeenAlerts();
  const unread = visibleAlerts(useAlerts()).filter((popup) => !seen.has(popup.id)).length;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={unread > 0 ? `알림 ${unread}개 안 읽음` : '알림'}
      hitSlop={8}
      onPress={() => router.push('/(student)/alerts' as never)}
      style={({ pressed }) => ({ width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center', backgroundColor: pressed ? palette.primaryLight : 'transparent' })}
    >
      <MaterialIcons name={unread > 0 ? 'notifications-active' : 'notifications-none'} size={24} color={unread > 0 ? palette.primary : palette.textSecondary} />
      {unread > 0 ? (
        <View style={{ position: 'absolute', top: 4, right: 3, minWidth: 17, height: 17, paddingHorizontal: 4, borderRadius: 9, backgroundColor: palette.error, alignItems: 'center', justifyContent: 'center' }}>
          <T variant="label" style={{ color: '#fff', fontSize: 10 }}>{unread > 9 ? '9+' : unread}</T>
        </View>
      ) : null}
    </Pressable>
  );
}

const alertStyles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.55)', alignItems: 'center', justifyContent: 'center', padding: 28 },
  sheet: {
    width: '100%',
    maxWidth: 380,
    borderRadius: 22,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 22,
    paddingTop: 26,
    paddingBottom: 14,
    alignItems: 'center',
    gap: 12,
  },
  icon: { width: 60, height: 60, borderRadius: 30, alignItems: 'center', justifyContent: 'center' },
  body: { maxHeight: 280, alignSelf: 'stretch' },
  actions: { alignSelf: 'stretch', gap: 4, marginTop: 6 },
  later: { alignItems: 'center', paddingVertical: 10 },
});
