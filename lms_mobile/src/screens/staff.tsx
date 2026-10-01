import { router } from 'expo-router';
import { useState } from 'react';
import { Text } from 'react-native';
import type { AssessmentQuestion, UserRole } from '@web/domain/types';

import { useSession } from '../auth/session';
import { deleteAssessment, gradeAnswer, saveAssessment, setPublished, useAssessments, useSubmissions } from '../data/assessments';
import { reviewAttendanceRequest, setSeatPresence, useAttendance, useIssues, usePresence, useSpotChecks } from '../data/attendance';
import { selectCohort } from '../data/cohort';
import { deleteFormTask, saveFormTask, useFormResponses, useFormTasks } from '../data/forms';
import { askAssistant, executeAssistant, type AssistantAction } from '../data/jobs';
import { adjustMileage, deleteProduct, reviewPurchase, saveMileageSettings, saveProduct, useMileageSettings, useProducts, usePurchases, useTransactions } from '../data/mileage';
import { publishScheduled, removeAlert, removeNotice, removeScheduled, saveAlert, saveNotice, saveScheduled, useAlerts, useNotices, useScheduled } from '../data/notices';
import { useDb } from '../data/query';
import { createCohort, createUser, deletePackage, replaceCurriculum, resetPassword, saveIntake, savePackage, syncQualExams, updateCohort, useCohorts, useCurriculum, usePackages, useUsers } from '../data/people';
import { deleteCounsel, reviewQuest, saveCounsel, saveQuest, useCounsel, useQuestSubmissions, useQuests } from '../data/quests';
import { reviewSubmission, useSubmissions as useRecords } from '../data/records';
import { useResumes } from '../data/resumes';
import { replaceTeams, useRooms, useTeams } from '../data/seating';
import { addGithub, listGithub, removeGithub, setSourceActive, syncSources, useNotes, useSources, type GithubOwner } from '../data/study';
import { Btn, Card, Field, Muted, Row, Screen, fmt, todayKey } from '../ui/kit';
import { SettingsPage } from './student';
import { ResumeListPage } from './extra';

function push(path: string) {
  router.push(path as never);
}

export function StaffHome({ role }: { role: 'instructor' | 'admin' }) {
  const { user } = useSession();
  const today = todayKey();
  const attendance = useAttendance().filter((row) => row.dateKey === today);
  const issues = useIssues().filter((row) => row.status === 'submitted');
  return (
    <Screen title={role === 'admin' ? '관리자' : '자리 확인'} back={false}>
      <Muted>{user?.displayName} · {user?.cohortName}</Muted>
      <Card><Text>오늘 출결 {attendance.length}건 · 대기 신청 {issues.length}건</Text></Card>
      {role === 'admin' ? <CohortPicker /> : null}
      <Btn label="메뉴" onPress={() => push(role === 'admin' ? '/(admin)/menu' : '/(instructor)/menu')} />
    </Screen>
  );
}

function CohortPicker() {
  const { user } = useSession();
  const cohorts = useCohorts();
  if (!user) return null;
  return (
    <Card>
      <Text style={{ fontWeight: '700' }}>기수</Text>
      {cohorts.map((cohort) => (
        <Btn key={cohort.cohortId} label={cohort.name} tone={cohort.cohortId === user.cohortId ? 'primary' : 'ghost'} onPress={() => void selectCohort(user.uid, cohort.cohortId)} />
      ))}
    </Card>
  );
}

export function MenuPage({ role }: { role: 'instructor' | 'admin' }) {
  const base = role === 'admin' ? '/(admin)' : '/(instructor)';
  const items = role === 'instructor'
    ? [
        ['이력서', `${base}/resumes`],
        ['게시판', `${base}/board`],
        ['공지 작성', `${base}/notice/new`],
        ['평가', `${base}/exams`],
        ['평가 만들기', `${base}/exams/new`],
        ['커리큘럼', `${base}/curriculum`],
        ['수업 저장소', `${base}/sources`],
        ['복습 문제 (PC)', `${base}/desktop/practice`],
        ['마이페이지', `${base}/mypage`],
        ['설정', `${base}/settings`],
      ]
    : [
        ['기수', `${base}/cohorts`],
        ['학생', `${base}/students`],
        ['강사', `${base}/instructors`],
        ['상담', `${base}/counsel`],
        ['퀘스트', `${base}/quests`],
        ['출결', `${base}/attendance`],
        ['자리 확인', `${base}/presence`],
        ['좌석 편집 (PC)', `${base}/desktop/seating`],
        ['평가', `${base}/exams`],
        ['기록', `${base}/records`],
        ['이력서 승인', `${base}/resumes`],
        ['설문', `${base}/forms`],
        ['학습실', `${base}/study`],
        ['게시판', `${base}/board`],
        ['예약 공지', `${base}/scheduled`],
        ['알림 팝업', `${base}/alerts`],
        ['마일리지', `${base}/mileage`],
        ['LLMOps', `${base}/ai`],
        ['AI 어시스턴트', `${base}/assistant`],
        ['설정', `${base}/settings`],
      ];
  return (
    <Screen title="메뉴">
      {items.map(([title, href]) => <Row key={href} title={title ?? ''} onPress={() => push(href ?? '')} />)}
    </Screen>
  );
}

export function PeoplePage({ role }: { role: UserRole }) {
  const { user } = useSession();
  const people = useUsers().filter((row) => row.role === role && (!user?.cohortId || row.cohortId === user.cohortId || role === 'instructor'));
  const base = '/(admin)';
  return (
    <Screen title={role === 'student' ? '학생' : '강사'}>
      <Btn label="추가" onPress={() => push(`${base}/people/new/${role}`)} />
      {people.map((person) => (
        <Row key={person.uid} title={person.displayName} subtitle={person.email} onPress={() => push(`${base}/people/${person.uid}`)} />
      ))}
    </Screen>
  );
}

export function PersonPage({ uid }: { uid: string }) {
  const person = useUsers().find((row) => row.uid === uid);
  const [message, setMessage] = useState('');
  const [major, setMajor] = useState('');
  if (!person) return <Screen title="사용자" empty />;
  return (
    <Screen title={person.displayName}>
      <Muted>{person.email} · {person.role} · 마일리지 {person.mileageBalance}</Muted>
      {person.role === 'student' ? <Field label="학력 / 전공" value={major} onChangeText={setMajor} /> : null}
      {message ? <Text>{message}</Text> : null}
      <Btn label="비밀번호 재설정" onPress={() => void resetPassword(uid).then((result) => setMessage(String(result.password ?? '재설정했습니다.')))} />
      {person.role === 'student' ? <Btn label="상담 내용 저장" tone="ghost" onPress={() => void saveIntake(uid, {
        educationMajor: major, currentStatus: '', weeklyStudyHours: '', programmingLevel: '', collaborationTools: '',
        aiLlmExperience: '', motivation: '', desiredRole: '', postCompletionGoal: '', awards: '', projectLinks: '',
        teamRole: '', selfLearningStyle: '', slumpOvercomeExperience: '',
      }).then(() => setMessage('저장했습니다.'))} /> : null}
    </Screen>
  );
}

export function PersonFormPage({ role }: { role: UserRole }) {
  const { user } = useSession();
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [message, setMessage] = useState('');
  return (
    <Screen title={role === 'student' ? '학생 추가' : '강사 추가'}>
      <Field label="이메일" value={email} onChangeText={setEmail} keyboard="email-address" />
      <Field label="이름" value={name} onChangeText={setName} />
      {message ? <Text>{message}</Text> : null}
      <Btn label="만들기" onPress={() => {
        if (!user) return;
        void createUser({ email, displayName: name, role, cohortId: user.cohortId, isActive: true, skills: [], socialLinks: {}, jobPreferences: { targetRoles: [], regions: [], employmentTypes: [] }, mileageBalance: 0, mustChangePassword: true })
          .then(() => setMessage('만들었습니다.'))
          .catch((error: unknown) => setMessage(error instanceof Error ? error.message : '실패'));
      }} />
    </Screen>
  );
}

export function CohortsPage() {
  const cohorts = useCohorts();
  const [name, setName] = useState('');
  return (
    <Screen title="기수">
      <Field label="새 기수 이름" value={name} onChangeText={setName} />
      <Btn label="추가" onPress={() => void createCohort({ cohortId: '', name, isActive: true, status: 'planned', studentCount: 0 })} />
      {cohorts.map((cohort) => (
        <Card key={cohort.cohortId}>
          <Text>{cohort.name}</Text>
          <Muted>{cohort.status}</Muted>
          <Btn label={cohort.isActive ? '닫기' : '열기'} tone="ghost" onPress={() => void updateCohort(cohort.cohortId, { isActive: !cohort.isActive })} />
        </Card>
      ))}
    </Screen>
  );
}

export function CounselPage() {
  const { user } = useSession();
  const query = useCounsel(user?.cohortId ?? '');
  const students = useUsers().filter((row) => row.role === 'student');
  const [uid, setUid] = useState('');
  const [content, setContent] = useState('');
  return (
    <Screen title="상담" loading={query.isLoading} error={query.error instanceof Error ? query.error.message : null} onRefresh={() => void query.refetch()}>
      {students.slice(0, 30).map((student) => (
        <Btn key={student.uid} label={student.displayName} tone={uid === student.uid ? 'primary' : 'ghost'} onPress={() => setUid(student.uid)} />
      ))}
      <Field label="내용" value={content} onChangeText={setContent} multiline />
      <Btn label="기록" disabled={!uid} onPress={() => void saveCounsel(uid, { content, category: 'adhoc', round: 1, counseledOn: todayKey(), followUp: '', followUpDone: false })} />
      {(query.data ?? []).map((note) => (
        <Card key={note.id}>
          <Text>{note.counselorName} · {note.counseledOn}</Text>
          <Muted>{note.content ?? note.followUp}</Muted>
          <Btn label="삭제" tone="danger" onPress={() => void deleteCounsel(note.id)} />
        </Card>
      ))}
    </Screen>
  );
}

export function AdminQuestsPage() {
  const { user } = useSession();
  const quests = useQuests(user?.cohortId ?? '');
  const submissions = useQuestSubmissions(user?.cohortId ?? '');
  const [title, setTitle] = useState('');
  const [reward, setReward] = useState('1000');
  return (
    <Screen title="마일리지 미션" loading={quests.isLoading} onRefresh={() => void quests.refetch()}>
      <Field label="제목" value={title} onChangeText={setTitle} />
      <Field label="보상" value={reward} onChangeText={setReward} keyboard="numeric" />
      <Btn label="미션 만들기" onPress={() => {
        if (!user) return;
        void saveQuest(user.cohortId, { title, description: title, reward: Number(reward), evidenceType: 'text', approval: 'manual', maxCompletions: 1, startOn: null, endOn: null, published: true, closed: false, open: true, createdAt: null });
      }} />
      {(quests.data?.quests ?? []).map((quest) => <Row key={quest.id} title={quest.title} subtitle={`${quest.reward}`} />)}
      {(submissions.data ?? []).map((row) => (
        <Card key={row.id}>
          <Text>{row.studentName} · {row.questTitle}</Text>
          <Muted>{row.text || row.link}</Muted>
          <Btn label="승인" onPress={() => void reviewQuest(row.id, 'approved', '')} />
          <Btn label="반려" tone="ghost" onPress={() => void reviewQuest(row.id, 'rejected', '')} />
        </Card>
      ))}
    </Screen>
  );
}

export function AttendanceAdminPage() {
  const issues = useIssues();
  const [comment, setComment] = useState('');
  return (
    <Screen title="출결">
      {issues.map((issue) => (
        <Card key={issue.id}>
          <Text>{issue.label ?? `${issue.dateKey} ${issue.issueType}`}</Text>
          <Muted>{issue.status} · {issue.reason}</Muted>
          {issue.status === 'submitted' ? (
            <>
              <Field label="메모" value={comment} onChangeText={setComment} />
              <Btn label="승인" onPress={() => void reviewAttendanceRequest([issue.id], 'approved', comment)} />
              <Btn label="반려" tone="ghost" onPress={() => void reviewAttendanceRequest([issue.id], 'rejected', comment)} />
            </>
          ) : null}
        </Card>
      ))}
    </Screen>
  );
}

export function PresencePage() {
  const { user } = useSession();
  const students = useUsers().filter((row) => row.role === 'student' && row.cohortId === user?.cohortId);
  const dateKey = todayKey();
  const presence = usePresence().filter((row) => row.dateKey === dateKey);
  const checks = useSpotChecks();
  return (
    <Screen title="자리 확인">
      {students.map((student) => {
        const state = presence.find((row) => row.userId === student.uid)?.state ?? 'unknown';
        return (
          <Card key={student.uid}>
            <Text>{student.displayName} · {state}</Text>
            <Btn label="확인" onPress={() => void setSeatPresence(dateKey, 1, student.uid, 'confirmed')} />
            <Btn label="보류" tone="ghost" onPress={() => void setSeatPresence(dateKey, 1, student.uid, 'held')} />
          </Card>
        );
      })}
      {checks.slice(0, 5).map((check) => <Row key={check.id} title={fmt(check.checkedAt)} subtitle={`${check.items.length}명`} />)}
    </Screen>
  );
}

export function TeamEditPage() {
  const { user } = useSession();
  const teams = useTeams().filter((team) => team.cohortId === user?.cohortId);
  const students = useUsers().filter((row) => row.role === 'student' && row.cohortId === user?.cohortId);
  const [picked, setPicked] = useState<string | null>(null);
  const [name, setName] = useState('새 팀');
  return (
    <Screen title="팀 편성">
      <Muted>학생을 누른 뒤 팀을 고릅니다. 드래그 대신 탭으로 옮깁니다.</Muted>
      <Field label="팀 이름" value={name} onChangeText={setName} />
      {students.map((student) => (
        <Btn key={student.uid} label={student.displayName} tone={picked === student.uid ? 'primary' : 'ghost'} onPress={() => setPicked(student.uid)} />
      ))}
      {teams.map((team) => (
        <Btn key={team.id} label={`${team.name}에 넣기`} onPress={() => {
          if (!user || !picked) return;
          const next = teams.map((row) => row.id === team.id ? { ...row, memberIds: [...new Set([...row.memberIds, picked])] } : { ...row, memberIds: row.memberIds.filter((id) => id !== picked) });
          void replaceTeams(user.cohortId, next, []);
        }} />
      ))}
      <Btn label="팀 만들기" tone="ghost" onPress={() => {
        if (!user) return;
        void replaceTeams(user.cohortId, [...teams, { name, memberIds: picked ? [picked] : [], sortOrder: teams.length, colorIndex: 0 }], []);
      }} />
    </Screen>
  );
}

export function NoticeAdminPage({ scheduled = false }: { scheduled?: boolean }) {
  const notices = useNotices();
  const planned = useScheduled();
  const { user } = useSession();
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  return (
    <Screen title={scheduled ? '예약 공지' : '게시판'}>
      <Field label="제목" value={title} onChangeText={setTitle} />
      <Field label="내용" value={content} onChangeText={setContent} multiline />
      <Btn label="저장" onPress={() => {
        if (!user) return;
        const job = scheduled
          ? saveScheduled({ title, content, cohortId: user.cohortId })
          : saveNotice({ title, content, isFavorite: false, cohortId: user.cohortId });
        void job.then(() => { setTitle(''); setContent(''); });
      }} />
      {(scheduled ? planned : notices).map((row) => (
        <Card key={row.id}>
          <Text>{row.title}</Text>
          {'repeatType' in row ? <Btn label="지금 발행" onPress={() => void publishScheduled(row.id)} /> : null}
          <Btn label="삭제" tone="danger" onPress={() => void ('repeatType' in row ? removeScheduled(row.id) : removeNotice(row.id))} />
        </Card>
      ))}
    </Screen>
  );
}

export function AlertsAdminPage() {
  const alerts = useAlerts();
  const { user } = useSession();
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  return (
    <Screen title="알림 팝업">
      <Field label="제목" value={title} onChangeText={setTitle} />
      <Field label="내용" value={content} onChangeText={setContent} multiline />
      <Btn label="만들기" onPress={() => { if (user) void saveAlert({ title, content, cohortId: user.cohortId, isActive: true }); }} />
      {alerts.map((popup) => (
        <Card key={popup.id}>
          <Text>{popup.title}</Text>
          <Btn label="삭제" tone="danger" onPress={() => void removeAlert(popup.id)} />
        </Card>
      ))}
    </Screen>
  );
}

export function ExamsAdminPage({ readOnly = false }: { readOnly?: boolean }) {
  const exams = useAssessments();
  const base = readOnly ? '/(admin)' : '/(instructor)';
  return (
    <Screen title="성취도 평가">
      {!readOnly ? <Btn label="새 평가" onPress={() => push(`${base}/exams/new`)} /> : null}
      {exams.map((exam) => (
        <Row key={exam.id} title={exam.title} subtitle={exam.published ? '공개' : '비공개'} onPress={() => push(`${base}/exams/${exam.id}`)} />
      ))}
    </Screen>
  );
}

export function ExamEditPage({ id }: { id?: string }) {
  const exam = useAssessments().find((row) => row.id === id);
  const { user } = useSession();
  const [title, setTitle] = useState(exam?.title ?? '');
  const [prompt, setPrompt] = useState('');
  const [message, setMessage] = useState('');
  return (
    <Screen title={id ? '평가 수정' : '평가 만들기'}>
      <Field label="제목" value={title} onChangeText={setTitle} />
      <Field label="객관식 문항" value={prompt} onChangeText={setPrompt} multiline />
      {message ? <Text>{message}</Text> : null}
      <Btn label="저장" onPress={() => {
        if (!user) return;
        const questions: AssessmentQuestion[] = prompt.trim()
          ? [{ id: 'q1', order: 1, type: 'shortAnswer', prompt, points: 10, choices: [], acceptedAnswers: [], origin: 'manual' }]
          : [];
        const start = exam?.startAt ?? new Date();
        const end = exam?.endAt ?? new Date(Date.now() + 7 * 86400000);
        void saveAssessment({
          id: exam?.id ?? '',
          title,
          tags: [],
          questionCount: questions.length,
          maxScore: 10,
          startAt: start,
          endAt: end,
          published: exam?.published ?? false,
        }, questions, user.cohortId).then(() => setMessage('저장했습니다.')).catch((error: unknown) => setMessage(error instanceof Error ? error.message : '실패'));
      }} />
      {exam ? (
        <>
          <Btn label={exam.published ? '비공개' : '공개'} tone="ghost" onPress={() => void setPublished(exam.id, !exam.published)} />
          <Btn label="삭제" tone="danger" onPress={() => void deleteAssessment(exam.id).then(() => router.back())} />
        </>
      ) : null}
    </Screen>
  );
}

export function ExamDetailPage({ id, readOnly = false }: { id: string; readOnly?: boolean }) {
  const exam = useAssessments().find((row) => row.id === id);
  const submissions = useSubmissions(id);
  const base = readOnly ? '/(admin)' : '/(instructor)';
  return (
    <Screen title={exam?.title ?? '평가'} empty={!exam}>
      {!readOnly && exam ? <Btn label="수정" onPress={() => push(`${base}/exams/${exam.id}/edit`)} /> : null}
      {submissions.map((row) => (
        <Row key={row.id} title={row.userDisplayName} subtitle={`${row.totalScore}점`} onPress={() => push(`${base}/exams/${id}/sub/${row.id}`)} />
      ))}
    </Screen>
  );
}

export function GradePage({ submissionId, readOnly = false }: { submissionId: string; readOnly?: boolean }) {
  const submission = useSubmissions().find((row) => row.id === submissionId);
  const [score, setScore] = useState('0');
  if (!submission) return <Screen title="채점" empty />;
  const entries = Object.entries(submission.answers);
  return (
    <Screen title={submission.userDisplayName}>
      <Muted>총점 {submission.totalScore}</Muted>
      {entries.map(([questionId, answer]) => (
        <Card key={questionId}>
          <Text>{String(answer.value ?? '')}</Text>
          {!readOnly ? <Btn label="이 점수 저장" onPress={() => void gradeAnswer(submission.id, questionId, Number(score))} /> : null}
        </Card>
      ))}
      {!readOnly ? <Field label="점수" value={score} onChangeText={setScore} keyboard="numeric" /> : null}
    </Screen>
  );
}

export function CurriculumPage() {
  const sheets = useCurriculum();
  const { user } = useSession();
  const [title, setTitle] = useState('커리큘럼');
  const [topic, setTopic] = useState('');
  return (
    <Screen title="커리큘럼">
      <Field label="주제" value={topic} onChangeText={setTopic} />
      <Btn label="한 줄 올리기" onPress={() => {
        if (!user) return;
        void replaceCurriculum({ id: '', title, fileName: 'mobile', rows: [{ dayIndex: 1, dateLabel: todayKey(), subject: title, topic, detail: '', order: 1 }] }, user.cohortId);
      }} />
      {sheets.map((sheet) => (
        <Card key={sheet.id}>
          <Text style={{ fontWeight: '700' }}>{sheet.title}</Text>
          {sheet.rows.slice(0, 8).map((row) => <Muted key={`${row.order}`}>{row.dateLabel} {row.topic}</Muted>)}
        </Card>
      ))}
    </Screen>
  );
}

export function SourcesPage() {
  const sources = useSources();
  const notes = useNotes();
  const { user } = useSession();
  const [owner, setOwner] = useState('');
  const [owners, setOwners] = useState<GithubOwner[]>([]);
  return (
    <Screen title="수업 저장소">
      <Field label="GitHub 조직" value={owner} onChangeText={setOwner} />
      <Btn label="연결" onPress={() => { if (user) void addGithub(user.cohortId, owner).then(() => listGithub(user.cohortId).then(setOwners)); }} />
      <Btn label="동기화" tone="ghost" onPress={() => { if (user) void syncSources(user.cohortId); }} />
      {owners.map((row) => <Row key={row.id} title={row.owner} subtitle={row.lastError || '연결됨'} onPress={() => void removeGithub(row.id)} />)}
      {sources.map((source) => (
        <Card key={source.id}>
          <Text>{source.title}</Text>
          <Muted>{notes.filter((note) => note.sourceId === source.id).length}개 노트 · {source.isActive ? '공개' : '숨김'}</Muted>
          <Btn label={source.isActive ? '숨기기' : '공개'} tone="ghost" onPress={() => void setSourceActive(source.id, !source.isActive)} />
        </Card>
      ))}
    </Screen>
  );
}

export function RecordsAdminPage() {
  const rows = useRecords();
  return (
    <Screen title="기록실">
      {rows.map((row) => (
        <Card key={row.id}>
          <Text>{row.userDisplayName} · {row.title}</Text>
          <Muted>{row.status}</Muted>
          <Btn label="승인" onPress={() => void reviewSubmission(row.id, 'approved')} />
          <Btn label="반려" tone="ghost" onPress={() => void reviewSubmission(row.id, 'rejected', '반려')} />
        </Card>
      ))}
    </Screen>
  );
}

export function FormsAdminPage() {
  const tasks = useFormTasks();
  const responses = useFormResponses();
  const { user } = useSession();
  const [title, setTitle] = useState('');
  return (
    <Screen title="설문 관리">
      <Field label="제목" value={title} onChangeText={setTitle} />
      <Btn label="외부 설문 만들기" onPress={() => {
        if (!user) return;
        void saveFormTask({
          id: '', title, description: '', mode: 'external', formUrl: '', questions: [], dueAt: new Date(Date.now() + 7 * 86400000), published: true, responseCount: 0,
        }, user.cohortId, false);
      }} />
      {tasks.map((task) => (
        <Card key={task.id}>
          <Text>{task.title}</Text>
          <Muted>응답 {responses.filter((row) => row.taskId === task.id).length}</Muted>
          <Btn label="삭제" tone="danger" onPress={() => void deleteFormTask(task.id)} />
        </Card>
      ))}
    </Screen>
  );
}

export function StudyAdminPage() {
  const packs = usePackages();
  const { user } = useSession();
  const [title, setTitle] = useState('');
  return (
    <Screen title="학습실">
      <Field label="패키지 제목" value={title} onChangeText={setTitle} />
      <Btn label="추가" onPress={() => {
        if (!user) return;
        void savePackage({ id: '', title, subject: title, type: 'review', units: [], courses: [], isPublished: true, sortOrder: 0 }, user.cohortId);
      }} />
      {packs.map((pack) => (
        <Card key={pack.id}>
          <Text>{pack.title}</Text>
          <Btn label="삭제" tone="danger" onPress={() => void deletePackage(pack.id)} />
        </Card>
      ))}
    </Screen>
  );
}

export function MileageAdminPage() {
  const products = useProducts();
  const purchases = usePurchases();
  const tx = useTransactions();
  const settings = useMileageSettings();
  const { user } = useSession();
  const [name, setName] = useState('');
  const [price, setPrice] = useState('1000');
  const [uid, setUid] = useState('');
  const [amount, setAmount] = useState('0');
  const [reason, setReason] = useState('조정');
  return (
    <Screen title="마일리지">
      <Field label="상품" value={name} onChangeText={setName} />
      <Field label="가격" value={price} onChangeText={setPrice} keyboard="numeric" />
      <Btn label="상품 추가" onPress={() => {
        if (!user) return;
        void saveProduct({ id: '', name, description: '', category: 'etc', pricingType: 'fixed', fixedPrice: Number(price), isActive: true, sortOrder: 0 }, user.cohortId);
      }} />
      {products.map((product) => <Row key={product.id} title={product.name} subtitle={`${product.fixedPrice ?? 0}`} onPress={() => void deleteProduct(product.id)} />)}
      {purchases.map((row) => (
        <Card key={row.id}>
          <Text>{row.userDisplayName} · {row.totalAmount} · {row.status}</Text>
          <Btn label="승인" onPress={() => void reviewPurchase(row.id, 'approved')} />
          <Btn label="반려" tone="ghost" onPress={() => void reviewPurchase(row.id, 'rejected')} />
        </Card>
      ))}
      <Field label="학생 uid" value={uid} onChangeText={setUid} />
      <Field label="금액" value={amount} onChangeText={setAmount} keyboard="numeric" />
      <Field label="사유" value={reason} onChangeText={setReason} />
      <Btn label="잔액 조정" onPress={() => void adjustMileage(uid, Number(amount), reason)} />
      <Btn label="설정 저장" tone="ghost" onPress={() => { if (user) void saveMileageSettings(settings, user.cohortId); }} />
      {tx.slice(0, 10).map((row) => <Row key={row.id} title={row.reason} subtitle={String(row.amount)} />)}
    </Screen>
  );
}

export function AiPage() {
  const logs = useDb()?.aiLogs ?? [];
  const evals = useDb()?.aiEvals ?? [];
  return (
    <Screen title="LLMOps">
      <Btn label="자격 일정 동기화" onPress={() => void syncQualExams()} />
      {logs.slice(0, 30).map((log) => <Row key={log.id} title={log.type} subtitle={`${log.model} · ${log.status} · ${log.latencyMs}ms`} />)}
      {evals.slice(0, 10).map((row) => <Row key={row.id} title={row.suite} subtitle={`${Math.round(row.passRate * 100)}% · ${fmt(row.ranAt)}`} />)}
    </Screen>
  );
}

export function AssistantPage() {
  const { user } = useSession();
  const [text, setText] = useState('');
  const [context, setContext] = useState('');
  const [log, setLog] = useState<string[]>([]);
  const [actions, setActions] = useState<AssistantAction[]>([]);
  return (
    <Screen title="AI 어시스턴트">
      {log.map((line, index) => <Card key={index}><Text>{line}</Text></Card>)}
      {actions.map((action) => (
        <Btn key={action.id} label={`실행 · ${action.type}`} onPress={() => { if (user) void executeAssistant(action, user.cohortId); }} />
      ))}
      <Field label="요청" value={text} onChangeText={setText} multiline />
      <Btn label="보내기" onPress={() => {
        if (!user || !text.trim()) return;
        const messages = [{ role: 'user' as const, content: text.trim() }];
        void askAssistant(messages, context, user.cohortId).then((result) => {
          setLog((prev) => [...prev, text.trim(), result.reply]);
          setContext(result.context);
          setActions(result.actions);
          setText('');
        });
      }} />
    </Screen>
  );
}

export function RoomsPage() {
  const rooms = useRooms();
  return (
    <Screen title="착석 현황">
      {rooms.map((room) => (
        <Card key={room.id}>
          <Text>{room.roomNumber ?? room.id}</Text>
          <Muted>좌석 {room.cells.filter((cell) => cell.type === 'seat').length}</Muted>
        </Card>
      ))}
      <Btn label="배치 편집은 PC" tone="ghost" onPress={() => push('/(admin)/desktop/seating')} />
    </Screen>
  );
}

export { SettingsPage, ResumeListPage };
