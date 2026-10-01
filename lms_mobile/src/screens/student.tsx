import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Linking, Text } from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import Markdown from 'react-native-markdown-display';
import {
  RecordTypeDescriptions,
  RecordTypeLabels,
  SubmissionStatusLabels,
} from '@web/domain/constants';
import { lessonDays } from '@web/features/study/lessonDays';
import { EVIDENCE_LABEL, STATUS_LABEL } from '@web/features/quests/questLabels';
import type { FormAnswer, FormQuestion, RecordType } from '@web/domain/types';

import { useSession } from '../auth/session';
import { useIssues, submitAttendanceRequest, cancelAttendanceRequest } from '../data/attendance';
import { useFormResponses, useFormTasks, markFormResponded, submitFormResponse } from '../data/forms';
import { askChatbot, askCoach } from '../data/jobs';
import { useCart, useProducts, usePurchases, useTransactions, createPurchase } from '../data/mileage';
import { addComment, addPost, likePost, useComments, useNotices, usePosts } from '../data/notices';
import { useDb } from '../data/query';
import { useQuests, submitQuest } from '../data/quests';
import { createSubmission, uploadEvidence, useSubmissions } from '../data/records';
import { fetchTake, submitAssessment, useAssessments, useSubmissions as useExamSubs } from '../data/assessments';
import { useRooms, useTeams } from '../data/seating';
import { useNotes, useSources } from '../data/study';
import { Btn, Card, Field, Muted, Row, Screen, fmt, todayKey } from '../ui/kit';
import { useTheme } from '../theme/Theme';
import { AlertHost } from './extra';
import { queryClient, queryKeys } from '../data/query';

function go(path: string) {
  router.push(path as never);
}

export function DashboardPage() {
  const { user } = useSession();
  const db = useDb();
  const notices = useNotices().slice(0, 5);
  const today = todayKey();
  const attendance = (db?.attendances ?? []).filter((row) => row.userId === user?.uid && row.dateKey === today);
  return (
    <Screen title="대시보드" back={false} onRefresh={() => void queryClient.invalidateQueries({ queryKey: queryKeys.bootstrap })}>
      <AlertHost />
      <Card>
        <Text style={{ fontSize: 20, fontWeight: '700' }}>{user?.displayName}</Text>
        <Muted>{user?.cohortName || '기수 없음'} · 마일리지 {user?.mileageBalance ?? 0}</Muted>
        <Muted>오늘 출결 {attendance[0]?.status ?? '기록 없음'}</Muted>
      </Card>
      <Text style={{ fontWeight: '700' }}>공지</Text>
      {notices.length === 0 ? <Muted>공지가 없습니다.</Muted> : notices.map((notice) => (
        <Row key={notice.id} title={notice.title} subtitle={fmt(notice.createdAt)} onPress={() => go(`/(student)/notice/${notice.id}`)} />
      ))}
      <Btn label="챗봇" onPress={() => go('/(student)/chat')} />
    </Screen>
  );
}

export function BoardPage() {
  const notices = useNotices();
  const posts = usePosts();
  const { user } = useSession();
  const [content, setContent] = useState('');
  return (
    <Screen title="게시판" back={false}>
      {notices.map((notice) => (
        <Row key={notice.id} title={notice.isFavorite ? `중요 · ${notice.title}` : notice.title} subtitle={notice.authorName} onPress={() => go(`/(student)/notice/${notice.id}`)} />
      ))}
      <Field label="글" value={content} onChangeText={setContent} multiline />
      <Btn label="올리기" disabled={!content.trim() || !user} onPress={() => { if (user) { addPost(user.uid, user.displayName, content.trim()); setContent(''); } }} />
      {posts.map((post) => (
        <Row key={post.id} title={post.authorName} subtitle={`${post.content} · 좋아요 ${post.likeCount}`} onPress={() => { likePost(post.id); go(`/(student)/post/${post.id}`); }} />
      ))}
    </Screen>
  );
}

export function NoticePage({ id }: { id: string }) {
  const notice = useNotices().find((row) => row.id === id);
  return (
    <Screen title="공지" empty={!notice} emptyText="공지를 찾지 못했습니다.">
      {notice ? (
        <Card>
          <Text style={{ fontWeight: '700', fontSize: 18 }}>{notice.title}</Text>
          <Muted>{notice.authorName} · {fmt(notice.createdAt)}</Muted>
          <Text>{notice.content}</Text>
        </Card>
      ) : null}
    </Screen>
  );
}

export function PostPage({ id }: { id: string }) {
  const post = usePosts().find((row) => row.id === id);
  const comments = useComments(id);
  const { user } = useSession();
  const [text, setText] = useState('');
  return (
    <Screen title="게시글" empty={!post}>
      {post ? <Card><Text>{post.content}</Text><Muted>{post.authorName}</Muted></Card> : null}
      {comments.map((comment) => <Row key={comment.id} title={comment.authorName} subtitle={comment.content} />)}
      <Field label="댓글" value={text} onChangeText={setText} />
      <Btn label="댓글 달기" disabled={!text.trim() || !user} onPress={() => { if (user) { addComment(id, user.uid, user.displayName, text.trim()); setText(''); } }} />
    </Screen>
  );
}

export function RecordsPage() {
  const { user } = useSession();
  const rows = useSubmissions().filter((row) => row.userId === user?.uid);
  return (
    <Screen title="기록실">
      <Btn label="기록 올리기" onPress={() => go('/(student)/records/new')} />
      {rows.length === 0 ? <Muted>올린 기록이 없습니다.</Muted> : rows.map((row) => (
        <Row key={row.id} title={row.title} subtitle={`${RecordTypeLabels[row.type]} · ${SubmissionStatusLabels[row.status] ?? row.status}`} />
      ))}
    </Screen>
  );
}

export function RecordNewPage() {
  const types = Object.keys(RecordTypeLabels) as RecordType[];
  return (
    <Screen title="기록 종류">
      {types.map((type) => (
        <Row key={type} title={RecordTypeLabels[type]} subtitle={RecordTypeDescriptions[type]} onPress={() => go(`/(student)/records/form/${type}`)} />
      ))}
    </Screen>
  );
}

export function RecordFormPage({ type }: { type: RecordType }) {
  const { user } = useSession();
  const [title, setTitle] = useState('');
  const [link, setLink] = useState('');
  const [score, setScore] = useState('');
  const [body, setBody] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  async function pickAndSend() {
    if (!user || !title.trim()) return;
    setBusy(true);
    try {
      const picked = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true });
      const evidence = [];
      if (!picked.canceled && picked.assets[0]) {
        const asset = picked.assets[0];
        evidence.push(await uploadEvidence({ uri: asset.uri, name: asset.name, type: asset.mimeType ?? 'application/octet-stream' }));
      }
      await createSubmission({
        userId: user.uid,
        userDisplayName: user.displayName,
        title: title.trim(),
        type,
        status: 'pending',
        link: link || undefined,
        quizScore: score ? Number(score) : undefined,
        learningContent: body || undefined,
        mileageGranted: false,
        mileageAmount: 0,
      }, evidence, user.cohortId);
      router.back();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '제출에 실패했습니다.');
    } finally {
      setBusy(false);
    }
  }
  return (
    <Screen title={RecordTypeLabels[type] ?? '기록'}>
      <Field label="제목" value={title} onChangeText={setTitle} />
      {type === 'blog' ? <Field label="링크" value={link} onChangeText={setLink} keyboard="url" /> : null}
      {type === 'precourseQuiz' ? <Field label="점수" value={score} onChangeText={setScore} keyboard="numeric" /> : null}
      <Field label="내용" value={body} onChangeText={setBody} multiline />
      {message ? <Text>{message}</Text> : null}
      <Btn label={busy ? '올리는 중…' : '증빙과 함께 제출'} disabled={busy} onPress={() => void pickAndSend()} />
    </Screen>
  );
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
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [message, setMessage] = useState('');
  if (!task) return <Screen title="설문" empty emptyText="설문을 찾지 못했습니다." />;
  async function send() {
    if (!user || !task) return;
    try {
      if (task.mode === 'external') {
        if (task.formUrl) await Linking.openURL(task.formUrl);
        await markFormResponded(task.id, user.uid);
      } else {
        const payload: Record<string, FormAnswer> = {};
        for (const question of task.questions) payload[question.id] = answers[question.id] ?? '';
        await submitFormResponse(task.id, payload);
      }
      setMessage('제출했습니다.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '제출에 실패했습니다.');
    }
  }
  return (
    <Screen title={task.title}>
      <Muted>{task.description}</Muted>
      {mine ? <Muted>이미 제출했습니다. 마감 전이면 다시 낼 수 있습니다.</Muted> : null}
      {task.mode === 'builtin' ? task.questions.map((question) => (
        <QuestionField key={question.id} question={question} value={answers[question.id] ?? ''} onChange={(value) => setAnswers((prev) => ({ ...prev, [question.id]: value }))} />
      )) : <Muted>외부 설문입니다. 열기를 누르면 브라우저로 이동합니다.</Muted>}
      {message ? <Text>{message}</Text> : null}
      <Btn label="제출" onPress={() => void send()} />
    </Screen>
  );
}

function QuestionField({ question, value, onChange }: { question: FormQuestion; value: string; onChange: (value: string) => void }) {
  if (question.type === 'single' || question.type === 'multi') {
    return (
      <Card>
        <Text>{question.title}</Text>
        {(question.options ?? []).map((option) => (
          <Btn key={option} label={option} tone={value === option ? 'primary' : 'ghost'} onPress={() => onChange(option)} />
        ))}
      </Card>
    );
  }
  return <Field label={question.title} value={value} onChangeText={onChange} multiline={question.type === 'long'} keyboard={question.type === 'scale' ? 'numeric' : 'default'} />;
}

export function QualPage() {
  const exams = useDb()?.qualExams ?? [];
  return (
    <Screen title="자격 시험">
      {exams.length === 0 ? <Muted>일정이 없습니다.</Muted> : exams.map((exam) => (
        <Row key={`${exam.qualgbCd}-${exam.implSeq}`} title={exam.qualgbNm ?? exam.qualgbCd} subtitle={`${exam.implYy}년 ${exam.implSeq}회`} />
      ))}
    </Screen>
  );
}

export function SeatingPage() {
  const { user } = useSession();
  const rooms = useRooms().filter((room) => !user?.cohortId || room.cohortId === user.cohortId);
  const room = rooms[0];
  const assignment = (useDb()?.seatingAssignments ?? []).find((row) => row.roomId === room?.id);
  return (
    <Screen title="자리 배치">
      {!room ? <Muted>확정된 강의실이 없습니다.</Muted> : (
        <Card>
          <Text style={{ fontWeight: '700' }}>{room.roomNumber ?? '강의실'}</Text>
          {room.cells.filter((cell) => cell.type === 'seat').map((cell) => (
            <Muted key={cell.seatId}>{cell.label || `${cell.row}-${cell.col}`} · {assignment?.seatNames[cell.seatId] ?? '빈 자리'}</Muted>
          ))}
        </Card>
      )}
      <Btn label="프로젝트 팀" onPress={() => go('/(student)/teams')} />
    </Screen>
  );
}

export function TeamsPage() {
  const { user } = useSession();
  const teams = useTeams().filter((team) => team.cohortId === user?.cohortId);
  const users = useDb()?.users ?? [];
  return (
    <Screen title="프로젝트 팀">
      {teams.length === 0 ? <Muted>팀이 없습니다.</Muted> : teams.map((team) => (
        <Card key={team.id}>
          <Text style={{ fontWeight: '700' }}>{team.name}</Text>
          {team.memberIds.map((id) => <Muted key={id}>{users.find((row) => row.uid === id)?.displayName ?? id}</Muted>)}
        </Card>
      ))}
    </Screen>
  );
}

export function AttendancePage() {
  const { user } = useSession();
  const issues = useIssues().filter((row) => row.userId === user?.uid);
  const [dateKey, setDate] = useState(todayKey());
  const [reason, setReason] = useState('');
  const [kind, setKind] = useState('late');
  const [message, setMessage] = useState('');
  return (
    <Screen title="출결 신청">
      <Field label="날짜" value={dateKey} onChangeText={setDate} />
      <Field label="사유" value={reason} onChangeText={setReason} multiline />
      {(['late', 'earlyLeave', 'outing', 'absent'] as const).map((item) => (
        <Btn key={item} label={item} tone={kind === item ? 'primary' : 'ghost'} onPress={() => setKind(item)} />
      ))}
      {message ? <Text>{message}</Text> : null}
      <Btn label="신청" onPress={() => {
        if (!user) return;
        void submitAttendanceRequest({ userId: user.uid, dateKey, issueType: kind, reason, cohortId: user.cohortId })
          .then(() => setMessage('신청했습니다.'))
          .catch((error: unknown) => setMessage(error instanceof Error ? error.message : '실패'));
      }} />
      {issues.map((issue) => (
        <Card key={issue.id}>
          <Text>{issue.label ?? `${issue.dateKey} ${issue.issueType}`}</Text>
          <Muted>{issue.status}</Muted>
          {issue.status === 'submitted' ? <Btn label="취소" tone="ghost" onPress={() => void cancelAttendanceRequest(issue.id)} /> : null}
        </Card>
      ))}
    </Screen>
  );
}

export function StudyPage() {
  const notes = useNotes();
  const sets = useDb()?.practiceSets ?? [];
  const days = lessonDays(sets, notes).slice(0, 14);
  return (
    <Screen title="학습실" back={false}>
      <Btn label="오답 · 복습 기록" onPress={() => go('/(student)/wrong')} />
      <Btn label="노트" onPress={() => go('/(student)/notes')} />
      <Btn label="연습장 (PC)" tone="ghost" onPress={() => go('/(student)/desktop/playground')} />
      {days.map((day) => (
        <Row key={day.date} title={day.date} subtitle={day.note ? '노트 있음' : '노트 없음'} onPress={() => day.note && go(`/(student)/notes/${day.note.id}`)} />
      ))}
    </Screen>
  );
}

export function NotesPage() {
  const notes = useNotes();
  const sources = useSources();
  return (
    <Screen title="공부 노트">
      {notes.length === 0 ? <Muted>노트가 없습니다.</Muted> : notes.map((note) => (
        <Row key={note.id} title={sources.find((source) => source.id === note.sourceId)?.title ?? note.scopeKey ?? '노트'} subtitle={note.status} onPress={() => go(`/(student)/notes/${note.id}`)} />
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

export function WrongPage() {
  const attempts = useDb()?.practiceAttempts ?? [];
  const { user } = useSession();
  const mine = attempts.filter((row) => row.uid === user?.uid && !row.passed);
  return (
    <Screen title="오답노트">
      <Muted>코드 연습은 PC에서 이어서 하세요.</Muted>
      {mine.length === 0 ? <Muted>틀린 문제가 없습니다.</Muted> : mine.map((row) => (
        <Row key={row.id} title={row.setId} subtitle={`문제 ${row.index + 1}`} />
      ))}
    </Screen>
  );
}

export function MileagePage() {
  const { user } = useSession();
  const tx = useTransactions(user?.uid);
  return (
    <Screen title="마일리지" back={false}>
      <Card><Text style={{ fontSize: 28, fontWeight: '800' }}>{user?.mileageBalance ?? 0}</Text><Muted>보유 마일리지</Muted></Card>
      <Btn label="상점" onPress={() => go('/(student)/shop')} />
      <Btn label="장바구니" tone="ghost" onPress={() => go('/(student)/cart')} />
      <Btn label="퀘스트" tone="ghost" onPress={() => go('/(student)/quests')} />
      {tx.map((row) => <Row key={row.id} title={row.reason} subtitle={`${row.amount > 0 ? '+' : ''}${row.amount}`} />)}
    </Screen>
  );
}

export function ShopPage() {
  const products = useProducts().filter((product) => product.isActive);
  const add = useCart((state) => state.add);
  return (
    <Screen title="상점">
      {products.map((product) => (
        <Card key={product.id}>
          <Text style={{ fontWeight: '700' }}>{product.name}</Text>
          <Muted>{product.description}</Muted>
          <Muted>{product.pricingType === 'fixed' ? `${product.fixedPrice ?? 0}` : '가격 직접 입력'}</Muted>
          <Btn label="담기" onPress={() => add({
            productId: product.id,
            productName: product.name,
            category: product.category,
            pricingType: product.pricingType,
            unitPrice: product.fixedPrice ?? 0,
            quantity: 1,
          })} />
        </Card>
      ))}
    </Screen>
  );
}

export function CartPage() {
  const { user } = useSession();
  const items = useCart((state) => state.items);
  const remove = useCart((state) => state.remove);
  const clear = useCart((state) => state.clear);
  const total = items.reduce((sum, item) => sum + item.unitPrice * item.quantity, 0);
  const [message, setMessage] = useState('');
  return (
    <Screen title="장바구니">
      {items.length === 0 ? <Muted>장바구니가 비어 있습니다.</Muted> : items.map((item) => (
        <Card key={item.productId}>
          <Text>{item.productName} × {item.quantity}</Text>
          <Btn label="빼기" tone="ghost" onPress={() => remove(item.productId)} />
        </Card>
      ))}
      <Muted>합계 {total}</Muted>
      {message ? <Text>{message}</Text> : null}
      <Btn label="신청" disabled={!user || items.length === 0} onPress={() => {
        if (!user) return;
        void createPurchase({ userId: user.uid, userDisplayName: user.displayName, items, totalAmount: total, status: 'pending' }, user.cohortId)
          .then(() => { clear(); setMessage('신청했습니다.'); })
          .catch((error: unknown) => setMessage(error instanceof Error ? error.message : '실패'));
      }} />
      {usePurchases(user?.uid).map((row) => <Row key={row.id} title={`${row.totalAmount}`} subtitle={row.status} />)}
    </Screen>
  );
}

export function QuestsPage() {
  const { user } = useSession();
  const query = useQuests(user?.cohortId ?? '');
  const [text, setText] = useState('');
  return (
    <Screen title="퀘스트" loading={query.isLoading} error={query.error instanceof Error ? query.error.message : null} onRefresh={() => void query.refetch()} refreshing={query.isRefetching}>
      {(query.data?.quests ?? []).filter((quest) => quest.open).map((quest) => (
        <Card key={quest.id}>
          <Text style={{ fontWeight: '700' }}>{quest.title}</Text>
          <Muted>{quest.description}</Muted>
          <Muted>{quest.reward} · {EVIDENCE_LABEL[quest.evidenceType]}</Muted>
          {quest.evidenceType === 'text' || quest.evidenceType === 'link' ? (
            <Field label="인증" value={text} onChangeText={setText} />
          ) : null}
          <Btn label="제출" onPress={() => void submitQuest(quest.id, quest.evidenceType === 'link' ? { link: text } : { text })} />
        </Card>
      ))}
      {(query.data?.submissions ?? []).map((row) => <Row key={row.id} title={row.questTitle} subtitle={STATUS_LABEL[row.status]} />)}
    </Screen>
  );
}

export function ExamsPage() {
  const exams = useAssessments().filter((exam) => exam.published);
  const { user } = useSession();
  const mine = useExamSubs().filter((row) => row.userId === user?.uid);
  return (
    <Screen title="성취도평가">
      {exams.map((exam) => {
        const done = mine.some((row) => row.assessmentId === exam.id);
        return (
          <Row key={exam.id} title={exam.title} subtitle={done ? '제출함' : `${fmt(exam.startAt)} ~ ${fmt(exam.endAt)}`} onPress={() => go(done ? `/(student)/exams/${exam.id}/result` : `/(student)/exams/${exam.id}/take`)} />
        );
      })}
    </Screen>
  );
}

export function ExamTakePage({ id }: { id: string }) {
  const exam = useAssessments().find((row) => row.id === id);
  const [questions, setQuestions] = useState<Awaited<ReturnType<typeof fetchTake>>>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  useEffect(() => {
    let cancelled = false;
    void fetchTake(id)
      .then((rows) => {
        if (!cancelled) setQuestions(rows);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '시험을 열지 못했습니다.');
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);
  return (
    <Screen title={exam?.title ?? '응시'} loading={!loaded && !error} error={error}>
      {questions.map((question) => (
        <Card key={question.id}>
          <Text>{question.prompt}</Text>
          {question.type === 'multipleChoice' ? question.choices.map((choice, index) => (
            <Btn key={choice} label={choice} tone={answers[question.id] === String(index) ? 'primary' : 'ghost'} onPress={() => setAnswers((prev) => ({ ...prev, [question.id]: String(index) }))} />
          )) : <Field label="답" value={answers[question.id] ?? ''} onChangeText={(value) => setAnswers((prev) => ({ ...prev, [question.id]: value }))} />}
        </Card>
      ))}
      <Btn label="제출" onPress={() => {
        const raw: Record<string, number | string | null> = {};
        for (const question of questions) {
          const value = answers[question.id];
          raw[question.id] = question.type === 'multipleChoice' ? (value === undefined ? null : Number(value)) : (value ?? '');
        }
        void submitAssessment(id, raw).then(() => go(`/(student)/exams/${id}/result`)).catch((err: unknown) => setError(err instanceof Error ? err.message : '제출 실패'));
      }} />
    </Screen>
  );
}

export function ExamResultPage({ id }: { id: string }) {
  const { user } = useSession();
  const submission = useExamSubs(id).find((row) => row.userId === user?.uid);
  return (
    <Screen title="결과" empty={!submission} emptyText="아직 제출 결과가 없습니다.">
      {submission ? <Card><Text style={{ fontSize: 28, fontWeight: '800' }}>{submission.totalScore}</Text><Muted>{fmt(submission.submittedAt)}</Muted></Card> : null}
    </Screen>
  );
}

export function MorePage() {
  const links: { title: string; href: string }[] = [
    { title: '기록실', href: '/(student)/records' },
    { title: '설문 · 제출', href: '/(student)/forms' },
    { title: '자격 시험', href: '/(student)/qual' },
    { title: '자리 배치', href: '/(student)/seating' },
    { title: '출결 신청', href: '/(student)/attendance' },
    { title: '성취도평가', href: '/(student)/exams' },
    { title: '이력서', href: '/(student)/resume' },
    { title: '공고 맞춤 지원', href: '/(student)/apply' },
    { title: '코치에게 묻기', href: '/(student)/coach' },
    { title: '마이페이지', href: '/(student)/mypage' },
    { title: '설정', href: '/(student)/settings' },
  ];
  return (
    <Screen title="더보기" back={false}>
      {links.map((link) => <Row key={link.href} title={link.title} onPress={() => go(link.href)} />)}
    </Screen>
  );
}

export function ChatPage() {
  const [text, setText] = useState('');
  const [log, setLog] = useState<{ role: string; text: string }[]>([]);
  return (
    <Screen title="학습 도우미">
      {log.map((line, index) => <Card key={`${line.role}-${index}`}><Muted>{line.role}</Muted><Text>{line.text}</Text></Card>)}
      <Field label="메시지" value={text} onChangeText={setText} />
      <Btn label="보내기" onPress={() => {
        const message = text.trim();
        if (!message) return;
        setText('');
        setLog((prev) => [...prev, { role: '나', text: message }]);
        void askChatbot(message).then((answer) => setLog((prev) => [...prev, { role: '도우미', text: answer }]));
      }} />
    </Screen>
  );
}

export function CoachPage() {
  const resumes = useDb()?.resumes ?? [];
  const { user } = useSession();
  const base = resumes.find((resume) => resume.userId === user?.uid && resume.isBaseResume);
  const [text, setText] = useState('');
  const [log, setLog] = useState<{ role: string; text: string }[]>([]);
  return (
    <Screen title="코치에게 묻기">
      {log.map((line, index) => <Card key={`${index}`}><Text>{line.text}</Text></Card>)}
      <Field label="메시지" value={text} onChangeText={setText} />
      <Btn label="보내기" onPress={() => {
        const message = text.trim();
        if (!message) return;
        setText('');
        void askCoach(message, base?.id ?? null).then((reply) => {
          const jobs = reply.jobs.map((job) => `${job.company} ${job.title}`).join('\n');
          setLog((prev) => [...prev, { role: '나', text: message }, { role: '코치', text: `${reply.reply}\n${jobs}` }]);
        });
      }} />
    </Screen>
  );
}

export function SettingsPage() {
  const { mode, setMode } = useTheme();
  const { signOut } = useSession();
  return (
    <Screen title="설정">
      {(['system', 'light', 'dark'] as const).map((item) => (
        <Btn key={item} label={item === 'system' ? '시스템' : item === 'light' ? '밝게' : '어둡게'} tone={mode === item ? 'primary' : 'ghost'} onPress={() => setMode(item)} />
      ))}
      <Btn label="로그아웃" tone="danger" onPress={() => void signOut()} />
    </Screen>
  );
}

export function MyPage() {
  const { user } = useSession();
  const [motto, setMotto] = useState(user?.motto ?? '');
  const [roles, setRoles] = useState(user?.jobPreferences.targetRoles.join(', ') ?? '');
  const [message, setMessage] = useState('');
  return (
    <Screen title="마이페이지">
      <Muted>{user?.email}</Muted>
      <Field label="좌우명" value={motto} onChangeText={setMotto} />
      <Field label="희망 직무 (쉼표)" value={roles} onChangeText={setRoles} />
      {message ? <Text>{message}</Text> : null}
      <Btn label="저장" onPress={() => {
        if (!user) return;
        void import('../data/people').then(({ updateProfile }) => updateProfile(user.uid, {
          motto,
          jobPreferences: { ...user.jobPreferences, targetRoles: roles.split(',').map((item) => item.trim()).filter(Boolean) },
        })).then(() => setMessage('저장했습니다.')).catch((error: unknown) => setMessage(error instanceof Error ? error.message : '실패'));
      }} />
    </Screen>
  );
}

export function DesktopPage({ feature }: { feature: string }) {
  return (
    <Screen title="PC에서 이용해 주세요">
      <Muted>{feature}은 코드 편집기와 실행기가 필요해 앱에 넣지 않았습니다.</Muted>
      <Btn label="웹으로 열기" onPress={() => void Linking.openURL(process.env.EXPO_PUBLIC_WEB_URL || 'http://127.0.0.1:5173')} />
    </Screen>
  );
}

function MarkdownBlock({ text }: { text: string }) {
  return <Markdown>{text}</Markdown>;
}
