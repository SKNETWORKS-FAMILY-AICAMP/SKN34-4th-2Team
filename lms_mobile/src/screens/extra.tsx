import * as ImagePicker from 'expo-image-picker';
import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { MaterialIcons } from '@expo/vector-icons';
import { Linking, Modal, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { formatPostingText, type PostingBlock } from '@web/features/jobs/postingText';
import { COMMON_QUESTIONS } from '@web/features/jobApply/companyQuestions';
import { ResumeStatusLabels } from '@web/domain/constants';
import type { Resume, ResumeContent } from '@web/domain/types';

import { useSession } from '../auth/session';
import { featuredPostings, fetchApplyLink, fetchPosting, type Posting } from '../data/jobs';
import { requestReview, updateResume, useFeedbacks, useResumes, createResume, setBaseResume, deleteResume } from '../data/resumes';
import { useAlerts, dismissAlertToday, markAlertRead } from '../data/notices';
import { Btn, Card, Field, Muted, Row, Screen, T, goBack, todayKey } from '../ui/kit';
import { confirmAction } from '../ui/form';
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

export function ResumeListPage({ canApprove = false }: { canApprove?: boolean }) {
  const { user } = useSession();
  const resumes = useResumes().filter((resume) => (canApprove ? true : resume.userId === user?.uid));
  return (
    <Screen title="이력서">
      {!canApprove ? <Btn label="새 이력서" onPress={() => router.push('/(student)/resume/new' as never)} /> : null}
      {resumes.map((resume) => (
        <Row
          key={resume.id}
          title={resume.title}
          subtitle={`${resume.userDisplayName ?? ''} · ${ResumeStatusLabels[resume.status] ?? '작성 중'}`}
          onPress={() => router.push(`${canApprove ? '/(admin)/resume' : '/(student)/resume'}/${encodeURIComponent(resume.id)}` as never)}
        />
      ))}
    </Screen>
  );
}

export function ResumeEditPage({ id }: { id: string }) {
  const { user } = useSession();
  const existing = useResumes().find((resume) => resume.id === id);
  const [title, setTitle] = useState(existing?.title ?? '새 이력서');
  const [name, setName] = useState(existing?.content.basicInfo.name ?? user?.displayName ?? '');
  const [phone, setPhone] = useState(existing?.content.basicInfo.phone ?? '');
  const [growth, setGrowth] = useState(existing?.content.selfIntroduction.growth.body ?? '');
  const [motivation, setMotivation] = useState(existing?.content.selfIntroduction.motivation.body ?? '');
  const [message, setMessage] = useState('');
  const mine = useResumes().filter((resume) => resume.userId === user?.uid);
  const feedbacks = useFeedbacks(existing?.id ?? '');
  const [review, setReview] = useState('');

  function content(): ResumeContent {
    const base = existing?.content ?? emptyContent(name);
    return {
      ...base,
      basicInfo: { ...base.basicInfo, name, phone },
      selfIntroduction: { ...base.selfIntroduction, growth: section(growth), motivation: section(motivation) },
    };
  }

  return (
    <Screen title="이력서 편집">
      <Field label="제목" value={title} onChangeText={setTitle} />
      <Field label="이름" value={name} onChangeText={setName} />
      <Field label="전화" value={phone} onChangeText={setPhone} />
      <Field label="성장 과정" value={growth} onChangeText={setGrowth} multiline />
      <Field label="지원 동기" value={motivation} onChangeText={setMotivation} multiline />
      {message ? <T tone="secondary">{message}</T> : null}
      <Btn label="저장" onPress={() => {
        if (!user) return;
        const patch = { title, content: content(), userId: user.uid, userDisplayName: user.displayName, status: 'draft' as const, sections: {}, isBaseResume: false, feedbackCount: 0, lastSeenFeedbackCount: 0, readFeedbackIds: [], revisionCount: 0 };
        const job = existing
          ? updateResume(existing.id, patch)
          : createResume(patch, user.cohortId).then(() => undefined);
        void job.then(() => setMessage('저장했습니다.')).catch((error: unknown) => setMessage(error instanceof Error ? error.message : '실패'));
      }} />
      {existing ? (
        <>
          <Btn label="기본 이력서로" tone="ghost" onPress={() => void setBaseResume(existing.id, mine)} />
          <Btn label="PDF로 공유" tone="ghost" onPress={() => void printResume(existing)} />
          <Btn label="첨삭 받기" tone="ghost" onPress={() => {
            void requestReview(existing.id).then((result) => {
              const lines = (result.suggestions ?? []).map((item) => item.reason).join('\n');
              setReview(result.summary ?? (lines || '제안이 없습니다.'));
            }).catch((error: unknown) => setReview(error instanceof Error ? error.message : '첨삭에 실패했습니다.'));
          }} />
          <Btn label="삭제" tone="danger" onPress={() => confirmAction('이력서 삭제', `'${existing.title}' 이력서를 삭제할까요?`, () => {
            void deleteResume(existing.id).then(goBack).catch((error: unknown) => setMessage(error instanceof Error ? error.message : '삭제에 실패했습니다.'));
          })} />
        </>
      ) : null}
      {review ? <Card><T>{review}</T></Card> : null}
      {feedbacks.map((row) => <Row key={row.id} title={row.authorName} subtitle={row.content} />)}
    </Screen>
  );
}

async function printResume(resume: Resume): Promise<void> {
  const html = `<h1>${resume.title}</h1><p>${resume.content.basicInfo.name}</p><p>${resume.content.selfIntroduction.growth.body}</p><p>${resume.content.selfIntroduction.motivation.body}</p>`;
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
  const alerts = useAlerts().filter((popup) => popup.isActive);
  const [hidden, setHidden] = useState<string[]>([]);
  const queue = alerts.filter((popup) => !hidden.includes(popup.id));
  const current = queue[0];
  if (!user) return null;

  const close = (dismissToday: boolean) => {
    if (!current) return;
    if (dismissToday) void dismissAlertToday(current.id, todayKey());
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
