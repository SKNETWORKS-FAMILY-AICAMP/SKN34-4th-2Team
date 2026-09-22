import { useCallback, useRef, useSyncExternalStore } from 'react';

import type {
  AlertPopup,
  Assessment,
  AssessmentAnswerEntry,
  AssessmentQuestion,
  AssessmentSubmission,
  Attendance,
  Cohort,
  FormTask,
  MileageProduct,
  MileageTransaction,
  Notice,
  Post,
  PostComment,
  PurchaseRequest,
  QualExamSchedule,
  Resume,
  ResumeFeedback,
  ScheduledNotice,
  SeatPresenceState,
  Submission,
  SubmissionStatus,
  Todo,
  User,
} from '../domain/types';
import { emptyDb, getDb, mutate, nextId, subscribe, type Database } from './store';
import { dateKeyOf } from './seed';
import { http, readApiError } from './http';
import { fetchBootstrap, lastBootstrapSession } from './bootstrap';
import { getBootstrapDb, subscribeBootstrap } from './bootstrapStore';
import { queryClient, queryKeys } from './queryClient';

function isTestMode(): boolean {
  return typeof import.meta !== 'undefined' && import.meta.env?.MODE === 'test';
}

function isApiId(id: string | undefined): id is string {
  return id !== undefined && /^\d+$/.test(id);
}

export function apiCohortId(): string {
  return lastBootstrapSession().cohortId;
}

async function invalidateBootstrap(): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: queryKeys.bootstrap });
}

async function runCommand(op: string, payload: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
  const { data } = await http.post<Record<string, unknown>>('/command', { op, payload });
  await invalidateBootstrap();
  return data;
}

export async function applyBootstrap(): Promise<boolean> {
  try {
    const db = await fetchBootstrap();
    queryClient.setQueryData(queryKeys.bootstrap, db);
    return true;
  } catch {
    return false;
  }
}

/**
 * 조회 훅 — Flutter의 `watch*` 스트림 자리.
 *
 * `select`는 스냅샷에서 필요한 조각만 꺼낸다. 새 배열을 만들어 돌려주면 매번
 * 다른 참조가 되어 무한 렌더가 되므로, 목록을 거르는 select는 `useFiltered`로
 * 감싸 원본 배열이 바뀔 때만 다시 거른다.
 */
/**
 * 화면이 보는 조회 결과.
 *
 * 지금은 메모리라 언제나 즉시 성공한다. 하지만 서버를 붙이면 **첫 렌더에 데이터가
 * 없다** — 응답이 오기 전에 화면은 이미 그려져야 하기 때문이다. 그때 화면 26개를
 * 다시 열지 않으려면 「아직 없을 수 있다」를 지금부터 타입에 담아 둬야 한다.
 *
 * 서버로 옮길 때 바뀌는 곳은 이 파일 안쪽뿐이고, 화면은 그대로 둔다.
 */
export interface Query<T> {
  data: T | undefined;
  loading: boolean;
  error: Error | null;
}

export function useDb<T>(select: (db: Database) => T): T {
  const cache = useRef<T | null>(null);

  const getSnapshot = useCallback(() => {
    const source = isTestMode() ? getDb() : getBootstrapDb();
    const next = select(source);
    const prev = cache.current;
    if (prev !== null && shallowEqual(prev, next)) return prev;
    cache.current = next;
    return next;
  }, [select]);

  const subscribeStore = isTestMode() ? subscribe : subscribeBootstrap;
  return useSyncExternalStore(subscribeStore, getSnapshot, getSnapshot);
}

/** 배열·객체를 한 겹만 견준다. 저장소가 불변이라 이 정도면 충분하다. */
function shallowEqual(a: unknown, b: unknown): boolean {
  if (Object.is(a, b)) return true;
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((item, i) => Object.is(item, b[i]));
  }
  // `db.alertDismissals[uid] ?? {}`처럼 없는 값을 빈 객체로 메우는 select가
  // 있다. 그 빈 객체는 매번 새것이라, 객체도 한 겹 견줘야 고리가 끊긴다.
  if (isPlainObject(a) && isPlainObject(b)) {
    const keysA = Object.keys(a);
    const keysB = Object.keys(b);
    return keysA.length === keysB.length && keysA.every((k) => Object.is(a[k], b[k]));
  }
  return false;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !(value instanceof Date);
}

// ── 사용자 · 기수 ──────────────────────────────────────

export function useUsers(): User[] {
  return useDb((db) => db.users);
}

export function useUser(uid: string | undefined): User | undefined {
  return useDb((db) => db.users.find((u) => u.uid === uid));
}

export function useStudents(cohortId: string): User[] {
  return useDb((db) => db.users.filter((u) => u.role === 'student' && u.cohortId === cohortId));
}

export function useInstructors(): User[] {
  return useDb((db) => db.users.filter((u) => u.role === 'instructor'));
}

export function useCohorts(): Cohort[] {
  return useDb((db) => db.cohorts);
}

export function updateUser(uid: string, patch: Partial<User>): void {
  mutate((db) => ({
    users: db.users.map((u) => (u.uid === uid ? { ...u, ...patch } : u)),
  }));
  if (!isTestMode()) void runCommand('updateProfile', { uid, ...patch });
}

export function createUser(user: User): void {
  mutate((db) => ({ users: [...db.users, user] }));
  if (!isTestMode()) void runCommand('createUser', { ...user });
}

export function createCohort(cohort: Cohort): void {
  mutate((db) => ({ cohorts: [...db.cohorts, cohort] }));
  if (!isTestMode()) void runCommand('createCohort', { ...cohort });
}

export function updateCohort(cohortId: string, patch: Partial<Cohort>): void {
  mutate((db) => ({
    cohorts: db.cohorts.map((c) => (c.cohortId === cohortId ? { ...c, ...patch } : c)),
  }));
  if (!isTestMode()) void runCommand('updateCohort', { cohortId, ...patch });
}

// ── 공지 · 게시판 ──────────────────────────────────────

export function useNotices(): Notice[] {
  return useDb((db) => db.notices);
}

export function useNotice(id: string | undefined): Notice | undefined {
  return useDb((db) => db.notices.find((n) => n.id === id));
}

export function createNotice(notice: Omit<Notice, 'id' | 'createdAt'>): string {
  const id = nextId('n');
  mutate((db) => ({
    notices: [{ ...notice, id, createdAt: new Date() }, ...db.notices],
  }));
  if (!isTestMode()) {
    void http.post('/notices', { ...notice, cohortId: apiCohortId() }).then(() => invalidateBootstrap());
  }
  return id;
}

export function updateNotice(id: string, patch: Partial<Notice>): void {
  mutate((db) => ({
    notices: db.notices.map((n) => (n.id === id ? { ...n, ...patch } : n)),
  }));
  if (!isTestMode() && isApiId(id)) {
    void http.patch(`/notices/${id}`, patch).then(() => invalidateBootstrap());
  }
}

export function deleteNotice(id: string): void {
  mutate((db) => ({ notices: db.notices.filter((n) => n.id !== id) }));
  if (!isTestMode() && isApiId(id)) {
    void http.delete(`/notices/${id}`).then(() => invalidateBootstrap());
  }
}

export function useScheduledNotices(): ScheduledNotice[] {
  return useDb((db) => db.scheduledNotices);
}

function patchScheduledLocal(notice: ScheduledNotice): ScheduledNotice {
  const saved = { ...notice, id: notice.id || nextId('sn') };
  mutate((db) => {
    const exists = db.scheduledNotices.some((n) => n.id === saved.id);
    return {
      scheduledNotices: exists
        ? db.scheduledNotices.map((n) => (n.id === saved.id ? saved : n))
        : [...db.scheduledNotices, saved],
    };
  });
  return saved;
}

export async function upsertScheduledNotice(notice: ScheduledNotice): Promise<ScheduledNotice> {
  if (isTestMode()) return patchScheduledLocal(notice);
  const existing = isApiId(notice.id);
  try {
    const { data } = existing
      ? await http.patch<{ id?: string }>(`/scheduled-notices/${notice.id}`, {
          title: notice.title,
          content: notice.content,
          isFavorite: notice.isFavorite,
          repeatType: notice.repeatType,
          publishTime: notice.publishTime,
          publishAt: notice.publishAt?.toISOString(),
          weekday: notice.weekday,
          isActive: notice.isActive,
          cohortId: apiCohortId(),
        })
      : await http.post<{ id?: string }>('/scheduled-notices', {
          title: notice.title,
          content: notice.content,
          isFavorite: notice.isFavorite,
          repeatType: notice.repeatType,
          publishTime: notice.publishTime,
          publishAt: notice.publishAt?.toISOString(),
          weekday: notice.weekday,
          isActive: notice.isActive,
          cohortId: apiCohortId(),
        });
    await invalidateBootstrap();
    return { ...notice, id: String(data.id ?? notice.id) };
  } catch (error) {
    throw new Error(await readApiError(error));
  }
}

export async function deleteScheduledNotice(id: string): Promise<void> {
  mutate((db) => ({
    scheduledNotices: db.scheduledNotices.filter((n) => n.id !== id),
  }));
  if (!isTestMode() && isApiId(id)) {
    try {
      await http.delete(`/scheduled-notices/${id}`);
      await invalidateBootstrap();
    } catch (error) {
      throw new Error(await readApiError(error));
    }
  }
}

export async function publishScheduledNotice(id: string): Promise<number> {
  if (isTestMode()) return 0;
  try {
    const { data } = await http.post<{ published?: number }>('/scheduled-notices/publish', { ids: [id] });
    await invalidateBootstrap();
    return Number(data.published ?? 0);
  } catch (error) {
    throw new Error(await readApiError(error));
  }
}

export function useAlertPopups(): AlertPopup[] {
  return useDb((db) => db.alertPopups);
}

function patchAlertLocal(popup: AlertPopup): AlertPopup {
  const saved = { ...popup, id: popup.id || nextId('ap') };
  mutate((db) => {
    const exists = db.alertPopups.some((p) => p.id === saved.id);
    return {
      alertPopups: exists
        ? db.alertPopups.map((p) => (p.id === saved.id ? saved : p))
        : [...db.alertPopups, saved],
    };
  });
  return saved;
}

export async function upsertAlertPopup(popup: AlertPopup): Promise<AlertPopup> {
  if (isTestMode()) return patchAlertLocal(popup);
  const existing = isApiId(popup.id);
  try {
    const body = {
      title: popup.title,
      content: popup.content,
      isActive: popup.isActive,
      sortOrder: popup.sortOrder,
      linkUrl: popup.linkUrl,
      startTime: popup.startTime,
      endTime: popup.endTime,
      cohortId: apiCohortId(),
    };
    const { data } = existing
      ? await http.patch<{ id?: string }>(`/alert-popups/${popup.id}`, body)
      : await http.post<{ id?: string }>('/alert-popups', body);
    await invalidateBootstrap();
    return { ...popup, id: String(data.id ?? popup.id) };
  } catch (error) {
    throw new Error(await readApiError(error));
  }
}

export async function deleteAlertPopup(id: string): Promise<void> {
  mutate((db) => ({ alertPopups: db.alertPopups.filter((p) => p.id !== id) }));
  if (!isTestMode() && isApiId(id)) {
    try {
      await http.delete(`/alert-popups/${id}`);
      await invalidateBootstrap();
    } catch (error) {
      throw new Error(await readApiError(error));
    }
  }
}

export function dismissAlertToday(uid: string, popupId: string): void {
  const dateKey = dateKeyOf(new Date());
  mutate((db) => ({
    alertDismissals: {
      ...db.alertDismissals,
      [uid]: { ...(db.alertDismissals[uid] ?? {}), [popupId]: dateKey },
    },
  }));
  if (!isTestMode() && isApiId(popupId)) {
    void http.post(`/alert-popups/${popupId}/dismiss`, { dateKey }).then(() => invalidateBootstrap());
  }
}

export function usePosts(): Post[] {
  return useDb((db) => db.posts);
}

export function createPost(authorId: string, authorName: string, content: string): void {
  mutate((db) => ({
    posts: [
      { id: nextId('p'), authorId, authorName, content, likeCount: 0, commentCount: 0, createdAt: new Date() },
      ...db.posts,
    ],
  }));
}

export function deletePost(id: string): void {
  mutate((db) => ({
    posts: db.posts.filter((p) => p.id !== id),
    postComments: db.postComments.filter((comment) => comment.postId !== id),
  }));
}

export function likePost(id: string): void {
  mutate((db) => ({
    posts: db.posts.map((p) => (p.id === id ? { ...p, likeCount: p.likeCount + 1 } : p)),
  }));
}

export function usePostComments(postId: string): PostComment[] {
  return useDb((db) => db.postComments.filter((comment) => comment.postId === postId));
}

export function createPostComment(
  postId: string,
  authorId: string,
  authorName: string,
  content: string,
): void {
  mutate((db) => ({
    postComments: [
      ...db.postComments,
      { id: nextId('pc'), postId, authorId, authorName, content, createdAt: new Date() },
    ],
    posts: db.posts.map((post) =>
      post.id === postId ? { ...post, commentCount: post.commentCount + 1 } : post,
    ),
  }));
}

export function deletePostComment(postId: string, commentId: string): void {
  mutate((db) => ({
    postComments: db.postComments.filter((comment) => comment.id !== commentId),
    posts: db.posts.map((post) =>
      post.id === postId
        ? { ...post, commentCount: Math.max(0, post.commentCount - 1) }
        : post,
    ),
  }));
}

// ── 할 일 ─────────────────────────────────────────────

export function useTodos(): Todo[] {
  return useDb((db) => db.todos);
}

export function addTodo(title: string): void {
  mutate((db) => ({
    todos: [{ id: nextId('t'), title, isCompleted: false, createdAt: new Date() }, ...db.todos],
  }));
  if (!isTestMode()) void runCommand('addTodo', { title });
}

export function toggleTodo(id: string): void {
  mutate((db) => ({
    todos: db.todos.map((t) => (t.id === id ? { ...t, isCompleted: !t.isCompleted } : t)),
  }));
  if (!isTestMode()) void runCommand('toggleTodo', { todoId: id });
}

export function deleteTodo(id: string): void {
  mutate((db) => ({ todos: db.todos.filter((t) => t.id !== id) }));
  if (!isTestMode()) void runCommand('deleteTodo', { todoId: id });
}

// ── 기록실 ────────────────────────────────────────────

export function useSubmissions(): Submission[] {
  return useDb((db) => db.submissions);
}

export function useMySubmissions(uid: string): Submission[] {
  return useDb((db) => db.submissions.filter((s) => s.userId === uid));
}

export function createSubmission(submission: Omit<Submission, 'id' | 'submittedAt'>): string {
  const id = nextId('sub');
  mutate((db) => ({
    submissions: [{ ...submission, id, submittedAt: new Date() }, ...db.submissions],
  }));
  if (!isTestMode()) {
    void runCommand('upsert', { table: 'record_submissions', action: 'insert', ...submission, cohortId: apiCohortId() });
  }
  return id;
}

export function reviewSubmission(
  id: string,
  status: SubmissionStatus,
  reviewComment?: string,
): void {
  mutate((db) => ({
    submissions: db.submissions.map((s) =>
      s.id === id
        ? { ...s, status, reviewComment, mileageGranted: status === 'approved' ? true : s.mileageGranted }
        : s,
    ),
  }));
}

// ── 출결 ──────────────────────────────────────────────

export function useAttendanceByDate(dateKey: string): Attendance[] {
  return useDb((db) => db.attendances.filter((a) => a.dateKey === dateKey));
}

export function useAttendanceOfUser(uid: string): Attendance[] {
  return useDb((db) => db.attendances.filter((a) => a.userId === uid));
}

export function setAttendanceStatus(
  userId: string,
  dateKey: string,
  status: Attendance['status'],
): void {
  mutate((db) => {
    const exists = db.attendances.some((a) => a.userId === userId && a.dateKey === dateKey);
    if (exists) {
      return {
        attendances: db.attendances.map((a) =>
          a.userId === userId && a.dateKey === dateKey
            ? { ...a, status, statusSource: 'manual' }
            : a,
        ),
      };
    }
    const user = db.users.find((u) => u.uid === userId);
    return {
      attendances: [
        ...db.attendances,
        {
          id: nextId('att'),
          userId,
          userDisplayName: user?.displayName,
          type: 'checkIn',
          dateKey,
          status,
          statusSource: 'manual',
        },
      ],
    };
  });
  if (!isTestMode()) {
    void runCommand('upsert', {
      table: 'attendances',
      action: 'insert',
      userId,
      dateKey,
      status,
      statusSource: 'manual',
      cohortId: apiCohortId(),
    });
  }
}

/**
 * 고용24 입퇴실 예시 채우기 — 관리자 출석 화면의 「예시 입실/퇴실 채우기」
 *
 * 실제 앱은 고용24에서 받아 온 시각을 넣는다. 프로토타입은 09:1x / 18:0x 안쪽에서
 * 사람마다 조금씩 다른 시각을 만들어 넣는다.
 */
function stampAttendance(userId: string, dateKey: string, patch: Partial<Attendance>): void {
  mutate((db) => {
    const exists = db.attendances.some((a) => a.userId === userId && a.dateKey === dateKey);
    if (exists) {
      return {
        attendances: db.attendances.map((a) =>
          a.userId === userId && a.dateKey === dateKey ? { ...a, ...patch } : a,
        ),
      };
    }
    const user = db.users.find((u) => u.uid === userId);
    return {
      attendances: [
        ...db.attendances,
        {
          id: nextId('att'),
          userId,
          userDisplayName: user?.displayName,
          type: 'checkIn',
          dateKey,
          ...patch,
        },
      ],
    };
  });
}

/** 사람마다 다르되 늘 같은 분(分)을 뽑는다 — 새로고침해도 시각이 흔들리지 않게. */
function minuteOf(userId: string, spread: number): string {
  let hash = 0;
  for (const ch of userId) hash = (hash * 31 + ch.charCodeAt(0)) % 997;
  return String(hash % spread).padStart(2, '0');
}

export function fillCheckIn(userId: string, dateKey: string): void {
  stampAttendance(userId, dateKey, { checkInTime: `09:${minuteOf(userId, 20)}` });
}

export function fillCheckOut(userId: string, dateKey: string): void {
  stampAttendance(userId, dateKey, { checkOutTime: `18:${minuteOf(userId, 15)}` });
}

// ── 자리 확인 ──────────────────────────────────────────

export function useSeating() {
  return useDb((db) => db.seating);
}

export function useSeatPresence(dateKey: string, period: number) {
  return useDb((db) =>
    db.seatPresence.filter((p) => p.dateKey === dateKey && p.period === period),
  );
}

export function setSeatPresence(
  dateKey: string,
  period: number,
  userId: string,
  state: SeatPresenceState,
): void {
  mutate((db) => {
    const rest = db.seatPresence.filter(
      (p) => !(p.dateKey === dateKey && p.period === period && p.userId === userId),
    );
    return { seatPresence: [...rest, { dateKey, period, userId, state }] };
  });
}

export function publishSeating(seats: { seatNumber: number; userId?: string; userDisplayName?: string }[]): void {
  mutate((db) => ({
    seating: {
      ...db.seating,
      updatedAt: new Date(),
      seats: db.seating.seats.map((s) => {
        const next = seats.find((n) => n.seatNumber === s.seatNumber);
        return next === undefined ? s : { ...s, userId: next.userId, userDisplayName: next.userDisplayName };
      }),
    },
  }));
  if (!isTestMode()) {
    const roomId = getDb().seating.id;
    if (roomId) void runCommand('publishSeating', { roomId, cohortId: apiCohortId() });
  }
}

// ── 이력서 ─────────────────────────────────────────────

export function useResumes(): Resume[] {
  return useDb((db) => db.resumes);
}

/** ⬇︎ Query 로 바꾼 것 — 나머지 훅은 아직 예전 모양이다 (시범) */
export function useMyResumes(uid: string): Query<Resume[]> {
  const data = useDb((db) => db.resumes.filter((r) => r.userId === uid));
  return { data, loading: false, error: null };
}

export function useResume(id: string | undefined): Resume | undefined {
  return useDb((db) => db.resumes.find((r) => r.id === id));
}

export function useResumeFeedbacks(resumeId: string): ResumeFeedback[] {
  return useDb((db) => db.resumeFeedbacks.filter((f) => f.resumeId === resumeId));
}

export function createResume(resume: Omit<Resume, 'id' | 'updatedAt'>): string {
  const id = nextId('r');
  mutate((db) => ({ resumes: [{ ...resume, id, updatedAt: new Date() }, ...db.resumes] }));
  if (!isTestMode()) {
    void runCommand('upsert', { table: 'resumes', action: 'insert', ...resume, cohortId: apiCohortId() });
  }
  return id;
}

export function updateResume(id: string, patch: Partial<Resume>): void {
  mutate((db) => ({
    resumes: db.resumes.map((r) => (r.id === id ? { ...r, ...patch, updatedAt: new Date() } : r)),
  }));
  if (!isTestMode()) void runCommand('upsert', { table: 'resumes', id, action: 'update', ...patch });
}

export function deleteResume(id: string): void {
  mutate((db) => ({ resumes: db.resumes.filter((r) => r.id !== id) }));
  if (!isTestMode()) void runCommand('upsert', { table: 'resumes', id, action: 'delete' });
}

export function addResumeFeedback(
  feedback: Omit<ResumeFeedback, 'id' | 'createdAt'>,
): void {
  mutate((db) => ({
    resumeFeedbacks: [...db.resumeFeedbacks, { ...feedback, id: nextId('fb'), createdAt: new Date() }],
    resumes: db.resumes.map((r) =>
      r.id === feedback.resumeId ? { ...r, feedbackCount: r.feedbackCount + 1 } : r,
    ),
  }));
}

// ── 성취도 평가 ────────────────────────────────────────

export function useAssessments(): Assessment[] {
  return useDb((db) => db.assessments);
}

export function useAssessment(id: string | undefined): Assessment | undefined {
  return useDb((db) => db.assessments.find((a) => a.id === id));
}

export function useAssessmentQuestions(assessmentId: string | undefined): AssessmentQuestion[] {
  return useDb((db) => (assessmentId === undefined ? [] : db.assessmentQuestions[assessmentId] ?? []));
}

export function useAssessmentSubmissions(assessmentId?: string): AssessmentSubmission[] {
  return useDb((db) =>
    assessmentId === undefined
      ? db.assessmentSubmissions
      : db.assessmentSubmissions.filter((s) => s.assessmentId === assessmentId),
  );
}

export function useMyAssessmentSubmission(
  assessmentId: string | undefined,
  uid: string,
): AssessmentSubmission | undefined {
  return useDb((db) =>
    db.assessmentSubmissions.find((s) => s.assessmentId === assessmentId && s.userId === uid),
  );
}

export function upsertAssessment(assessment: Assessment, questions: AssessmentQuestion[]): void {
  mutate((db) => {
    const exists = db.assessments.some((a) => a.id === assessment.id);
    return {
      assessments: exists
        ? db.assessments.map((a) => (a.id === assessment.id ? assessment : a))
        : [assessment, ...db.assessments],
      assessmentQuestions: { ...db.assessmentQuestions, [assessment.id]: questions },
    };
  });
}

export function deleteAssessment(id: string): void {
  mutate((db) => ({ assessments: db.assessments.filter((a) => a.id !== id) }));
}

export function setAssessmentPublished(id: string, published: boolean): void {
  mutate((db) => ({
    assessments: db.assessments.map((a) => (a.id === id ? { ...a, published } : a)),
  }));
}

/** 객관식·단답은 제출 즉시 자동 채점한다. Flutter도 같은 규칙이다. */
export function submitAssessment(
  assessment: Assessment,
  questions: AssessmentQuestion[],
  user: User,
  rawAnswers: Record<string, number | string | null>,
): AssessmentSubmission {
  const answers: Record<string, AssessmentAnswerEntry> = {};
  let total = 0;
  for (const q of questions) {
    const value = rawAnswers[q.id] ?? null;
    let correct = false;
    if (q.type === 'multipleChoice') {
      correct = typeof value === 'number' && value === q.correctIndex;
    } else {
      const text = String(value ?? '').trim().toLowerCase();
      correct = q.acceptedAnswers.some((a) => a.trim().toLowerCase() === text);
    }
    const score = correct ? q.points : 0;
    total += score;
    answers[q.id] = { value, autoScore: score, finalScore: score, isCorrect: correct };
  }
  const submission: AssessmentSubmission = {
    id: `${assessment.id}_${user.uid}`,
    assessmentId: assessment.id,
    userId: user.uid,
    userDisplayName: user.displayName,
    answers,
    autoTotalScore: total,
    totalScore: total,
    submittedAt: new Date(),
  };
  mutate((db) => ({
    assessmentSubmissions: [
      ...db.assessmentSubmissions.filter((s) => s.id !== submission.id),
      submission,
    ],
  }));
  return submission;
}

export function gradeAssessmentAnswer(
  submissionId: string,
  questionId: string,
  finalScore: number,
  comment?: string,
): void {
  mutate((db) => ({
    assessmentSubmissions: db.assessmentSubmissions.map((s) => {
      if (s.id !== submissionId) return s;
      const answers = {
        ...s.answers,
        [questionId]: { ...s.answers[questionId], finalScore, comment },
      };
      const totalScore = Object.values(answers).reduce((sum, a) => sum + (a.finalScore ?? 0), 0);
      return { ...s, answers, totalScore, gradedAt: new Date() };
    }),
  }));
}

// ── 학습실 · 커리큘럼 ──────────────────────────────────

export function useInflearnPackages() {
  return useDb((db) => db.inflearnPackages);
}

export function useYoutubeRecommendations() {
  return useDb((db) => db.youtubeRecommendations);
}

export function useStudySources() {
  return useDb((db) => db.studySources);
}

export function useStudyNotes() {
  return useDb((db) => db.studyNotes);
}

export function createDemoStudyNote(
  sourceId: string,
  scopeKey: string,
  files: { path: string; commit: string }[],
): string {
  const id = nextId('note');
  const label = scopeKey.replace(/^date:|^folder:|^files:/, '');
  mutate((db) => ({
    studyNotes: [
      ...db.studyNotes,
      {
        id,
        sourceId,
        status: 'done',
        scopeKey,
        reportMarkdown:
          `## ${label} 수업 요약\n\n- 선택한 범위의 핵심 개념을 정리했습니다.\n- 예제 코드를 다시 실행하며 흐름을 확인해 보세요.\n- 실제 내용 생성은 공부방 API 연결 후 저장소 자료를 기반으로 제공됩니다.`,
        reviewMarkdown:
          `## 복습 문제\n\n1. ${label}에서 가장 중요한 개념을 한 문장으로 설명해 보세요.\n2. 실습 코드를 다른 입력값으로 바꾸면 결과가 어떻게 달라지는지 확인해 보세요.`,
        files,
        createdAt: new Date(),
      },
    ],
  }));
  return id;
}

export function useCurriculumSheets() {
  return useDb((db) => db.curriculumSheets);
}

export function upsertInflearnPackage(pkg: import('../domain/types').InflearnPackage): void {
  mutate((db) => {
    const exists = db.inflearnPackages.some((p) => p.id === pkg.id);
    return {
      inflearnPackages: exists
        ? db.inflearnPackages.map((p) => (p.id === pkg.id ? pkg : p))
        : [...db.inflearnPackages, { ...pkg, id: pkg.id || nextId('pkg') }],
    };
  });
}

export function deleteInflearnPackage(id: string): void {
  mutate((db) => ({ inflearnPackages: db.inflearnPackages.filter((p) => p.id !== id) }));
}

export function replaceCurriculumSheet(sheet: import('../domain/types').CurriculumSheet): void {
  mutate(() => ({ curriculumSheets: [sheet] }));
}

// ── 설문 · 제출 ────────────────────────────────────────

export function useFormTasks(): FormTask[] {
  return useDb((db) => db.formTasks);
}

export function useFormResponses(taskId?: string) {
  return useDb((db) =>
    taskId === undefined ? db.formResponses : db.formResponses.filter((r) => r.taskId === taskId),
  );
}

export function upsertFormTask(task: FormTask): void {
  mutate((db) => {
    const exists = db.formTasks.some((t) => t.id === task.id);
    return {
      formTasks: exists
        ? db.formTasks.map((t) => (t.id === task.id ? task : t))
        : [{ ...task, id: task.id || nextId('form') }, ...db.formTasks],
    };
  });
}

export function deleteFormTask(id: string): void {
  mutate((db) => ({ formTasks: db.formTasks.filter((t) => t.id !== id) }));
}

export function markFormResponded(taskId: string, user: User): void {
  mutate((db) => ({
    formResponses: [
      ...db.formResponses.filter((r) => !(r.taskId === taskId && r.userId === user.uid)),
      {
        id: nextId('fr'),
        taskId,
        userId: user.uid,
        userEmail: user.personalEmail ?? user.email,
        userDisplayName: user.displayName,
        source: 'manual',
        submittedAt: new Date(),
      },
    ],
    formTasks: db.formTasks.map((t) =>
      t.id === taskId ? { ...t, responseCount: t.responseCount + 1 } : t,
    ),
  }));
}

// ── 마일리지 ───────────────────────────────────────────

export function useMileageProducts(): MileageProduct[] {
  return useDb((db) => db.mileageProducts);
}

export function useMileageTransactions(uid?: string): MileageTransaction[] {
  return useDb((db) =>
    uid === undefined ? db.mileageTransactions : db.mileageTransactions.filter((t) => t.userId === uid),
  );
}

export function usePurchaseRequests(uid?: string): PurchaseRequest[] {
  return useDb((db) =>
    uid === undefined ? db.purchaseRequests : db.purchaseRequests.filter((r) => r.userId === uid),
  );
}

export function useMileageSettings() {
  return useDb((db) => db.mileageSettings);
}

export function upsertMileageProduct(product: MileageProduct): void {
  mutate((db) => {
    const exists = db.mileageProducts.some((p) => p.id === product.id);
    return {
      mileageProducts: exists
        ? db.mileageProducts.map((p) => (p.id === product.id ? product : p))
        : [...db.mileageProducts, { ...product, id: product.id || nextId('mp') }],
    };
  });
}

export function deleteMileageProduct(id: string): void {
  mutate((db) => ({ mileageProducts: db.mileageProducts.filter((p) => p.id !== id) }));
}

export function createPurchaseRequest(request: Omit<PurchaseRequest, 'id' | 'createdAt'>): string {
  const id = nextId('pr');
  mutate((db) => ({
    purchaseRequests: [{ ...request, id, createdAt: new Date() }, ...db.purchaseRequests],
  }));
  return id;
}

/** 승인하면 잔액이 깎이고 사용 내역이 남는다. */
export function reviewPurchaseRequest(
  id: string,
  status: PurchaseRequest['status'],
  reviewComment?: string,
): void {
  mutate((db) => {
    const request = db.purchaseRequests.find((r) => r.id === id);
    if (request === undefined) return {};
    const approving = status === 'approved' && request.status !== 'approved';
    return {
      purchaseRequests: db.purchaseRequests.map((r) =>
        r.id === id ? { ...r, status, reviewComment } : r,
      ),
      users: approving
        ? db.users.map((u) =>
            u.uid === request.userId
              ? { ...u, mileageBalance: u.mileageBalance - request.totalAmount }
              : u,
          )
        : db.users,
      mileageTransactions: approving
        ? [
            {
              id: nextId('mt'),
              userId: request.userId,
              userDisplayName: request.userDisplayName,
              amount: -request.totalAmount,
              reason: `구매 승인 — ${request.items.map((i) => i.productName).join(', ')}`,
              type: 'redemption',
              relatedId: id,
              createdAt: new Date(),
            },
            ...db.mileageTransactions,
          ]
        : db.mileageTransactions,
    };
  });
}

export function adjustMileage(
  userId: string,
  amount: number,
  reason: string,
  adjustedBy: string,
): void {
  mutate((db) => {
    const user = db.users.find((u) => u.uid === userId);
    return {
      users: db.users.map((u) =>
        u.uid === userId ? { ...u, mileageBalance: u.mileageBalance + amount } : u,
      ),
      mileageTransactions: [
        {
          id: nextId('mt'),
          userId,
          userDisplayName: user?.displayName ?? '',
          amount,
          reason,
          type: 'admin_adjust',
          adjustedBy,
          createdAt: new Date(),
        },
        ...db.mileageTransactions,
      ],
    };
  });
  if (!isTestMode()) {
    void http.post('/mileage/adjust', { uid: userId, amount, reason }).then(() => invalidateBootstrap());
  }
}

export function updateMileageSettings(patch: Partial<import('../domain/types').MileageSettings>): void {
  mutate((db) => ({
    mileageSettings: { ...db.mileageSettings, ...patch, updatedAt: new Date() },
  }));
}

// ── 자격 시험 ──────────────────────────────────────────

/** ⬇︎ Query 로 바꾼 것 (시범) */
export function useQualExams(): Query<QualExamSchedule[]> {
  return { data: useDb((db) => db.qualExams), loading: false, error: null };
}
