import { MaterialIcons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useState, type ReactNode } from 'react';
import { Alert, Linking, Pressable, Text, View, useWindowDimensions } from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import Markdown from 'react-native-markdown-display';
import {
  AttendanceLabels,
} from '@web/domain/constants';
import { RoutePaths } from '@web/app/routePaths';
import {
  EVIDENCE_MAX_BYTES,
  IssueTypeLabels,
  IssueTypes,
  LeaveTypeLabels,
  LeaveTypes,
  REQUEST_FUTURE_DAYS,
  REQUEST_PAST_DAYS,
  RequestStatusLabels,
  RequestStatusTones,
  draftError,
  labelOf,
  requestDateRange,
  timeFieldsFor,
  type AttendanceRequestDraft,
} from '@web/features/attendance/attendanceRequest';
import { lessonDays } from '@web/features/study/lessonDays';
import { EVIDENCE_LABEL, STATUS_LABEL, STATUS_TONE, periodLabel } from '@web/features/quests/questLabels';
import type {
  AttendanceIssue,
  AttendanceIssueType,
  FormAnswer,
  FormQuestion,
  OfficialLeaveType,
  Quest,
} from '@web/domain/types';

import { useSession } from '../auth/session';
import { useIssues, submitAttendanceRequest, cancelAttendanceRequest } from '../data/attendance';
import { useFormResponses, useFormTasks, markFormResponded, submitFormResponse } from '../data/forms';
import { WEB_URL } from '../data/http';
import { askCoach, chatHistory, streamChatbot } from '../data/jobs';
import { useTransactions } from '../data/mileage';
import { addComment, addPost, likePost, useComments, useNotices, usePosts } from '../data/notices';
import { refreshBootstrap, useBootstrap, useDb } from '../data/query';
import { useQuests, submitQuest } from '../data/quests';
import { uploadEvidence } from '../data/records';
import { useRooms, useTeams } from '../data/seating';
import { useNotes, useSources } from '../data/study';
import { appNav, navIcon, navLabel } from '../nav/webNav';
import { SeatGrid } from '../ui/SeatGrid';
import {
  Avatar,
  Badge,
  Btn,
  Callout,
  Card,
  Chip,
  Composer,
  EmptyState,
  Fab,
  Field,
  ListGroup,
  ListItem,
  Muted,
  QuickAction,
  Row,
  Screen,
  SectionHeader,
  Segmented,
  StatTile,
  T,
  fmt,
  todayKey,
  type IconName,
  type Tone,
} from '../ui/kit';
import { useTheme } from '../theme/Theme';
import { AlertHost } from './extra';
import { EvidencePicker, type PickedFile } from './records';
function go(path: string) {
  router.push(path as never);
}

export function DashboardPage() {
  const { user } = useSession();
  const boot = useBootstrap();
  const db = boot.data;
  const { palette } = useTheme();
  const notices = useNotices().slice(0, 5);
  const tasks = useFormTasks();
  const responses = useFormResponses();
  const today = todayKey();
  const attendance = (db?.attendances ?? []).find((row) => row.userId === user?.uid && row.dateKey === today);
  const status = attendance?.status;
  const statusTone = status ? AttendanceTones[status] ?? 'neutral' : 'neutral';
  const now = Date.now();
  const pendingForms = tasks.filter(
    (task) =>
      task.published &&
      new Date(task.dueAt).getTime() > now &&
      !responses.some((row) => row.taskId === task.id && row.userId === user?.uid),
  );
  const studentMenu = appNav('student').flatMap((section) => section.items);
  const attendanceLabel = navLabel(RoutePaths.attendanceRequest, '출결 신청');
  const hour = new Date().getHours();
  const greeting = hour < 12 ? '좋은 아침이에요' : hour < 18 ? '오늘도 힘내요' : '오늘도 수고했어요';

  return (
    <Screen
      title={navLabel(RoutePaths.dashboard, '대시보드')}
      back={false}
      right={
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={attendanceLabel}
          hitSlop={8}
          onPress={() => go('/(student)/attendance')}
          style={({ pressed }) => ({
            flexDirection: 'row',
            alignItems: 'center',
            gap: 6,
            paddingHorizontal: 10,
            paddingVertical: 8,
            borderRadius: 8,
            backgroundColor: pressed ? palette.primaryLight : 'transparent',
          })}
        >
          <MaterialIcons name={navIcon(RoutePaths.attendanceRequest, 'event-busy')} size={18} color={palette.primary} />
          <Text style={{ color: palette.primary, fontSize: 14, fontWeight: '600' }}>{attendanceLabel}</Text>
        </Pressable>
      }
      loading={boot.isLoading}
      error={boot.isError && !db ? '대시보드를 불러오지 못했습니다.' : null}
      onRefresh={refreshBootstrap}
      footer={<Fab icon="smart-toy" label="챗봇" onPress={() => go('/(student)/chat')} />}
    >
      <AlertHost />

      <Card onPress={() => go('/(student)/mypage')}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
          <Avatar name={user?.displayName} />
          <View style={{ flex: 1, gap: 2 }}>
            <T variant="caption" tone="primary" style={{ fontWeight: '600' }}>{user?.cohortName || '기수 없음'}</T>
            <T variant="title">{user?.displayName}님</T>
            <T variant="caption" tone="secondary">{greeting}</T>
          </View>
          <MaterialIcons name="chevron-right" size={22} color={palette.textHint} />
        </View>
      </Card>

      <View style={{ flexDirection: 'row', gap: 12 }}>
        <StatTile
          icon="savings"
          label="마일리지"
          value={`${(user?.mileageBalance ?? 0).toLocaleString('ko-KR')} P`}
          tone="warning"
          onPress={() => go('/(student)/(tabs)/mileage')}
        />
        <StatTile
          icon="event-available"
          label="오늘 출결"
          value={status ? AttendanceLabels[status] ?? status : '기록 없음'}
          tone={statusTone}
          onPress={() => go('/(student)/attendance')}
        />
      </View>

      <Card style={{ paddingVertical: 14 }}>
        <View style={{ flexDirection: 'row' }}>
          {[RoutePaths.records, RoutePaths.assessments, RoutePaths.forms, RoutePaths.seating].map((path) => {
            const item = studentMenu.find((row) => row.webPath === path);
            return item ? <QuickAction key={path} icon={item.icon} label={item.label} onPress={() => go(item.href)} /> : null;
          })}
        </View>
      </Card>

      {pendingForms.length > 0 ? (
        <>
          <SectionHeader title="해야 할 설문" onAction={() => go('/(student)/forms')} />
          <ListGroup>
            {pendingForms.slice(0, 3).map((task) => (
              <ListItem
                key={task.id}
                title={task.title}
                subtitle={`마감 ${fmt(task.dueAt)}`}
                left={<MaterialIcons name="assignment-late" size={20} color={palette.warning} />}
                onPress={() => go(`/(student)/forms/${task.id}`)}
              />
            ))}
          </ListGroup>
        </>
      ) : null}

      <SectionHeader title="시스템 공지" onAction={() => go('/(student)/(tabs)/board')} />
      {notices.length === 0 ? (
        <Card>
          <EmptyState icon="campaign" text="공지사항이 없습니다" />
        </Card>
      ) : (
        <ListGroup>
          {notices.map((notice) => (
            <ListItem
              key={notice.id}
              title={notice.title}
              subtitle={`${notice.authorName} · ${fmt(notice.createdAt)}`}
              left={notice.isFavorite ? <Badge label="중요" tone="error" /> : null}
              onPress={() => go(`/(student)/notice/${notice.id}`)}
            />
          ))}
        </ListGroup>
      )}
    </Screen>
  );
}

const AttendanceTones: Record<string, Tone | string> = {
  present: 'success',
  late: 'warning',
  absent: 'error',
  officialLeave: 'info',
  earlyLeave: 'primary',
  outing: '#0f766e',
};

export function BoardPage() {
  const { palette } = useTheme();
  const notices = [...useNotices()].sort((a, b) => Number(b.isFavorite) - Number(a.isFavorite));
  const posts = usePosts();
  const { user } = useSession();
  const [tab, setTab] = useState<'notice' | 'free'>('notice');
  const [content, setContent] = useState('');
  return (
    <Screen title="게시판" back={false} onRefresh={refreshBootstrap}>
      <Segmented
        options={[
          { key: 'notice', label: `공지 ${notices.length}` },
          { key: 'free', label: `자유게시판 ${posts.length}` },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === 'notice' ? (
        notices.length === 0 ? (
          <Card><EmptyState icon="campaign" text="공지사항이 없습니다" /></Card>
        ) : (
          <ListGroup>
            {notices.map((notice) => (
              <ListItem
                key={notice.id}
                title={notice.title}
                subtitle={`${notice.authorName} · ${fmt(notice.createdAt)}`}
                left={notice.isFavorite ? <Badge label="중요" tone="error" /> : null}
                onPress={() => go(`/(student)/notice/${notice.id}`)}
              />
            ))}
          </ListGroup>
        )
      ) : (
        <>
          <Card style={{ gap: 10 }}>
            <Field label="새 글" value={content} onChangeText={setContent} placeholder="동기들과 나누고 싶은 이야기를 적어 보세요" multiline />
            <Btn
              label="올리기"
              icon="send"
              disabled={!content.trim() || !user}
              onPress={() => {
                if (user) {
                  addPost(user.uid, user.displayName, content.trim());
                  setContent('');
                }
              }}
            />
          </Card>
          {posts.length === 0 ? <EmptyState icon="forum" text="첫 글을 남겨 보세요" /> : null}
          {posts.map((post) => (
            <Card key={post.id} onPress={() => go(`/(student)/post/${post.id}`)} style={{ gap: 10 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <Avatar name={post.authorName} size={32} />
                <View style={{ flex: 1 }}>
                  <T variant="subtitle" style={{ fontSize: 14 }}>{post.authorName}</T>
                  <T variant="caption" tone="hint">{fmt(post.createdAt)}</T>
                </View>
              </View>
              <T numberOfLines={4}>{post.content}</T>
              <View style={{ flexDirection: 'row', gap: 16 }}>
                <Pressable hitSlop={8} onPress={() => likePost(post.id)} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  <MaterialIcons name="favorite-border" size={18} color={palette.error} />
                  <T variant="caption" tone="secondary">{post.likeCount}</T>
                </Pressable>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  <MaterialIcons name="chat-bubble-outline" size={17} color={palette.textSecondary} />
                  <T variant="caption" tone="secondary">{post.commentCount}</T>
                </View>
              </View>
            </Card>
          ))}
        </>
      )}
    </Screen>
  );
}

export function NoticePage({ id }: { id: string }) {
  const notice = useNotices().find((row) => row.id === id);
  return (
    <Screen title="공지" empty={!notice} emptyText="공지를 찾지 못했습니다.">
      {notice ? (
        <Card style={{ gap: 12 }}>
          {notice.isFavorite ? <Badge label="중요" tone="error" /> : null}
          <T variant="title" style={{ fontSize: 20 }}>{notice.title}</T>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Avatar name={notice.authorName} size={28} />
            <T variant="caption" tone="secondary">{notice.authorName} · {fmt(notice.createdAt)}</T>
          </View>
          <Divider />
          <MarkdownBlock text={notice.content} />
        </Card>
      ) : null}
    </Screen>
  );
}

export function PostPage({ id }: { id: string }) {
  const { palette } = useTheme();
  const post = usePosts().find((row) => row.id === id);
  const comments = useComments(id);
  const { user } = useSession();
  const [text, setText] = useState('');
  const send = () => {
    if (!user || !text.trim()) return;
    addComment(id, user.uid, user.displayName, text.trim());
    setText('');
  };
  return (
    <Screen
      title="게시글"
      empty={!post}
      footer={post ? <Composer value={text} onChangeText={setText} onSend={send} placeholder="댓글을 입력하세요" /> : null}
    >
      {post ? (
        <Card style={{ gap: 12 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <Avatar name={post.authorName} size={36} />
            <View style={{ flex: 1 }}>
              <T variant="subtitle">{post.authorName}</T>
              <T variant="caption" tone="hint">{fmt(post.createdAt)}</T>
            </View>
          </View>
          <T>{post.content}</T>
          <Pressable hitSlop={8} onPress={() => likePost(post.id)} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <MaterialIcons name="favorite-border" size={20} color={palette.error} />
            <T variant="caption" tone="secondary">좋아요 {post.likeCount}</T>
          </Pressable>
        </Card>
      ) : null}
      <SectionHeader title={`댓글 ${comments.length}`} />
      {comments.length === 0 ? <EmptyState icon="chat-bubble-outline" text="아직 댓글이 없습니다" /> : null}
      {comments.map((comment) => (
        <View key={comment.id} style={{ flexDirection: 'row', gap: 10 }}>
          <Avatar name={comment.authorName} size={30} />
          <View style={{ flex: 1, gap: 2, padding: 12, borderRadius: 14, backgroundColor: palette.surface, borderWidth: 0.5, borderColor: palette.border }}>
            <T variant="caption" style={{ fontWeight: '700' }}>{comment.authorName}</T>
            <T>{comment.content}</T>
          </View>
        </View>
      ))}
    </Screen>
  );
}

function Divider() {
  const { palette } = useTheme();
  return <View style={{ height: 0.5, backgroundColor: palette.border }} />;
}

export function FormsPage() {
  const tasks = useFormTasks().filter((task) => task.published);
  return (
    <Screen title="설문 · 제출">
      {tasks.length === 0 ? <Muted>열린 설문이 없습니다.</Muted> : tasks.map((task) => (
        <Row key={task.id} title={task.title} subtitle={fmt(task.dueAt)} onPress={() => go(`/(student)/forms/${task.id}`)} />
      ))}
    </Screen>
  );
}

export function FormFillPage({ id }: { id: string }) {
  const task = useFormTasks().find((row) => row.id === id);
  const { user } = useSession();
  const responses = useFormResponses(id);
  const mine = responses.find((row) => row.userId === user?.uid);
  const [answers, setAnswers] = useState<Record<string, FormAnswer>>({});
  const [notice, setNotice] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  if (!task) return <Screen title="설문" empty emptyText="설문을 찾지 못했습니다." />;
  const closed = task.dueAt ? new Date(task.dueAt).getTime() < Date.now() : false;

  function missingTitle(): string | null {
    if (!task || task.mode !== 'builtin') return null;
    for (const question of task.questions) {
      if (!question.required) continue;
      const value = answers[question.id];
      const empty = value === undefined || (Array.isArray(value) ? value.length === 0 : String(value).trim() === '');
      if (empty) return question.title;
    }
    return null;
  }

  async function send() {
    if (!user || !task || busy) return;
    const missing = missingTitle();
    if (missing) {
      setNotice({ tone: 'error', text: `필수 문항을 입력해 주세요: ${missing}` });
      return;
    }
    setBusy(true);
    setNotice(null);
    try {
      if (task.mode === 'external') {
        if (task.formUrl) await Linking.openURL(task.formUrl);
        await markFormResponded(task.id, user.uid);
      } else {
        const payload: Record<string, FormAnswer> = {};
        for (const question of task.questions) {
          const value = answers[question.id];
          payload[question.id] = value ?? (question.type === 'multi' ? [] : '');
        }
        await submitFormResponse(task.id, payload);
      }
      setNotice({ tone: 'success', text: task.mode === 'external' ? '응답 완료로 표시했습니다.' : '제출했습니다.' });
    } catch (error) {
      setNotice({ tone: 'error', text: error instanceof Error ? error.message : '제출에 실패했습니다.' });
    } finally {
      setBusy(false);
    }
  }
  return (
    <Screen title={task.title}>
      {task.description ? <Muted>{task.description}</Muted> : null}
      {task.dueAt ? <T variant="caption" tone={closed ? 'error' : 'secondary'}>마감 {fmt(task.dueAt)}{closed ? ' · 마감됨' : ''}</T> : null}
      {mine ? <Callout tone="info"><T>이미 제출했습니다. 마감 전이면 다시 낼 수 있습니다.</T></Callout> : null}
      {task.mode === 'builtin' ? task.questions.map((question) => (
        <QuestionField key={question.id} question={question} value={answers[question.id]} onChange={(value) => setAnswers((prev) => ({ ...prev, [question.id]: value }))} />
      )) : <Muted>외부 설문입니다. 버튼을 누르면 브라우저로 이동하고 응답 완료로 표시됩니다.</Muted>}
      {notice ? <Callout tone={notice.tone}><T tone={notice.tone === 'error' ? 'error' : undefined}>{notice.text}</T></Callout> : null}
      <Btn
        label={busy ? '제출 중…' : task.mode === 'external' ? '설문 열기' : '제출'}
        disabled={busy || closed}
        onPress={() => void send()}
      />
    </Screen>
  );
}

function QuestionField({ question, value, onChange }: { question: FormQuestion; value: FormAnswer | undefined; onChange: (value: FormAnswer) => void }) {
  const title = `${question.title}${question.required ? ' *' : ''}`;
  if (question.type === 'single' || question.type === 'multi') {
    const picked = Array.isArray(value) ? value : typeof value === 'string' && value ? [value] : [];
    const toggle = (option: string) => {
      if (question.type === 'single') return onChange(option);
      onChange(picked.includes(option) ? picked.filter((row) => row !== option) : [...picked, option]);
    };
    return (
      <Card style={{ gap: 8 }}>
        <T variant="subtitle">{title}</T>
        {question.description ? <T variant="caption" tone="secondary">{question.description}</T> : null}
        {question.type === 'multi' ? <T variant="caption" tone="secondary">여러 개 고를 수 있습니다.</T> : null}
        {(question.options ?? []).map((option) => (
          <Btn key={option} label={option} tone={picked.includes(option) ? 'primary' : 'ghost'} onPress={() => toggle(option)} />
        ))}
      </Card>
    );
  }
  if (question.type === 'scale') {
    const max = Math.max(2, question.scaleMax ?? 5);
    return (
      <Card style={{ gap: 8 }}>
        <T variant="subtitle">{title}</T>
        {question.description ? <T variant="caption" tone="secondary">{question.description}</T> : null}
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
          {Array.from({ length: max }, (_, i) => i + 1).map((score) => (
            <Chip key={score} label={String(score)} selected={Number(value) === score} onPress={() => onChange(score)} />
          ))}
        </View>
        {question.minLabel || question.maxLabel ? (
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <T variant="caption" tone="secondary">{question.minLabel ? `1 = ${question.minLabel}` : ''}</T>
            <T variant="caption" tone="secondary">{question.maxLabel ? `${max} = ${question.maxLabel}` : ''}</T>
          </View>
        ) : null}
      </Card>
    );
  }
  return (
    <Field
      label={title}
      value={typeof value === 'string' ? value : value === undefined ? '' : String(value)}
      onChangeText={onChange}
      multiline={question.type === 'long'}
      placeholder={question.type === 'date' ? 'YYYY-MM-DD' : question.description}
    />
  );
}

export function SeatingPage() {
  const { user } = useSession();
  const db = useDb();
  const { palette } = useTheme();
  const { width } = useWindowDimensions();
  const roomId = user?.cohortId ? db?.seatingMeta?.[user.cohortId]?.publishedRoomId : undefined;
  const room = (db?.seatingRooms ?? []).find((row) => row.id === roomId);
  const assignment = (db?.seatingAssignments ?? []).find((row) => row.roomId === roomId);
  const published = room !== undefined && assignment?.status === 'published';
  const where = [user?.cohortName, room?.roomNumber?.trim()].filter((value): value is string => Boolean(value)).join(' · ');
  const mySeatId = assignment ? Object.keys(assignment.assignments).find((seatId) => assignment.assignments[seatId] === user?.uid) : undefined;
  const mySeat = room?.cells.find((cell) => cell.seatId === mySeatId);

  return (
    <Screen title="자리 배치" onRefresh={refreshBootstrap}>
      <T tone="secondary">{where === '' ? '확정된 강의실 자리를 확인하세요.' : `${where} · 내 자리는 파랗게 표시됩니다.`}</T>
      {room === undefined ? (
        <Card><EmptyState icon="event-seat" text="좌석 배치가 아직 준비되지 않았습니다." /></Card>
      ) : !published || assignment === undefined ? (
        <Card style={{ alignItems: 'center', paddingVertical: 36, gap: 8 }}>
          <MaterialIcons name="event-seat" size={48} color={palette.textHint} />
          <T variant="subtitle">좌석 배치 확정 대기 중</T>
          <T tone="secondary" style={{ textAlign: 'center' }}>관리자가 배치를 확정하면 이곳에서 확인할 수 있습니다.</T>
        </Card>
      ) : (
        <>
          {mySeat ? (
            <Callout tone="info">
              <T variant="subtitle">내 자리 {mySeat.label}번</T>
            </Callout>
          ) : null}
          <Card style={{ paddingHorizontal: 8, paddingVertical: 16 }}>
            <SeatGrid
              grid={room}
              seatUserIds={assignment.assignments}
              seatNames={assignment.seatNames}
              highlightUserId={user?.uid}
              width={width - 32 - 16 - 2}
            />
          </Card>
        </>
      )}
      <ListGroup>
        <ListItem title="프로젝트 팀" left={<MenuIcon name="groups" />} onPress={() => go('/(student)/teams')} />
      </ListGroup>
    </Screen>
  );
}

export function TeamsPage() {
  const { user } = useSession();
  const teams = useTeams().filter((team) => team.cohortId === user?.cohortId);
  const users = useDb()?.users ?? [];
  return (
    <Screen title="프로젝트 팀">
      {teams.length === 0 ? <Card><EmptyState icon="groups" text="아직 팀이 없습니다." /></Card> : teams.map((team) => {
        const mine = team.memberIds.includes(user?.uid ?? '');
        return (
          <Card key={team.id} style={{ gap: 10 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <T variant="subtitle" style={{ flex: 1 }}>{team.name}</T>
              {mine ? <Badge label="내 팀" tone="primary" /> : null}
              <T variant="caption" tone="secondary">{team.memberIds.length}명</T>
            </View>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {team.memberIds.map((id) => {
                const name = users.find((row) => row.uid === id)?.displayName ?? '이름 없음';
                return (
                  <View key={id} style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Avatar name={name} size={24} />
                    <T variant="caption" style={{ fontWeight: id === user?.uid ? '700' : '400' }}>{name}</T>
                  </View>
                );
              })}
            </View>
          </Card>
        );
      })}
    </Screen>
  );
}

const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/;

function emptyDraft(dateKey: string): AttendanceRequestDraft {
  return { dateKey, issueType: 'late', reason: '', officialLeaveUsed: false };
}

function draftOf(row: AttendanceIssue): AttendanceRequestDraft {
  return {
    id: row.id,
    dateKey: row.dateKey,
    issueType: (IssueTypes as string[]).includes(row.issueType) ? (row.issueType as AttendanceIssueType) : 'absent',
    timeFrom: row.timeFrom,
    timeTo: row.timeTo,
    reason: row.reason ?? '',
    officialLeaveUsed: row.officialLeaveUsed,
    officialLeaveType: (LeaveTypes as string[]).includes(row.officialLeaveType ?? '')
      ? (row.officialLeaveType as OfficialLeaveType)
      : row.officialLeaveUsed
        ? 'other'
        : undefined,
    officialLeaveOther: row.officialLeaveOther,
  };
}

function shiftKey(key: string, days: number): string {
  const [y, m, d] = key.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

/** 「0930」처럼 숫자만 넣어도 09:30 으로 맞춘다 */
function normalizeTime(raw: string): string {
  const digits = raw.replace(/\D/g, '').slice(0, 4);
  if (digits.length <= 2) return digits;
  return `${digits.slice(0, 2)}:${digits.slice(2)}`;
}

export function AttendancePage() {
  const { user } = useSession();
  const { palette } = useTheme();
  const today = todayKey();
  const requests = [...useIssues().filter((row) => row.userId === user?.uid)].sort(
    (a, b) => b.dateKey.localeCompare(a.dateKey) || (b.submittedAt?.getTime() ?? 0) - (a.submittedAt?.getTime() ?? 0),
  );
  const [draft, setDraft] = useState<AttendanceRequestDraft>(() => emptyDraft(today));
  const [file, setFile] = useState<PickedFile | null>(null);
  const [editing, setEditing] = useState<AttendanceIssue | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const fields = timeFieldsFor(draft.issueType);
  const todayCount = requests.filter((row) => row.dateKey === today).length;
  const pending = requests.filter((row) => row.status === 'submitted').length;
  const rejected = requests.filter((row) => row.status === 'rejected');
  const { min: minDate, max: maxDate } = requestDateRange(today);
  const duplicate = requests.find((row) => row.id !== draft.id && row.dateKey === draft.dateKey && row.issueType === draft.issueType);

  const patch = (change: Partial<AttendanceRequestDraft>) => {
    setDraft((prev) => ({ ...prev, ...change }));
    setError(null);
  };
  const reset = (dateKey = today) => {
    setDraft(emptyDraft(dateKey));
    setFile(null);
    setEditing(undefined);
    setError(null);
  };
  const startEdit = (row: AttendanceIssue) => {
    setEditing(row);
    setDraft(draftOf(row));
    setFile(null);
    setDone(null);
    setError(null);
  };
  const moveDate = (days: number) => {
    const next = shiftKey(draft.dateKey, days);
    if (next >= minDate && next <= maxDate) patch({ dateKey: next });
  };

  const pickFile = async () => {
    const picked = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true, type: ['image/*', 'application/pdf'] });
    if (picked.canceled || !picked.assets[0]) return;
    const asset = picked.assets[0];
    setFile({ uri: asset.uri, name: asset.name, type: asset.mimeType ?? 'application/octet-stream', size: asset.size });
    setError(null);
  };

  const submit = () => {
    if (!user) return;
    const clean: AttendanceRequestDraft = {
      ...draft,
      reason: draft.reason.trim(),
      timeFrom: fields.from !== undefined ? draft.timeFrom : undefined,
      timeTo: fields.to !== undefined ? draft.timeTo : undefined,
      officialLeaveType: draft.officialLeaveUsed ? draft.officialLeaveType : undefined,
      officialLeaveOther: draft.officialLeaveUsed && draft.officialLeaveType === 'other' ? draft.officialLeaveOther : undefined,
    };
    const badTime =
      (clean.timeFrom && !TIME_PATTERN.test(clean.timeFrom)) || (clean.timeTo && !TIME_PATTERN.test(clean.timeTo))
        ? '시각은 09:30 처럼 적어 주세요.'
        : null;
    const problem =
      draftError(clean) ??
      badTime ??
      (file?.size !== undefined && file.size > EVIDENCE_MAX_BYTES ? '증빙 파일은 10MB 이하만 올릴 수 있습니다.' : null) ??
      (clean.dateKey < minDate || clean.dateKey > maxDate
        ? `발생일은 ${minDate}부터 ${maxDate}까지 고를 수 있습니다.`
        : duplicate !== undefined
          ? `${duplicate.dateKey} ${IssueTypeLabels[draft.issueType]} 신청이 이미 있습니다. 아래 내역에서 그 신청을 고쳐 주세요.`
          : null);
    if (problem !== null) {
      setError(problem);
      return;
    }
    setSaving(true);
    setError(null);
    void (async () => {
      try {
        const evidence = file ? await uploadEvidence(file) : undefined;
        await submitAttendanceRequest({
          ...clean,
          evidence: evidence && { key: evidence.key, name: evidence.name, contentType: evidence.contentType, size: evidence.size },
        });
        setDone(editing ? '신청을 고쳤습니다. 매니저 확인을 기다려 주세요.' : '신청했습니다. 매니저 확인을 기다려 주세요.');
        reset(clean.dateKey);
      } catch (err) {
        setError(err instanceof Error ? err.message : '신청하지 못했습니다.');
      } finally {
        setSaving(false);
      }
    })();
  };

  const cancel = (row: AttendanceIssue) => {
    Alert.alert('신청 취소', `${row.dateKey} ${labelOf(row)} 신청을 취소할까요?`, [
      { text: '닫기', style: 'cancel' },
      {
        text: '취소하기',
        style: 'destructive',
        onPress: () =>
          void cancelAttendanceRequest(row.id)
            .then(() => {
              if (editing?.id === row.id) reset();
              setDone('신청을 취소했습니다.');
            })
            .catch((err: unknown) => setError(err instanceof Error ? err.message : '취소하지 못했습니다.')),
      },
    ]);
  };

  return (
    <Screen title="출결 신청">
      <T tone="secondary">정상 출석 외에 지각 · 조퇴 · 외출 · 결석(공가 포함)이 있으면 그날 신청해 주세요. 매니저가 확인하면 출석부에 반영됩니다.</T>

      <View style={{ flexDirection: 'row', gap: 8 }}>
        <CountChip label={`오늘 신청 ${todayCount}건`} none={todayCount === 0} />
        <CountChip label={`확인 대기 ${pending}건`} />
      </View>

      {done !== null ? <Callout tone="success"><T>{done}</T></Callout> : null}

      {rejected.length > 0 && editing === undefined ? (
        <Callout tone="warning">
          <T>반려된 신청이 {rejected.length}건 있습니다. 매니저 메모를 보고 고쳐서 다시 내 주세요.</T>
          <Pressable onPress={() => startEdit(rejected[0])} hitSlop={6} style={{ marginTop: 6 }}>
            <T variant="caption" tone="primary" style={{ fontWeight: '700' }}>
              {rejected[0].dateKey} {labelOf(rejected[0])} 고치기 ›
            </T>
          </Pressable>
        </Callout>
      ) : null}

      <Card style={{ gap: 16 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          <T variant="title" style={{ flex: 1 }}>{editing ? '신청 고치기' : '새 신청'}</T>
          {editing ? (
            <Pressable onPress={() => reset()} hitSlop={8}>
              <T variant="caption" tone="secondary">고치기 그만</T>
            </Pressable>
          ) : null}
        </View>
        {editing?.status === 'rejected' ? (
          <Callout tone="warning">
            <T>반려된 신청입니다{editing.reviewComment ? ` — ${editing.reviewComment}` : ''}. 고쳐서 내면 다시 확인 대기로 갑니다.</T>
          </Callout>
        ) : null}

        <FormBlock label="발생일" hint={`${REQUEST_PAST_DAYS}일 전부터 ${REQUEST_FUTURE_DAYS}일 뒤까지`}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <StepButton icon="chevron-left" label="하루 전" disabled={draft.dateKey <= minDate} onPress={() => moveDate(-1)} />
            <View style={{ flex: 1, minHeight: 44, borderRadius: 12, borderWidth: 1, borderColor: palette.border, alignItems: 'center', justifyContent: 'center' }}>
              <T variant="subtitle">{formatLessonDate(draft.dateKey)}</T>
            </View>
            <StepButton icon="chevron-right" label="하루 뒤" disabled={draft.dateKey >= maxDate} onPress={() => moveDate(1)} />
          </View>
          {draft.dateKey !== today ? (
            <Pressable onPress={() => patch({ dateKey: today })} hitSlop={6} style={{ alignSelf: 'flex-start' }}>
              <T variant="caption" tone="primary" style={{ fontWeight: '600' }}>오늘로</T>
            </Pressable>
          ) : null}
        </FormBlock>

        <FormBlock label="출결 유형">
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {IssueTypes.map((type) => (
              <Chip key={type} label={IssueTypeLabels[type]} selected={draft.issueType === type} onPress={() => patch({ issueType: type })} />
            ))}
          </View>
        </FormBlock>

        {fields.from !== undefined || fields.to !== undefined ? (
          <View style={{ flexDirection: 'row', gap: 12 }}>
            {fields.from !== undefined ? (
              <View style={{ flex: 1 }}>
                <Field label={fields.from} value={draft.timeFrom ?? ''} onChangeText={(value) => patch({ timeFrom: normalizeTime(value) })} placeholder="09:30" keyboard="numeric" />
              </View>
            ) : null}
            {fields.to !== undefined ? (
              <View style={{ flex: 1 }}>
                <Field label={fields.to} value={draft.timeTo ?? ''} onChangeText={(value) => patch({ timeTo: normalizeTime(value) })} placeholder="11:00" keyboard="numeric" />
              </View>
            ) : null}
          </View>
        ) : null}

        <FormBlock label="공가 활용 여부">
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <Chip label="미사용" selected={!draft.officialLeaveUsed} onPress={() => patch({ officialLeaveUsed: false })} />
            <Chip label="사용" selected={draft.officialLeaveUsed} onPress={() => patch({ officialLeaveUsed: true })} />
          </View>
        </FormBlock>

        {draft.officialLeaveUsed ? (
          <FormBlock label="공가 유형">
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {LeaveTypes.map((type) => (
                <Chip key={type} label={LeaveTypeLabels[type]} selected={draft.officialLeaveType === type} onPress={() => patch({ officialLeaveType: type })} />
              ))}
            </View>
          </FormBlock>
        ) : null}
        {draft.officialLeaveUsed && draft.officialLeaveType === 'other' ? (
          <Field label="기타 공가 내용" value={draft.officialLeaveOther ?? ''} onChangeText={(value) => patch({ officialLeaveOther: value.slice(0, 100) })} placeholder="예: 가족 행사" />
        ) : null}

        <View style={{ gap: 4 }}>
          <Field label="사유" value={draft.reason} onChangeText={(value) => patch({ reason: value.slice(0, 1000) })} placeholder="예: 병원 진료로 오후 3시에 조퇴합니다." multiline />
          <T variant="caption" tone="hint" style={{ alignSelf: 'flex-end' }}>{draft.reason.length} / 1000</T>
        </View>

        <FormBlock
          label="증빙 파일 (선택)"
          hint={
            editing?.evidenceName && !draft.removeEvidence && file === null
              ? `지금 붙어 있는 파일: ${editing.evidenceName} — 새로 고르면 바뀝니다.`
              : '진단서 · 면접 확인서 등 이미지나 PDF, 10MB 까지'
          }
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Btn label={file ? '다른 파일 고르기' : '파일 고르기'} icon="attach-file" tone="ghost" onPress={() => void pickFile()} />
            {file ? <T variant="caption" style={{ flex: 1 }} numberOfLines={1}>{file.name}</T> : null}
            {file ? (
              <Pressable onPress={() => setFile(null)} hitSlop={8} accessibilityLabel="파일 빼기">
                <MaterialIcons name="close" size={18} color={palette.textSecondary} />
              </Pressable>
            ) : null}
          </View>
          {editing?.evidenceName && file === null ? (
            <Chip
              label={draft.removeEvidence ? '✓ 붙어 있던 증빙 떼기' : '붙어 있던 증빙 떼기'}
              selected={draft.removeEvidence === true}
              onPress={() => patch({ removeEvidence: !draft.removeEvidence })}
            />
          ) : null}
        </FormBlock>

        {duplicate !== undefined && error === null ? (
          <Callout tone="warning">
            <T>
              {duplicate.dateKey} {IssueTypeLabels[draft.issueType]} 신청이 이미 있습니다 ({RequestStatusLabels[duplicate.status]}).{' '}
              {duplicate.status === 'approved' ? '승인된 신청은 고칠 수 없으니 바꿔야 하면 매니저에게 알려 주세요.' : ''}
            </T>
            {duplicate.status !== 'approved' ? (
              <Pressable onPress={() => startEdit(duplicate)} hitSlop={6} style={{ marginTop: 6 }}>
                <T variant="caption" tone="primary" style={{ fontWeight: '700' }}>그 신청 고치기 ›</T>
              </Pressable>
            ) : null}
          </Callout>
        ) : null}

        {error !== null ? <T tone="error">{error}</T> : null}

        <Btn label={saving ? '보내는 중…' : editing ? '고쳐서 내기' : '신청하기'} icon="send" disabled={saving} onPress={submit} />
      </Card>

      <SectionHeader title="내 신청 내역" />
      {requests.length === 0 ? (
        <Card><EmptyState icon="event-note" text="아직 낸 신청이 없습니다." /></Card>
      ) : (
        requests.map((row) => (
          <Card key={row.id} style={{ gap: 8 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <T variant="subtitle">{row.dateKey}</T>
              <T>{labelOf(row)}</T>
              <Badge label={RequestStatusLabels[row.status] ?? '확인 대기'} tone={RequestStatusTones[row.status] ?? 'warning'} />
            </View>
            {row.status === 'approved' ? <T variant="caption" tone="secondary">출석부에 반영됐습니다. 바꿔야 하면 매니저에게 알려 주세요.</T> : null}
            {row.reason ? <T>{row.reason}</T> : null}
            <View style={{ gap: 2 }}>
              {row.submittedAt ? <T variant="caption" tone="hint">제출 {fmt(row.submittedAt)}</T> : null}
              {row.evidenceUrl ? (
                <Pressable onPress={() => void Linking.openURL(row.evidenceUrl!)} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  <MaterialIcons name="attach-file" size={14} color={palette.primary} />
                  <T variant="caption" tone="primary">{row.evidenceName ?? '증빙'}</T>
                </Pressable>
              ) : null}
              {row.reviewComment ? <T variant="caption" tone="secondary">매니저 메모: {row.reviewComment}</T> : null}
            </View>
            {row.status !== 'approved' ? (
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <View style={{ flex: 1 }}><Btn label="고치기" tone="ghost" onPress={() => startEdit(row)} /></View>
                <View style={{ flex: 1 }}><Btn label="취소" tone="ghost" onPress={() => cancel(row)} /></View>
              </View>
            ) : null}
          </Card>
        ))
      )}
    </Screen>
  );
}

function FormBlock({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <View style={{ gap: 8 }}>
      <T variant="label" tone="secondary">{label}</T>
      {children}
      {hint ? <T variant="caption" tone="hint">{hint}</T> : null}
    </View>
  );
}

function CountChip({ label, none }: { label: string; none?: boolean }) {
  const { palette } = useTheme();
  return (
    <View style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.surface }}>
      <Text style={{ fontSize: 13, fontWeight: '600', color: none ? palette.textHint : palette.text }}>{label}</Text>
    </View>
  );
}

function StepButton({ icon, label, disabled, onPress }: { icon: IconName; label: string; disabled?: boolean; onPress: () => void }) {
  const { palette } = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      disabled={disabled}
      onPress={onPress}
      style={{ width: 44, height: 44, borderRadius: 12, borderWidth: 1, borderColor: palette.border, alignItems: 'center', justifyContent: 'center', opacity: disabled ? 0.35 : 1 }}
    >
      <MaterialIcons name={icon} size={22} color={palette.text} />
    </Pressable>
  );
}

export function StudyPage() {
  const notes = useNotes();
  const sets = useDb()?.practiceSets ?? [];
  const { palette } = useTheme();
  const days = lessonDays(sets, notes).slice(0, 14);
  return (
    <Screen title="학습실" back={false} onRefresh={refreshBootstrap}>
      <View style={{ flexDirection: 'row', gap: 12 }}>
        <StatTile icon="menu-book" label="공부 노트" value={`${notes.length}개`} tone="primary" onPress={() => go('/(student)/notes')} />
        <StatTile icon="replay" label="오답 · 복습" value="다시 풀기" tone="error" onPress={() => go('/(student)/wrong')} />
      </View>
      <Card onPress={() => go('/(student)/desktop/playground')}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <View style={{ width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.surfaceVariant }}>
            <MaterialIcons name="terminal" size={22} color={palette.textSecondary} />
          </View>
          <View style={{ flex: 1 }}>
            <T variant="subtitle">코드 연습장</T>
            <T variant="caption" tone="secondary">편집기가 필요해 PC 웹에서 열립니다</T>
          </View>
          <MaterialIcons name="open-in-new" size={20} color={palette.textHint} />
        </View>
      </Card>

      <SectionHeader title="최근 수업" />
      {days.length === 0 ? (
        <Card><EmptyState icon="event-note" text="아직 수업 기록이 없습니다" /></Card>
      ) : (
        <ListGroup>
          {days.map((day) => (
            <ListItem
              key={day.date}
              title={formatLessonDate(day.date)}
              subtitle={day.set ? `복습 문제 · ${day.set.sourceTitle}` : undefined}
              left={<MaterialIcons name={day.note ? 'description' : 'event'} size={20} color={day.note ? palette.primary : palette.textHint} />}
              right={day.note ? <Badge label="노트" tone="primary" /> : <Badge label="노트 없음" tone="neutral" />}
              onPress={day.note ? () => go(`/(student)/notes/${day.note!.id}`) : undefined}
            />
          ))}
        </ListGroup>
      )}
    </Screen>
  );
}

const NoteStatusLabels: Record<string, string> = {
  ready: '정리 완료',
  done: '정리 완료',
  generating: '정리 중',
  too_broad: '범위가 너무 넓음',
  failed: '정리 실패',
};

function formatLessonDate(key: string): string {
  const date = new Date(`${key}T00:00:00`);
  if (Number.isNaN(date.getTime())) return key;
  return date.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short' });
}

export function NotesPage() {
  const notes = useNotes();
  const sources = useSources();
  return (
    <Screen title="공부 노트">
      {notes.length === 0 ? <Muted>노트가 없습니다.</Muted> : notes.map((note) => (
        <Row key={note.id} title={sources.find((source) => source.id === note.sourceId)?.title ?? note.scopeKey ?? '노트'} subtitle={NoteStatusLabels[note.status] ?? '정리 완료'} onPress={() => go(`/(student)/notes/${note.id}`)} />
      ))}
    </Screen>
  );
}

export function NotePage({ id }: { id: string }) {
  const note = useNotes().find((row) => row.id === id);
  return (
    <Screen title="노트" empty={!note}>
      {note ? <MarkdownBlock text={note.reportMarkdown || note.reviewMarkdown || '내용이 없습니다.'} /> : null}
    </Screen>
  );
}

export function MileagePage() {
  const { user } = useSession();
  const { palette } = useTheme();
  const tx = useTransactions(user?.uid);
  const earned = tx.filter((row) => row.amount > 0).reduce((sum, row) => sum + row.amount, 0);
  const spent = tx.filter((row) => row.amount < 0).reduce((sum, row) => sum - row.amount, 0);
  return (
    <Screen title="마일리지" back={false} onRefresh={refreshBootstrap}>
      <View style={{ borderRadius: 18, padding: 20, gap: 14, backgroundColor: palette.primary }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <MaterialIcons name="savings" size={20} color="rgba(255,255,255,0.9)" />
          <Text style={{ color: 'rgba(255,255,255,0.9)', fontWeight: '600' }}>보유 마일리지</Text>
        </View>
        <Text style={{ color: '#fff', fontSize: 34, fontWeight: '800', letterSpacing: -0.6 }}>
          {(user?.mileageBalance ?? 0).toLocaleString('ko-KR')} <Text style={{ fontSize: 20 }}>P</Text>
        </Text>
        <View style={{ flexDirection: 'row', gap: 16 }}>
          <Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: 13 }}>적립 +{earned.toLocaleString('ko-KR')}</Text>
          <Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: 13 }}>사용 -{spent.toLocaleString('ko-KR')}</Text>
        </View>
      </View>

      <Card style={{ paddingVertical: 14 }}>
        <View style={{ flexDirection: 'row' }}>
          <QuickAction icon="storefront" label="상점" onPress={() => go('/(student)/shop')} />
          <QuickAction icon="shopping-cart" label="장바구니" onPress={() => go('/(student)/cart')} />
          <QuickAction icon="emoji-events" label="퀘스트" onPress={() => go('/(student)/quests')} />
        </View>
      </Card>

      <SectionHeader title="적립 · 사용 내역" />
      {tx.length === 0 ? (
        <Card><EmptyState icon="receipt-long" text="아직 내역이 없습니다" /></Card>
      ) : (
        <ListGroup>
          {tx.map((row) => {
            const plus = row.amount > 0;
            return (
              <ListItem
                key={row.id}
                title={row.reason}
                subtitle={fmt(row.createdAt)}
                left={
                  <MaterialIcons name={plus ? 'add-circle-outline' : 'remove-circle-outline'} size={22} color={plus ? palette.success : palette.error} />
                }
                right={
                  <T variant="subtitle" tone={plus ? 'success' : 'error'}>
                    {plus ? '+' : ''}
                    {row.amount.toLocaleString('ko-KR')}
                  </T>
                }
              />
            );
          })}
        </ListGroup>
      )}
    </Screen>
  );
}

export function QuestsPage() {
  const { user } = useSession();
  const { palette } = useTheme();
  const query = useQuests(user?.cohortId ?? '');
  const [activeId, setActiveId] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [link, setLink] = useState('');
  const [files, setFiles] = useState<PickedFile[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const mine = query.data?.submissions ?? [];
  const quests = (query.data?.quests ?? []).filter((q) => q.open || mine.some((s) => s.questId === q.id));
  const earned = mine.reduce((sum, s) => sum + s.grantedAmount, 0);

  const open = (quest: Quest) => {
    setActiveId(activeId === quest.id ? null : quest.id);
    setText('');
    setLink('');
    setFiles([]);
    setError(null);
  };

  const send = (quest: Quest) => {
    const problem =
      quest.evidenceType === 'text' && text.trim() === ''
        ? '인증 내용을 적어 주세요.'
        : quest.evidenceType === 'link' && !/^https?:\/\//.test(link.trim())
          ? 'http:// 나 https:// 로 시작하는 링크를 붙여 주세요.'
          : quest.evidenceType === 'file' && files.length === 0
            ? '인증 사진이나 파일을 올려 주세요.'
            : null;
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    void (async () => {
      try {
        const uploaded = quest.evidenceType === 'file' ? await Promise.all(files.map((file) => uploadEvidence(file))) : [];
        const submission = await submitQuest(quest.id, {
          text: text.trim(),
          link: link.trim(),
          fileKeys: uploaded.map((file) => file.key),
        });
        setActiveId(null);
        setFlash(
          submission.grantedAmount > 0
            ? `"${quest.title}" 완료! ${submission.grantedAmount.toLocaleString('ko-KR')}M 이 적립되었습니다.`
            : `"${quest.title}" 인증을 제출했습니다. 승인되면 마일리지가 적립됩니다.`,
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : '제출하지 못했습니다.');
      } finally {
        setBusy(false);
      }
    })();
  };

  return (
    <Screen title="추가 마일리지 미션" loading={query.isLoading} error={query.error instanceof Error ? query.error.message : null} onRefresh={() => query.refetch()}>
      <Card style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        <MaterialIcons name="flag" size={24} color={palette.primary} />
        <View style={{ flex: 1 }}>
          <T variant="caption" tone="secondary">미션으로 받은 마일리지</T>
          <T variant="title">{earned.toLocaleString('ko-KR')}M</T>
        </View>
      </Card>
      {flash ? <Callout tone="success"><T>{flash}</T></Callout> : null}

      {quests.length === 0 ? (
        <Card><EmptyState icon="flag" text="지금 참여할 수 있는 미션이 없습니다." /></Card>
      ) : (
        quests.map((quest) => {
          const subs = mine.filter((s) => s.questId === quest.id);
          const approved = subs.filter((s) => s.status === 'approved').length;
          const pending = subs.some((s) => s.status === 'pending');
          const full = approved >= quest.maxCompletions;
          const last = subs[0];
          const active = activeId === quest.id;
          return (
            <Card key={quest.id} style={{ gap: 8 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <T variant="subtitle" style={{ flex: 1 }}>{quest.title}</T>
                <T variant="subtitle" tone="primary">+{quest.reward.toLocaleString('ko-KR')}M</T>
              </View>
              {quest.description ? <T tone="secondary">{quest.description}</T> : null}
              <T variant="caption" tone="hint">
                {periodLabel(quest)} · 인증 {EVIDENCE_LABEL[quest.evidenceType]} · 완료 {approved}/{quest.maxCompletions}회
                {quest.approval === 'auto' ? ' · 제출 즉시 지급' : ' · 승인 후 지급'}
              </T>
              {last ? (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <Badge label={STATUS_LABEL[last.status]} tone={STATUS_TONE[last.status]} />
                  {last.status === 'rejected' && last.reviewComment ? <T variant="caption" tone="secondary">사유: {last.reviewComment}</T> : null}
                </View>
              ) : null}

              {full ? (
                <Badge label="모두 완료" tone="success" />
              ) : pending ? (
                <Btn label="검토 중" tone="ghost" disabled onPress={() => undefined} />
              ) : !quest.open ? (
                <Badge label="마감" tone="neutral" />
              ) : active ? (
                <View style={{ gap: 12, marginTop: 4 }}>
                  {quest.evidenceType === 'text' ? (
                    <Field label="인증 내용" value={text} onChangeText={(v) => setText(v.slice(0, 3000))} multiline />
                  ) : null}
                  {quest.evidenceType === 'link' ? (
                    <Field label="인증 링크" value={link} onChangeText={(v) => setLink(v.slice(0, 500))} placeholder="https://" keyboard="url" />
                  ) : null}
                  {quest.evidenceType === 'file' ? (
                    <EvidencePicker label="인증 사진 · 파일" hint="날짜가 보이는 사진이면 좋아요" multiple files={files} onChange={setFiles} onError={setError} />
                  ) : null}
                  {quest.evidenceType === 'none' ? <T tone="secondary">완료하기를 누르면 바로 처리됩니다.</T> : null}
                  {error ? <Callout tone="error"><T>{error}</T></Callout> : null}
                  <View style={{ flexDirection: 'row', gap: 8 }}>
                    <View style={{ flex: 1 }}><Btn label="취소" tone="ghost" disabled={busy} onPress={() => open(quest)} /></View>
                    <View style={{ flex: 1 }}>
                      <Btn label={busy ? '처리 중…' : quest.evidenceType === 'none' ? '완료하기' : '제출'} disabled={busy} onPress={() => send(quest)} />
                    </View>
                  </View>
                </View>
              ) : (
                <Btn label={quest.evidenceType === 'none' ? '완료하기' : '인증 제출'} onPress={() => open(quest)} />
              )}
            </Card>
          );
        })
      )}
    </Screen>
  );
}

export function MorePage() {
  const { user } = useSession();
  const { palette } = useTheme();
  const sections = appNav('student');
  return (
    <Screen title="메뉴" back={false}>
      <Card onPress={() => go('/(student)/mypage')}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
          <Avatar name={user?.displayName} />
          <View style={{ flex: 1, gap: 2 }}>
            <T variant="caption" tone="primary" style={{ fontWeight: '600' }}>{user?.cohortName || '기수 없음'}</T>
            <T variant="title">{user?.displayName}</T>
            <T variant="caption" tone="secondary">{user?.email}</T>
          </View>
          <MaterialIcons name="chevron-right" size={22} color={palette.textHint} />
        </View>
      </Card>
      {sections.map((section) => (
        <View key={section.id} style={{ gap: 8 }}>
          {section.title ? <T variant="label" tone="secondary" style={{ marginLeft: 4, marginTop: 4 }}>{section.title}</T> : null}
          <ListGroup>
            {section.items.map((item) => (
              <ListItem key={item.href + item.label} title={item.label} left={<MenuIcon name={item.icon} />} onPress={() => go(item.href)} />
            ))}
          </ListGroup>
        </View>
      ))}
    </Screen>
  );
}

function MenuIcon({ name }: { name: IconName }) {
  const { palette } = useTheme();
  return (
    <View style={{ width: 32, height: 32, borderRadius: 9, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.primaryLight }}>
      <MaterialIcons name={name} size={18} color={palette.primary} />
    </View>
  );
}

type ChatLine = { role: 'me' | 'bot'; text: string };

function ChatBubble({ line, botName }: { line: ChatLine; botName: string }) {
  const { palette } = useTheme();
  const mine = line.role === 'me';
  return (
    <View style={{ flexDirection: 'row', justifyContent: mine ? 'flex-end' : 'flex-start', gap: 8 }}>
      {mine ? null : (
        <View style={{ width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.primaryLight }}>
          <MaterialIcons name="smart-toy" size={18} color={palette.primary} />
        </View>
      )}
      <View style={{ maxWidth: '80%', gap: 4 }}>
        {mine ? null : <T variant="caption" tone="secondary">{botName}</T>}
        <View
          style={{
            paddingHorizontal: 14,
            paddingVertical: 10,
            borderRadius: 18,
            borderTopRightRadius: mine ? 4 : 18,
            borderTopLeftRadius: mine ? 18 : 4,
            backgroundColor: mine ? palette.primary : palette.surface,
            borderWidth: mine ? 0 : 0.5,
            borderColor: palette.border,
          }}
        >
          {mine ? <Text style={{ color: '#fff', fontSize: 15 }}>{line.text}</Text> : <MarkdownBlock text={line.text} />}
        </View>
      </View>
    </View>
  );
}

function ChatScreen({
  title,
  botName,
  intro,
  suggestions,
  ask,
}: {
  title: string;
  botName: string;
  intro: string;
  suggestions: string[];
  /** onToken 을 부르면 지금까지 받은 답변 전체로 말풍선을 갈아 끼운다 */
  ask: (message: string, onToken: (text: string) => void) => Promise<string>;
}) {
  const { palette } = useTheme();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [log, setLog] = useState<ChatLine[]>(() => chatHistory.get(title) ?? [{ role: 'bot', text: intro }]);
  const update = (next: (prev: ChatLine[]) => ChatLine[]) =>
    setLog((prev) => {
      const value = next(prev);
      chatHistory.set(title, value);
      return value;
    });
  const send = (raw: string) => {
    const message = raw.trim();
    if (!message || busy) return;
    setText('');
    setBusy(true);
    setStreaming(false);
    update((prev) => [...prev, { role: 'me', text: message }]);
    const replace = (answer: string) =>
      update((prev) => (prev[prev.length - 1]?.role === 'bot' ? [...prev.slice(0, -1), { role: 'bot', text: answer }] : [...prev, { role: 'bot', text: answer }]));
    let received = '';
    void ask(message, (partial) => {
      received = partial;
      setStreaming(true);
      replace(partial);
    })
      .then((answer) => replace(answer))
      .catch((error: unknown) => {
        const reason = error instanceof Error ? error.message : '답변을 받지 못했습니다.';
        replace(received ? `${received}\n\n${reason}` : reason);
      })
      .finally(() => {
        setBusy(false);
        setStreaming(false);
      });
  };
  const reset = () => {
    chatHistory.delete(title);
    setLog([{ role: 'bot', text: intro }]);
  };
  return (
    <Screen
      title={title}
      stickToBottom
      right={
        log.length > 1 && !busy ? (
          <Pressable accessibilityRole="button" accessibilityLabel="새 대화" hitSlop={8} onPress={reset}>
            <MaterialIcons name="refresh" size={22} color={palette.textSecondary} />
          </Pressable>
        ) : null
      }
      footer={<Composer value={text} onChangeText={setText} onSend={() => send(text)} busy={busy} />}
    >
      {log.map((line, index) => (
        <ChatBubble key={`${line.role}-${index}`} line={line} botName={botName} />
      ))}
      {busy && !streaming ? <T variant="caption" tone="hint" style={{ marginLeft: 38 }}>답변을 쓰는 중…</T> : null}
      {log.length === 1 ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginLeft: 38 }}>
          {suggestions.map((item) => (
            <Pressable key={item} onPress={() => send(item)} style={({ pressed }) => ({ opacity: pressed ? 0.6 : 1 })}>
              <Badge label={item} tone="primary" />
            </Pressable>
          ))}
        </View>
      ) : null}
    </Screen>
  );
}

export function ChatPage() {
  return (
    <ChatScreen
      title="학습 도우미"
      botName="학습 도우미"
      intro="안녕하세요! 수업 내용이나 LMS 사용법에 대해 무엇이든 물어보세요."
      suggestions={['오늘 수업 요약해줘', '출결 신청은 어떻게 해?', '마일리지는 어디에 써?']}
      ask={streamChatbot}
    />
  );
}

export function CoachPage() {
  const resumes = useDb()?.resumes ?? [];
  const { user } = useSession();
  const base = resumes.find((resume) => resume.userId === user?.uid && resume.isBaseResume);
  return (
    <ChatScreen
      title="코치에게 묻기"
      botName="취업 코치"
      intro={base ? '대표 이력서를 바탕으로 답해 드릴게요. 무엇이 궁금하세요?' : '대표 이력서를 등록하면 더 정확하게 추천해 드려요. 무엇이 궁금하세요?'}
      suggestions={['나한테 맞는 공고 추천해줘', '이력서 보완할 점 알려줘']}
      ask={async (message) => {
        const reply = await askCoach(message, base?.id ?? null);
        const jobs = reply.jobs.map((job) => `- **${job.company}** ${job.title}`).join('\n');
        return jobs ? `${reply.reply}\n\n${jobs}` : reply.reply;
      }}
    />
  );
}

export function SettingsPage() {
  const { palette, mode, setMode } = useTheme();
  const { signOut } = useSession();
  return (
    <Screen title="설정">
      <T variant="label" tone="secondary" style={{ marginLeft: 4 }}>화면 테마</T>
      <Segmented
        options={[
          { key: 'system', label: '시스템' },
          { key: 'light', label: '밝게' },
          { key: 'dark', label: '어둡게' },
        ]}
        value={mode}
        onChange={setMode}
      />
      <T variant="label" tone="secondary" style={{ marginLeft: 4, marginTop: 8 }}>계정</T>
      <ListGroup>
        <ListItem title="비밀번호 변경" left={<MenuIcon name="lock-outline" />} onPress={() => go('/change-password')} />
        <ListItem
          title="로그아웃"
          left={
            <View style={{ width: 32, height: 32, borderRadius: 9, alignItems: 'center', justifyContent: 'center', backgroundColor: `${palette.error}1f` }}>
              <MaterialIcons name="logout" size={18} color={palette.error} />
            </View>
          }
          onPress={() => void signOut()}
        />
      </ListGroup>
    </Screen>
  );
}

export function MyPage() {
  const { user } = useSession();
  const [motto, setMotto] = useState(user?.motto ?? '');
  const [roles, setRoles] = useState(user?.jobPreferences.targetRoles.join(', ') ?? '');
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  return (
    <Screen title="마이페이지">
      <Card style={{ alignItems: 'center', gap: 8, paddingVertical: 24 }}>
        <Avatar name={user?.displayName} size={72} />
        <T variant="title">{user?.displayName}</T>
        <T variant="caption" tone="secondary">{user?.email}</T>
        {user?.cohortName ? <Badge label={user.cohortName} tone="primary" /> : null}
      </Card>
      <Card style={{ gap: 14 }}>
        <Field label="좌우명" value={motto} onChangeText={setMotto} placeholder="나를 표현하는 한 줄" />
        <Field label="희망 직무 (쉼표로 구분)" value={roles} onChangeText={setRoles} placeholder="백엔드, 데이터 엔지니어" />
        {message ? <T variant="caption" tone={message.ok ? 'success' : 'error'}>{message.text}</T> : null}
        <Btn
          label="저장"
          icon="check"
          onPress={() => {
            if (!user) return;
            void import('../data/people')
              .then(({ updateProfile }) =>
                updateProfile(user.uid, {
                  motto,
                  jobPreferences: { ...user.jobPreferences, targetRoles: roles.split(',').map((item) => item.trim()).filter(Boolean) },
                }),
              )
              .then(() => setMessage({ ok: true, text: '저장했습니다.' }))
              .catch((error: unknown) => setMessage({ ok: false, text: error instanceof Error ? error.message : '저장하지 못했습니다.' }));
          }}
        />
      </Card>
    </Screen>
  );
}

function topicParticle(word: string): string {
  const code = word.charCodeAt(word.length - 1);
  return code >= 0xac00 && code <= 0xd7a3 && (code - 0xac00) % 28 !== 0 ? '은' : '는';
}

export function DesktopPage({ feature }: { feature: string }) {
  return (
    <Screen title="PC에서 이용해 주세요">
      <Card style={{ alignItems: 'center', gap: 12, paddingVertical: 32 }}>
        <EmptyState icon="computer" text={`${feature}${topicParticle(feature)} 넓은 화면과 편집 도구가 필요해 앱에 넣지 않았습니다.\nPC 웹에서 이어서 이용해 주세요.`} />
        <Btn label="웹으로 열기" icon="open-in-new" onPress={() => void Linking.openURL(WEB_URL)} />
      </Card>
    </Screen>
  );
}

function MarkdownBlock({ text }: { text: string }) {
  const { palette } = useTheme();
  return (
    <Markdown
      style={{
        body: { color: palette.text, fontSize: 15, lineHeight: 22 },
        link: { color: palette.primary },
        code_inline: { backgroundColor: palette.surfaceVariant, color: palette.text },
        code_block: { backgroundColor: palette.surfaceVariant, color: palette.text, borderColor: palette.border },
        fence: { backgroundColor: palette.surfaceVariant, color: palette.text, borderColor: palette.border },
        blockquote: { backgroundColor: palette.surfaceVariant, borderColor: palette.primary },
        hr: { backgroundColor: palette.border },
      }}
    >
      {text}
    </Markdown>
  );
}
