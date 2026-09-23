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
  ProjectTeam,
  PublishedSeating,
  ScheduledNotice,
  SeatPresenceState,
  SeatingAssignment,
  SeatingGrid,
  SeatingRoom,
  Submission,
  SubmissionStatus,
  Todo,
  User,
  PracticeAttempt,
  PracticeReport,
  PracticeReportReason,
  PracticeReview,
  PracticeSet,
  StudyNote,
  StudyNoteScopeType,
} from '../domain/types';
import { getDb, mutate as mutateStore, nextId, subscribe, type Database } from './store';
import { dateKeyOf } from './seed';
import { buildScopeKey, scopeLabel } from '../features/study/noteScope';
import { resumeStatusToServer } from '../features/resume/resumeGroups';
import { remapAssignments } from '../domain/seatingLayout';
import { http, readApiError } from './http';
import { fetchBootstrap, lastBootstrapSession, mapStudyNote } from './bootstrap';
import { getBootstrapDb, subscribeBootstrap } from './bootstrapStore';
import { queryClient, queryKeys } from './queryClient';

function isTestMode(): boolean {
  return typeof import.meta !== 'undefined' && import.meta.env?.MODE === 'test';
}

/**
 * 쓰기 — 테스트(데모)는 메모리 저장소에, 실제 앱은 화면이 읽는 서버 스냅샷(bootstrap 캐시)에도 바로 반영한다.
 * 서버 저장(runCommand)이 끝나면 스냅샷을 다시 받아 서버 값으로 맞춘다. 그 사이에 화면이 옛 값으로
 * 되돌아가 보이지 않게 하려는 것이다(새 강의실이 만들자마자 사라져 보이던 문제).
 */
function mutate(change: (current: Database) => Partial<Database>): void {
  mutateStore(change);
  if (!isTestMode()) {
    queryClient.setQueryData<Database>(queryKeys.bootstrap, (prev) => (prev ? { ...prev, ...change(prev) } : prev));
  }
}

/** 지금 화면이 보는 데이터 — 쓰기 직후 서버로 보낼 값을 꺼낼 때 */
function currentDb(): Database {
  return isTestMode() ? getDb() : getBootstrapDb();
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

/** 학생 상담 내용 저장 — 열쇠가 학생이라 표 하나에 한 줄이다(student_intakes) */
export function saveStudentIntake(uid: string, intake: import('../domain/types').StudentIntake): void {
  if (!isTestMode()) void runCommand('saveStudentIntake', { uid, ...intake });
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
  if (!isTestMode()) void runCommand('reviewRecord', { id, status, reviewComment });
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
  if (!isTestMode()) {
    void runCommand('setSeatPresence', { dateKey, period, uid: userId, state, cohortId: apiCohortId() });
  }
}

// ── 좌석 배치 ──────────────────────────────────────────
// seating_repository.dart — 강의실(틀) · 강의실별 배치 · 확정 표시 · 프로젝트 팀

export function useSeatingRooms(cohortId: string): SeatingRoom[] {
  return useDb((db) =>
    db.seatingRooms
      .filter((r) => r.cohortId === cohortId)
      .sort((a, b) => (b.updatedAt?.getTime() ?? 0) - (a.updatedAt?.getTime() ?? 0)),
  );
}

export function useSeatingRoom(roomId: string | undefined): SeatingRoom | undefined {
  return useDb((db) => db.seatingRooms.find((r) => r.id === roomId));
}

export function useSeatingAssignment(roomId: string | undefined): SeatingAssignment | undefined {
  return useDb((db) => db.seatingAssignments.find((a) => a.roomId === roomId));
}

/** 학생·강사가 보는 확정 배치 */
export function usePublishedSeating(cohortId: string): PublishedSeating {
  return useDb((db) => {
    const roomId = db.seatingMeta[cohortId]?.publishedRoomId;
    const room = db.seatingRooms.find((r) => r.id === roomId);
    const assignment = db.seatingAssignments.find((a) => a.roomId === roomId);
    return { room, assignment, published: room !== undefined && assignment?.status === 'published' };
  });
}

export function createSeatingRoom(cohortId: string, grid: SeatingGrid, roomNumber?: string): string {
  const id = nextId('room');
  const now = new Date();
  mutate((db) => ({
    seatingRooms: [...db.seatingRooms, { ...grid, id, cohortId, roomNumber, createdAt: now, updatedAt: now }],
  }));
  if (!isTestMode()) {
    void runCommand('saveSeatingRoom', { roomId: id, cohortId, roomNumber, ...gridForServer(grid) });
  }
  return id;
}

/** 서버로 보낼 격자 — 빈 칸은 빼고, 강사석 · 출입문은 좌석 id 자리에 '행_열'(DB · Flutter 규칙) */
function gridForServer(grid: SeatingGrid) {
  return {
    rows: grid.rows,
    cols: grid.cols,
    cells: grid.cells
      .filter((c) => c.type !== 'empty')
      .map((c) => ({ ...c, seatId: c.seatId || `${c.row}_${c.col}` })),
  };
}

/**
 * 틀을 저장한다. 좌석 번호가 바뀌었을 수 있으니, 이미 있던 배치는 자리(행·열)를
 * 따라 옮겨 싣는다. 확정 여부는 건드리지 않는다.
 */
export function saveSeatingRoom(roomId: string, grid: SeatingGrid, roomNumber?: string): void {
  mutate((db) => {
    const old = db.seatingRooms.find((r) => r.id === roomId);
    if (old === undefined) return {};
    const next: SeatingRoom = { ...old, ...grid, roomNumber, updatedAt: new Date() };
    return {
      seatingRooms: db.seatingRooms.map((r) => (r.id === roomId ? next : r)),
      seatingAssignments: db.seatingAssignments.map((a) => {
        if (a.roomId !== roomId) return a;
        const assignments = remapAssignments(old, next, a.assignments);
        const seatNames = Object.fromEntries(
          Object.keys(assignments).flatMap((seatId) => {
            // 이름 사본은 옛 번호로 적혀 있다. 같은 학생의 옛 좌석을 찾아 옮긴다.
            const oldSeat = Object.keys(a.assignments).find((k) => a.assignments[k] === assignments[seatId]);
            const name = oldSeat === undefined ? undefined : a.seatNames[oldSeat];
            return name === undefined ? [] : [[seatId, name]];
          }),
        );
        return { ...a, assignments, seatNames };
      }),
    };
  });
  if (!isTestMode()) {
    // 좌석 번호가 바뀌었을 수 있으니 자리를 따라 옮긴 배치를 함께 보낸다
    const assignment = currentDb().seatingAssignments.find((a) => a.roomId === roomId);
    const room = currentDb().seatingRooms.find((r) => r.id === roomId);
    void runCommand('saveSeatingRoom', {
      roomId,
      cohortId: room?.cohortId ?? apiCohortId(),
      roomNumber,
      ...gridForServer(grid),
      assignments: assignment?.assignments ?? {},
    });
  }
}

/** 강의실과 그 배치를 지운다. 학생에게 보이던 강의실이면 확정 표시도 걷는다. */
export function deleteSeatingRoom(roomId: string): void {
  mutate((db) => ({
    seatingRooms: db.seatingRooms.filter((r) => r.id !== roomId),
    seatingAssignments: db.seatingAssignments.filter((a) => a.roomId !== roomId),
    seatingMeta: Object.fromEntries(
      Object.entries(db.seatingMeta).map(([cohortId, meta]) => [
        cohortId,
        meta.publishedRoomId === roomId ? {} : meta,
      ]),
    ),
  }));
  if (!isTestMode()) void runCommand('deleteSeatingRoom', { roomId });
}

function writeAssignment(
  db: Database,
  roomId: string,
  patch: Pick<SeatingAssignment, 'status' | 'assignments' | 'seatNames'> & { publishedAt?: Date },
): SeatingAssignment[] {
  const cohortId = db.seatingRooms.find((r) => r.id === roomId)?.cohortId ?? '';
  const prev = db.seatingAssignments.find((a) => a.roomId === roomId);
  // 통째로 갈아 끼운다. 합치면 비운·옮긴 좌석 키가 남아 이름이 겹친다.
  const next: SeatingAssignment = {
    roomId,
    cohortId,
    ...patch,
    publishedAt: patch.publishedAt ?? prev?.publishedAt,
    updatedAt: new Date(),
  };
  return prev === undefined
    ? [...db.seatingAssignments, next]
    : db.seatingAssignments.map((a) => (a.roomId === roomId ? next : a));
}

/** 임시 저장 — 원본처럼 상태는 「작성 중」으로 돌아간다. 학생 화면에서는 내려간다. */
export function saveSeatingDraft(
  roomId: string,
  assignments: Record<string, string>,
  seatNames: Record<string, string>,
): void {
  mutate((db) => ({
    seatingAssignments: writeAssignment(db, roomId, { status: 'draft', assignments, seatNames }),
  }));
  if (!isTestMode()) void runCommand('saveSeatingAssignments', { roomId, assignments, status: 'draft' });
}

/** 확정 — 이 강의실만 학생에게 보인다. 같은 기수의 다른 확정은 작성 중으로 내린다. */
export function publishSeatingAssignment(
  roomId: string,
  assignments: Record<string, string>,
  seatNames: Record<string, string>,
): void {
  mutate((db) => {
    const cohortId = db.seatingRooms.find((r) => r.id === roomId)?.cohortId ?? '';
    const lowered = db.seatingAssignments.map((a) =>
      a.cohortId === cohortId && a.roomId !== roomId && a.status === 'published'
        ? { ...a, status: 'draft' as const }
        : a,
    );
    return {
      seatingAssignments: writeAssignment({ ...db, seatingAssignments: lowered }, roomId, {
        status: 'published',
        assignments,
        seatNames,
        publishedAt: new Date(),
      }),
      seatingMeta: { ...db.seatingMeta, [cohortId]: { publishedRoomId: roomId } },
    };
  });
  // 서버도 좌석 배정을 저장하고, 같은 기수의 다른 확정은 작성 중으로 내린 뒤 이 강의실을 확정한다
  if (!isTestMode()) void runCommand('saveSeatingAssignments', { roomId, assignments, status: 'published' });
}

export function useProjectTeams(cohortId: string): ProjectTeam[] {
  return useDb((db) =>
    db.projectTeams
      .filter((t) => t.cohortId === cohortId)
      .sort((a, b) => a.sortOrder - b.sortOrder || a.name.localeCompare(b.name, 'ko')),
  );
}

export function createProjectTeam(cohortId: string, name: string, sortOrder: number, colorIndex: number): string {
  const id = nextId('team');
  mutate((db) => ({
    projectTeams: [
      ...db.projectTeams,
      { id, cohortId, name, memberIds: [], sortOrder, colorIndex, updatedAt: new Date() },
    ],
  }));
  saveTeams(cohortId, [id], []);
  return id;
}

/** 서버에 팀을 저장한다 — 바뀐 팀(ids)의 지금 값과 지운 팀(deleteIds) */
function saveTeams(cohortId: string, ids: string[], deleteIds: string[]): void {
  if (isTestMode()) return;
  const teams = currentDb().projectTeams.filter((t) => ids.includes(t.id));
  void runCommand('replaceProjectTeams', { cohortId, teams, deleteIds });
}

export function updateProjectTeam(team: ProjectTeam): void {
  mutate((db) => ({
    projectTeams: db.projectTeams.map((t) => (t.id === team.id ? { ...team, updatedAt: new Date() } : t)),
  }));
  saveTeams(team.cohortId, [team.id], []);
}

export function deleteProjectTeam(teamId: string): void {
  const cohortId = currentDb().projectTeams.find((t) => t.id === teamId)?.cohortId ?? apiCohortId();
  mutate((db) => ({ projectTeams: db.projectTeams.filter((t) => t.id !== teamId) }));
  saveTeams(cohortId, [], [teamId]);
}

/** 팀 구성을 한 번에 갈아 끼운다. `id`가 빈 팀은 새로 만든다. */
export function replaceProjectTeams(cohortId: string, upserts: ProjectTeam[], deleteIds: string[]): void {
  // 새 팀 id 는 여기서 한 번 정한다 — 화면 스냅샷과 서버(legacy_id)가 같은 id 를 쓰게
  const withIds = upserts.map((u) => (u.id === '' ? { ...u, id: nextId('team'), cohortId } : u));
  mutate((db) => {
    const now = new Date();
    const kept = db.projectTeams.filter((t) => !deleteIds.includes(t.id));
    const updated = kept.map((t) => {
      const u = withIds.find((x) => x.id === t.id);
      return u === undefined ? t : { ...u, updatedAt: now };
    });
    const created = withIds
      .filter((u) => !kept.some((t) => t.id === u.id))
      .map((u) => ({ ...u, updatedAt: now }));
    return { projectTeams: [...updated, ...created] };
  });
  saveTeams(cohortId, withIds.map((u) => u.id), deleteIds);
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

/** 서버로 보낼 이력서 값 — 상태는 DB 값(writing · submitted · approved)으로, 관계 칸은 뺀다 */
function resumeForServer(resume: Partial<Resume>): Record<string, unknown> {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { baseResumeId, sourceTailoredResumeId, linkedJobId, ...rest } = resume;
  return rest.status === undefined ? rest : { ...rest, status: resumeStatusToServer(rest.status) };
}

export function createResume(resume: Omit<Resume, 'id' | 'updatedAt'>): string {
  const id = nextId('r');
  mutate((db) => ({ resumes: [{ ...resume, id, updatedAt: new Date() }, ...db.resumes] }));
  if (!isTestMode()) {
    void runCommand('upsert', { table: 'resumes', action: 'insert', id, ...resumeForServer(resume), cohortId: apiCohortId() });
  }
  return id;
}

export function updateResume(id: string, patch: Partial<Resume>): void {
  mutate((db) => ({
    resumes: db.resumes.map((r) => (r.id === id ? { ...r, ...patch, updatedAt: new Date() } : r)),
  }));
  if (!isTestMode()) void runCommand('upsert', { table: 'resumes', id, action: 'update', ...resumeForServer(patch) });
}

/**
 * 기본 이력서 바꾸기 — Flutter setBaseResume. 한 사람에게 기본 이력서는 하나라 고른 것만 true 로 둔다.
 * 공고 추천 · AI 첨삭이 이 이력서를 바탕으로 쓴다.
 */
export function setBaseResume(userId: string, resumeId: string): void {
  const changed = currentDb().resumes.filter(
    (r) => r.userId === userId && r.isBaseResume !== (r.id === resumeId),
  );
  if (changed.length === 0) return;
  mutate((db) => ({
    resumes: db.resumes.map((r) =>
      r.userId === userId && r.isBaseResume !== (r.id === resumeId) ? { ...r, isBaseResume: r.id === resumeId } : r,
    ),
  }));
  if (isTestMode()) return;
  // 먼저 옛 기본을 내리고 새 것을 올린다 — 순서가 바뀌면 잠깐 기본이 둘이 된다
  const order = [...changed].sort((a, b) => Number(a.id === resumeId) - Number(b.id === resumeId));
  void (async () => {
    for (const r of order) {
      await runCommand('upsert', { table: 'resumes', id: r.id, action: 'update', isBaseResume: r.id === resumeId });
    }
  })();
}

export function deleteResume(id: string): void {
  mutate((db) => ({ resumes: db.resumes.filter((r) => r.id !== id) }));
  if (!isTestMode()) void runCommand('upsert', { table: 'resumes', id, action: 'delete' });
}

export function addResumeFeedback(
  feedback: Omit<ResumeFeedback, 'id' | 'createdAt'>,
): void {
  const id = nextId('fb');
  mutate((db) => ({
    resumeFeedbacks: [...db.resumeFeedbacks, { ...feedback, id, createdAt: new Date() }],
    resumes: db.resumes.map((r) =>
      r.id === feedback.resumeId ? { ...r, feedbackCount: r.feedbackCount + 1 } : r,
    ),
  }));
  if (!isTestMode()) {
    void runCommand('upsert', {
      table: 'resume_feedback',
      action: 'insert',
      id,
      resumeId: feedback.resumeId,
      parentId: feedback.parentId,
      sectionKey: feedback.sectionKey,
      content: feedback.content,
    });
  }
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
  if (!isTestMode()) {
    void runCommand('saveAssessment', {
      id: assessment.id,
      cohortId: apiCohortId(),
      title: assessment.title,
      tags: assessment.tags,
      maxScore: assessment.maxScore,
      startAt: assessment.startAt?.toISOString(),
      endAt: assessment.endAt?.toISOString(),
      thumbnailUrl: assessment.thumbnailUrl,
      published: assessment.published,
      questions,
    });
  }
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
  if (!isTestMode()) void runCommand('upsert', { table: 'assessments', id, action: 'delete' });
}

export function setAssessmentPublished(id: string, published: boolean): void {
  mutate((db) => ({
    assessments: db.assessments.map((a) => (a.id === id ? { ...a, published } : a)),
  }));
  if (!isTestMode()) void runCommand('upsert', { table: 'assessments', id, action: 'update', published });
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
  if (!isTestMode()) {
    void runCommand('submitAssessment', {
      id: submission.id,
      assessmentId: assessment.id,
      answers,
      autoTotalScore: total,
      totalScore: total,
    });
  }
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
  if (!isTestMode()) {
    void runCommand('gradeAssessmentAnswer', { submissionId, questionId, score: finalScore });
  }
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

/** 노트 범위를 고를 재료 — 저장소의 최근 수업 날짜와 분석할 수 있는 파일 */
export interface StudySourceTree {
  dates: string[];
  files: string[];
}

/** 테스트(데모)는 저장소를 못 읽으니 정해 둔 날짜와, 이미 있는 노트의 파일로 대신한다 */
const DEMO_DATES = ['2026-09-17', '2026-09-18', '2026-09-19'];

function demoFiles(sourceId: string): string[] {
  const notes = getDb().studyNotes.filter((n) => n.sourceId === sourceId);
  return [...new Set(notes.flatMap((n) => n.files.map((f) => f.path)))];
}

export async function fetchStudySourceTree(sourceId: string): Promise<StudySourceTree> {
  if (isTestMode()) return { dates: DEMO_DATES, files: demoFiles(sourceId) };
  const { data } = await http.post<{ dates?: string[]; entries?: { path: string }[] }>('/study-notes/tree', { sourceId });
  return { dates: data.dates ?? [], files: (data.entries ?? []).map((e) => e.path) };
}

function putStudyNote(note: StudyNote): StudyNote {
  mutate((db) => ({ studyNotes: [...db.studyNotes.filter((n) => n.id !== note.id), note] }));
  return note;
}

/**
 * 노트 만들기 — 서버가 수업 저장소를 읽어 AI 로 정리한다. 몇 분 걸려서 서버는 「정리 중」 노트를 먼저 돌려주고,
 * 화면은 refreshStudyNote 로 끝났는지 본다. 같은 범위의 노트가 이미 있으면 그것이 온다.
 */
export async function requestStudyNote(
  sourceId: string,
  scopeType: StudyNoteScopeType,
  scopeValue: string | string[],
): Promise<StudyNote> {
  if (isTestMode()) {
    const all = demoFiles(sourceId);
    const picked = Array.isArray(scopeValue) ? scopeValue : all.filter((p) => scopeType !== 'prefix' || p.startsWith(scopeValue));
    const id = createDemoStudyNote(sourceId, scopeType, scopeValue, picked.slice(0, 8).map((path) => ({ path, commit: 'demo-local' })));
    return getDb().studyNotes.find((n) => n.id === id)!;
  }
  const { data } = await http.post<Record<string, unknown>>('/study-notes', { sourceId, scopeType, scopeValue });
  return putStudyNote(mapStudyNote(data));
}

export async function refreshStudyNote(id: string): Promise<StudyNote> {
  if (isTestMode()) {
    const found = getDb().studyNotes.find((n) => n.id === id);
    if (!found) throw new Error('노트를 찾을 수 없습니다.');
    return found;
  }
  const { data } = await http.get<Record<string, unknown>>(`/study-notes/${encodeURIComponent(id)}`);
  return putStudyNote(mapStudyNote(data));
}

// ── 수업 저장소 관리 (강사 · 관리자) ─────────────────────────
// 기수에 GitHub 조직·강사 계정을 연결해 두면 서버가 저장소를 찾아 바로 공개로 올린다. 여기서는 연결과 숨기기만.

export interface GithubOwner {
  id: string;
  owner: string;
  lastSyncedAt: string | null;
  lastError: string;
}

export interface StudySourceSync {
  owners: GithubOwner[];
  /** 이번에 새로 올라간 저장소 이름 */
  added: string[];
  errors: { owner: string; error: string }[];
}

/** 테스트(데모)는 GitHub 에 못 나가니 연결만 기억한다 */
let demoOwners: GithubOwner[] = [];

export async function fetchGithubOwners(cohortId: string): Promise<GithubOwner[]> {
  if (isTestMode()) return demoOwners;
  const { data } = await http.get<{ owners: GithubOwner[] }>('/study-sources/github', { params: { cohortId } });
  return data.owners;
}

export async function syncStudySources(cohortId: string, force = false): Promise<StudySourceSync> {
  if (isTestMode()) return { owners: demoOwners, added: [], errors: [] };
  const { data } = await http.post<StudySourceSync>('/study-sources/sync', { cohortId, force });
  if (data.added.length) await invalidateBootstrap();
  return data;
}

export async function addGithubOwner(cohortId: string, owner: string): Promise<StudySourceSync> {
  if (isTestMode()) {
    demoOwners = [...demoOwners, { id: nextId('gh'), owner: owner.trim(), lastSyncedAt: new Date().toISOString(), lastError: '' }];
    return { owners: demoOwners, added: [], errors: [] };
  }
  const { data } = await http.post<StudySourceSync>('/study-sources/github', { cohortId, owner });
  if (data.added.length) await invalidateBootstrap();
  return data;
}

export async function removeGithubOwner(id: string): Promise<GithubOwner[]> {
  if (isTestMode()) {
    demoOwners = demoOwners.filter((o) => o.id !== id);
    return demoOwners;
  }
  const { data } = await http.delete<{ owners: GithubOwner[] }>(`/study-sources/github/${encodeURIComponent(id)}`);
  return data.owners;
}

/** 복습 문제 자동 출제(매일 18:30) — 마지막으로 돌린 결과 */
export interface PracticeAutoRun {
  status: 'running' | 'done' | 'failed';
  /** 이번에 새로 낸 문제 수 — 새 내용이 없으면 0 */
  problems: number;
  dates: string[];
  message: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface PracticeAutoStatus {
  /** practice 스키마가 있는지 — 없으면 출제해도 넣을 곳이 없다 */
  practiceReady: boolean;
  /** 저장소 id → 자동 출제 켜짐(기본 켜짐) · 마지막 출제 */
  sources: Record<string, { enabled: boolean; lastRun: PracticeAutoRun | null }>;
}

let demoPracticeAuto: PracticeAutoStatus['sources'] = {};

export async function fetchPracticeAuto(cohortId: string): Promise<PracticeAutoStatus> {
  if (isTestMode()) return { practiceReady: true, sources: demoPracticeAuto };
  const { data } = await http.get<PracticeAutoStatus>('/practice-auto', { params: { cohortId } });
  return data;
}

export async function setPracticeAuto(sourceId: string, enabled: boolean): Promise<void> {
  if (isTestMode()) {
    demoPracticeAuto = { ...demoPracticeAuto, [sourceId]: { lastRun: demoPracticeAuto[sourceId]?.lastRun ?? null, enabled } };
    return;
  }
  await http.patch(`/practice-auto/${encodeURIComponent(sourceId)}`, { enabled });
}

/**
 * 「지금 만들기」 — 고른 수업 날짜로(지난 과목도, 한 번에 5일까지). 날짜가 없으면 자동과 같은 규칙.
 * 서버는 바로 돌려주고 뒤에서 출제한다(몇 분). 끝났는지는 fetchPracticeAuto 로 본다
 */
export async function runPracticeNow(sourceId: string, dates: string[] = []): Promise<void> {
  if (isTestMode()) return;
  await http.post(`/practice-auto/${encodeURIComponent(sourceId)}/run`, { dates });
}

/** 새 복습 세트가 생겼을 때 — 강사 화면의 신고 · 세트 목록이 새 세트를 보게 */
export async function refreshAfterPractice(): Promise<void> {
  if (!isTestMode()) await invalidateBootstrap();
}

/** 공개 · 숨김. 숨긴 저장소는 학생 공부방에서 빠지고, 다시 찾아도 숨긴 채로 남는다 */
export async function setStudySourceActive(sourceId: string, isActive: boolean): Promise<void> {
  mutate((db) => ({ studySources: db.studySources.map((s) => (s.id === sourceId ? { ...s, isActive } : s)) }));
  if (isTestMode()) return;
  await http.patch(`/study-sources/${encodeURIComponent(sourceId)}`, { isActive });
  await invalidateBootstrap();
}

/** 내 노트 지우기. 같은 범위를 다시 고르면 새로 만든다 */
export async function deleteStudyNote(id: string): Promise<void> {
  if (!isTestMode()) await http.delete(`/study-notes/${encodeURIComponent(id)}`);
  mutate((db) => ({ studyNotes: db.studyNotes.filter((n) => n.id !== id) }));
}

function createDemoStudyNote(
  sourceId: string,
  scopeType: StudyNoteScopeType,
  scopeValue: string | string[],
  files: { path: string; commit: string }[],
): string {
  const id = nextId('note');
  const scopeKey = buildScopeKey(scopeType, scopeValue);
  const label = scopeLabel(scopeType, scopeValue);
  mutate((db) => ({
    studyNotes: [
      ...db.studyNotes,
      {
        id,
        sourceId,
        status: 'done',
        scopeType,
        scopeValue,
        scopeKey,
        reportMarkdown:
          `## ${label} 요약\n\n- 선택한 범위의 핵심 개념을 정리했습니다.\n- 예제 코드를 다시 실행하며 흐름을 확인해 보세요.\n- 실제 내용 생성은 공부방 API 연결 후 저장소 자료를 기반으로 제공됩니다.`,
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
  if (!isTestMode()) {
    void runCommand('upsert', {
      table: 'inflearn_packages',
      id: pkg.id || undefined,
      cohortId: apiCohortId(),
      title: pkg.title,
      subject: pkg.subject,
      type: pkg.type,
      summary: pkg.summary,
      units: pkg.units,
      courses: pkg.courses,
      isPublished: pkg.isPublished,
      sortOrder: pkg.sortOrder,
    });
  }
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
  if (!isTestMode()) void runCommand('upsert', { table: 'inflearn_packages', id, action: 'delete' });
}

export function replaceCurriculumSheet(sheet: import('../domain/types').CurriculumSheet): void {
  mutate(() => ({ curriculumSheets: [sheet] }));
  if (!isTestMode()) {
    void runCommand('replaceCurriculumSheet', {
      id: sheet.id,
      cohortId: apiCohortId(),
      title: sheet.title,
      fileName: sheet.fileName,
      rows: sheet.rows,
    });
  }
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
  if (!isTestMode()) {
    void runCommand('upsert', {
      table: 'form_tasks',
      id: task.id || undefined,
      cohortId: apiCohortId(),
      title: task.title,
      description: task.description,
      formUrl: task.formUrl,
      notionGuideUrl: task.notionGuideUrl,
      dueAt: task.dueAt?.toISOString(),
      published: task.published,
    });
  }
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
  if (!isTestMode()) void runCommand('upsert', { table: 'form_tasks', id, action: 'delete' });
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
  if (!isTestMode()) void runCommand('markFormResponded', { taskId, uid: user.uid, source: 'manual' });
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
  if (!isTestMode()) {
    void runCommand('upsert', {
      table: 'mileage_products',
      id: product.id || undefined,
      cohortId: apiCohortId(),
      name: product.name,
      description: product.description,
      imageUrl: product.imageUrl,
      category: product.category,
      pricingType: product.pricingType,
      fixedPrice: product.fixedPrice ?? null,
      isActive: product.isActive,
      sortOrder: product.sortOrder,
    });
  }
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
  if (!isTestMode()) void runCommand('upsert', { table: 'mileage_products', id, action: 'delete' });
}

export function createPurchaseRequest(request: Omit<PurchaseRequest, 'id' | 'createdAt'>): string {
  const id = nextId('pr');
  mutate((db) => ({
    purchaseRequests: [{ ...request, id, createdAt: new Date() }, ...db.purchaseRequests],
  }));
  if (!isTestMode()) {
    void runCommand('savePurchaseRequest', {
      id,
      cohortId: apiCohortId(),
      items: request.items,
      totalAmount: request.totalAmount,
      status: request.status,
    });
  }
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
  if (!isTestMode()) void runCommand('reviewPurchaseRequest', { id, status, managerMemo: reviewComment });
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
  if (isTestMode()) return;
  const next = currentDb().mileageSettings;
  void runCommand('saveMileageSettings', {
    cohortId: apiCohortId(),
    categoryLimits: next.categoryLimits,
    accrualRules: next.accrualRules,
  });
}

// ── 자격 시험 ──────────────────────────────────────────

/** ⬇︎ Query 로 바꾼 것 (시범) */
export function useQualExams(): Query<QualExamSchedule[]> {
  return { data: useDb((db) => db.qualExams), loading: false, error: null };
}

// ── 실습 문제 ──────────────────────────────────────────

/** 기수의 실습 세트 — 최근 수업이 위로 */
export function usePracticeSets(cohortId: string): PracticeSet[] {
  return useDb((db) =>
    db.practiceSets
      .filter((s) => s.cohortId === cohortId)
      .sort((a, b) => b.lessonDate.localeCompare(a.lessonDate)),
  );
}

export function usePracticeSet(id: string | null | undefined): PracticeSet | undefined {
  return useDb((db) => (id ? db.practiceSets.find((s) => s.id === id) : undefined));
}

export function useMyPracticeAttempts(uid: string): PracticeAttempt[] {
  return useDb((db) => db.practiceAttempts.filter((a) => a.uid === uid));
}

/** 채점 한 번을 남긴다. 한 번 통과하면 뒤에 틀려도 통과로 둔다. */
export function recordPracticeAttempt(uid: string, setId: string, index: number, passed: boolean): void {
  mutate((db) => {
    const found = db.practiceAttempts.find((a) => a.uid === uid && a.setId === setId && a.index === index);
    if (!found) {
      return {
        practiceAttempts: [
          ...db.practiceAttempts,
          { id: nextId('pa'), uid, setId, index, passed, tries: 1, answeredAt: new Date() },
        ],
      };
    }
    return {
      practiceAttempts: db.practiceAttempts.map((a) =>
        a === found ? { ...a, passed: a.passed || passed, tries: a.tries + 1, answeredAt: new Date() } : a,
      ),
    };
  });
  if (!isTestMode()) void runCommand('recordPracticeAttempt', { setId, index, passed });
}

// ── 복습 문제 신고 ────────────────────────────────────────

export function usePracticeReports(): PracticeReport[] {
  return useDb((db) => db.practiceReports);
}

export function usePracticeReviews(): PracticeReview[] {
  return useDb((db) => db.practiceReviews);
}

/** 한 문제에 한 사람 한 번. 이미 했으면 이유·메모만 바꾼다 */
export function reportPracticeProblem(uid: string, setId: string, index: number, reason: PracticeReportReason, note: string): void {
  mutate((db) => {
    const found = db.practiceReports.find((r) => r.uid === uid && r.setId === setId && r.index === index);
    if (found) {
      return { practiceReports: db.practiceReports.map((r) => (r === found ? { ...r, reason, note, createdAt: new Date() } : r)) };
    }
    return {
      practiceReports: [...db.practiceReports, { id: nextId('pr'), uid, setId, index, reason, note, createdAt: new Date() }],
    };
  });
  if (!isTestMode()) void runCommand('reportPracticeProblem', { setId, index, reason, note });
}

/** 강사 결정 — 숨김 유지 또는 다시 보이기 */
export function reviewPracticeProblem(decidedBy: string, setId: string, index: number, decision: PracticeReview['decision']): void {
  mutate((db) => ({
    practiceReviews: [
      ...db.practiceReviews.filter((r) => !(r.setId === setId && r.index === index)),
      { setId, index, decision, decidedBy, decidedAt: new Date() },
    ],
  }));
  if (!isTestMode()) void runCommand('reviewPracticeProblem', { setId, index, decision });
}
