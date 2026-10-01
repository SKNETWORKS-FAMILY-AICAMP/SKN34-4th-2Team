import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';

import type {
  AlertPopup,
  Assessment,
  AssessmentAnswerEntry,
  AssessmentQuestion,
  AssessmentSubmission,
  Attendance,
  AttendanceIssue,
  AttendanceRequestStatus,
  Cohort,
  CounselNote,
  FormAnswer,
  Quest,
  QuestSubmission,
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
  SpotCheck,
  SpotCheckItem,
  SpotCheckPeriod,
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
  WeeklyYoutube,
} from '../domain/types';
import { useQuery } from '@tanstack/react-query';
import { getDb, mutate as mutateStore, nextId, subscribe, type Database } from './store';
import { dateKeyOf } from './seed';
import { buildScopeKey, scopeLabel } from '../features/study/noteScope';
import {
  requestLabel,
  resultingStatus,
  type AttendanceRequestDraft,
} from '../features/attendance/attendanceRequest';
import { resumeStatusToServer } from '../features/resume/resumeGroups';
import { remapAssignments } from '../domain/seatingLayout';
import { http, readApiError } from './http';
import { fetchBootstrap, lastBootstrapSession, mapAlert, mapAttendanceIssue, mapStudyNote } from './bootstrap';
import { getBootstrapDb, subscribeBootstrap } from './bootstrapStore';
import { selectedCohortFor } from './cohortSelection';
import { queryClient, queryKeys } from './queryClient';
import { demoTutorAsk, demoTutorReset, demoTutorThread } from './tutorDemo';

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
  const session = lastBootstrapSession();
  // 관리자가 상단에서 고른 기수가 있으면 쓰기도 그 기수로(data/cohortSelection)
  return selectedCohortFor(session.uid) ?? session.cohortId;
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

/** 새 계정 · 재발급한 계정의 로그인 정보 — 비밀번호는 이때 한 번만 받는다(서버는 해시만 둔다) */
export interface AccountCredentials {
  uid: string;
  email: string;
  password: string;
}

/**
 * 학생 · 강사 계정 만들기 — 서버가 임시 비밀번호를 만들어 돌려준다(createStudentAccount).
 * 로그인 이메일을 비우면 서버가 만든다. 관리자 화면은 돌려받은 값을 복사 창으로 보여 준다.
 */
export async function createUser(user: User): Promise<AccountCredentials> {
  if (isTestMode()) {
    const email = user.email || `${user.uid}@playdata.co.kr`;
    mutate((db) => ({ users: [...db.users, { ...user, email }] }));
    return { uid: user.uid, email, password: 'demo-pass-1234' };
  }
  const result = await runCommand('createUser', { ...user });
  return { uid: String(result.uid), email: String(result.email), password: String(result.password) };
}

/** 비밀번호 재발급 — 새 임시 비밀번호를 받고, 그 계정은 다음 로그인에서 비밀번호를 바꾼다 */
export async function resetUserPassword(uid: string): Promise<AccountCredentials> {
  if (isTestMode()) {
    mutate((db) => ({ users: db.users.map((u) => (u.uid === uid ? { ...u, mustChangePassword: true } : u)) }));
    const email = currentDb().users.find((u) => u.uid === uid)?.email ?? '';
    return { uid, email, password: 'demo-pass-5678' };
  }
  const result = await runCommand('resetPassword', { uid });
  return { uid, email: String(result.email), password: String(result.password) };
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

export async function createNotice(notice: Omit<Notice, 'id' | 'createdAt'>): Promise<string> {
  const id = nextId('n');
  if (isTestMode()) {
    mutate((db) => ({ notices: [{ ...notice, id, createdAt: new Date() }, ...db.notices] }));
    return id;
  }
  try {
    const { data } = await http.post<{ id: string }>('/notices', { ...notice, cohortId: apiCohortId() });
    await invalidateBootstrap();
    return data.id;
  } catch (error) {
    throw new Error(await readApiError(error));
  }
}

export async function updateNotice(id: string, patch: Partial<Notice>): Promise<void> {
  if (isTestMode()) {
    mutate((db) => ({ notices: db.notices.map((n) => (n.id === id ? { ...n, ...patch } : n)) }));
    return;
  }
  if (isApiId(id)) {
    try {
      await http.patch(`/notices/${id}`, patch);
      await invalidateBootstrap();
    } catch (error) {
      throw new Error(await readApiError(error));
    }
  }
}

export async function uploadNoticeImage(file: File): Promise<{ key: string; url: string }> {
  if (isTestMode()) return { key: `demo/${file.name}`, url: `demo://${encodeURIComponent(file.name)}` };
  const form = new FormData();
  form.append('file', file);
  const { data } = await http.post<{ key: string; url: string }>('/uploads/notice-image', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
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
      endDate: popup.endDate ?? null,
      cohortId: apiCohortId(),
      // 없으면 서버가 대상을 그대로 둔다(노출 토글). 빈 목록이면 기수 전체로
      ...(popup.targetUserIds !== undefined ? { targetUserIds: popup.targetUserIds } : {}),
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

/** 노출 토글 — 누르는 즉시 화면에 반영하고, 저장이 실패하면 되돌린다 */
export async function setAlertPopupActive(popup: AlertPopup, isActive: boolean): Promise<void> {
  patchAlertLocal({ ...popup, isActive });
  if (isTestMode()) return;
  try {
    await upsertAlertPopup({ ...popup, isActive });
  } catch (error) {
    patchAlertLocal(popup);
    throw error;
  }
}

/** 예약 공지 동작 토글 — 알림 팝업 토글과 같은 방식 */
export async function setScheduledNoticeActive(notice: ScheduledNotice, isActive: boolean): Promise<void> {
  patchScheduledLocal({ ...notice, isActive });
  if (isTestMode()) return;
  try {
    await upsertScheduledNotice({ ...notice, isActive });
  } catch (error) {
    patchScheduledLocal(notice);
    throw error;
  }
}

/**
 * 학생 화면의 새 알림 · 출결 신청 처리 결과 확인 — 그것만 가볍게 다시 받는다(스냅샷 전체는 1MB 가 넘는다).
 * 서버가 학생 본인에게 보이는 켜진 알림과 본인 출결 신청만 준다.
 */
export async function refreshMyAlertPopups(): Promise<void> {
  if (isTestMode()) return;
  const { data } = await http.get<{
    alertPopups?: Record<string, unknown>[];
    dismissals?: Record<string, unknown>[];
    readPopupIds?: unknown[];
    attendanceIssues?: Record<string, unknown>[];
  }>('/alert-popups/mine');
  const uid = lastBootstrapSession().uid;
  const dismissed: Record<string, string> = {};
  for (const row of data.dismissals ?? []) {
    const popupId = String(row.popupId ?? row.popup_id ?? '');
    const dateKey = String(row.dateKey ?? row.date_key ?? '').slice(0, 10);
    if (popupId && dateKey) dismissed[popupId] = dateKey;
  }
  const popups = (data.alertPopups ?? []).map(mapAlert);
  queryClient.setQueryData<Database>(queryKeys.bootstrap, (prev) =>
    prev
      ? {
          ...prev,
          alertPopups: popups,
          alertDismissals: uid ? { ...prev.alertDismissals, [uid]: dismissed } : prev.alertDismissals,
          alertReadIds: data.readPopupIds ? data.readPopupIds.map(String) : prev.alertReadIds,
          attendanceIssues: data.attendanceIssues ? data.attendanceIssues.map(mapAttendanceIssue) : prev.attendanceIssues,
        }
      : prev,
  );
}

/** 학생이 알림을 확인했다 — 관리자 화면 「읽음 n/m」. 한 번만 보낸다 */
export function markAlertRead(popupId: string): void {
  if (currentDb().alertReadIds.includes(popupId)) return;
  mutate((db) => ({ alertReadIds: [...db.alertReadIds, popupId] }));
  if (!isTestMode() && isApiId(popupId)) {
    void http.post(`/alert-popups/${popupId}/read`).catch(() => undefined);
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
    void http.post(`/alert-popups/${popupId}/dismiss`, { dateKey }).catch(() => undefined);
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

/** 올린 증빙 한 장 — 서버가 준 저장 키와 지금 열 수 있는 주소 */
export interface UploadedEvidence {
  key: string;
  name: string;
  contentType: string;
  size: number;
  url: string;
}

/** 기록 증빙 올리기 — 이미지 · PDF, 10MB 까지. 제출할 때 돌려받은 키를 붙인다 */
export async function uploadRecordEvidence(file: File): Promise<UploadedEvidence> {
  if (isTestMode()) {
    return { key: `demo/${file.name}`, name: file.name, contentType: file.type, size: file.size, url: `demo://${encodeURIComponent(file.name)}` };
  }
  const form = new FormData();
  form.append('file', file);
  // 기본 머리말이 JSON 이라 여기서 바꾼다 — 경계(boundary)는 브라우저가 붙인다
  const { data } = await http.post<UploadedEvidence>('/uploads/record-evidence', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

/** 기록 제출 — 증빙은 먼저 uploadRecordEvidence 로 올린 것을 붙인다. 서버 저장이 끝나야 돌아온다 */
export async function createSubmission(
  submission: Omit<Submission, 'id' | 'submittedAt' | 'fileUrls'>,
  evidence: UploadedEvidence[] = [],
): Promise<string> {
  const fileUrls = evidence.map((f) => f.url);
  if (!isTestMode()) {
    const result = await runCommand('upsert', {
      table: 'record_submissions',
      action: 'insert',
      ...submission,
      files: evidence.map(({ key, name, contentType, size }) => ({ key, name, contentType, size })),
      cohortId: apiCohortId(),
    });
    return String(result.id);
  }
  const id = nextId('sub');
  mutate((db) => ({
    submissions: [{ ...submission, fileUrls, id, submittedAt: new Date() }, ...db.submissions],
  }));
  return id;
}

export function reviewSubmission(
  id: string,
  status: SubmissionStatus,
  reviewComment?: string,
  mileageAmount?: number,
): void {
  // 지급액은 서버가 규칙대로 정한다 — 승인 뒤 bootstrap 을 다시 받으면 채워진다
  mutate((db) => ({
    submissions: db.submissions.map((s) =>
      s.id === id
        ? {
            ...s,
            status,
            reviewComment,
            ...(status !== 'approved' ? { mileageGranted: false, mileageAmount: 0 } : {}),
          }
        : s,
    ),
  }));
  if (!isTestMode()) void runCommand('reviewRecord', { id, status, reviewComment, mileageAmount });
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

/** 자리 확인 저장 줄 — 연달아 눌러도 누른 차례대로 서버에 닿게 한다 */
let seatPresenceWrites: Promise<unknown> = Promise.resolve();

/**
 * 호명은 확인·보류를 빠르게 연달아 누른다. 화면에 먼저 반영하고 서버 저장은 뒤에서 차례로 보낸다.
 * 저장이 되면 캐시가 이미 같은 값이라 스냅샷을 다시 받지 않는다(받으면 누를 때마다 전체를 새로 읽는다).
 * 실패하면 스냅샷을 다시 받아 서버 값으로 되돌린다.
 */
export function setSeatPresence(
  dateKey: string,
  period: number,
  userId: string,
  state: SeatPresenceState,
): Promise<void> {
  mutate((db) => {
    const rest = db.seatPresence.filter(
      (p) => !(p.dateKey === dateKey && p.period === period && p.userId === userId),
    );
    return { seatPresence: [...rest, { dateKey, period, userId, state }] };
  });
  if (isTestMode()) return Promise.resolve();
  const request = seatPresenceWrites
    .catch(() => undefined)
    .then(() => http.post('/command', { op: 'setSeatPresence', payload: { dateKey, period, userId, state } }));
  seatPresenceWrites = request;
  return request.then(
    () => undefined,
    async (error: unknown) => {
      await invalidateBootstrap();
      throw error;
    },
  );
}

// ── 불시 자리 점검 ─────────────────────────────────────

export function useSpotChecks(cohortId: string): SpotCheck[] {
  return useDb((db) => db.spotChecks.filter((c) => c.cohortId === cohortId));
}

export interface SpotCheckDraft {
  id?: string;
  checkedAt: Date;
  period: SpotCheckPeriod;
  note?: string;
  items: SpotCheckItem[];
}

/** 점검 한 번을 통째로 저장한다 — id 가 있으면 그 점검을 고쳐 쓴다. 저장된 id 를 돌려준다. */
export async function saveSpotCheck(cohortId: string, draft: SpotCheckDraft, checker: User): Promise<string> {
  const local: SpotCheck = {
    id: draft.id ?? nextId('sc'),
    cohortId,
    checkedAt: draft.checkedAt,
    period: draft.period,
    note: draft.note,
    checkedBy: checker.uid,
    checkedByName: checker.displayName,
    items: draft.items,
  };
  if (isTestMode()) {
    mutate((db) => ({
      spotChecks: [local, ...db.spotChecks.filter((c) => c.id !== local.id)].sort(
        (a, b) => b.checkedAt.getTime() - a.checkedAt.getTime(),
      ),
    }));
    return local.id;
  }
  try {
    const data = await runCommand('savePresenceCheck', {
      id: draft.id !== undefined && isApiId(draft.id) ? draft.id : undefined,
      cohortId: apiCohortId(),
      checkedAt: draft.checkedAt.toISOString(),
      period: draft.period,
      note: draft.note,
      items: draft.items,
    });
    return String(data.id ?? local.id);
  } catch (error) {
    throw new Error(await readApiError(error));
  }
}

export async function deleteSpotCheck(id: string): Promise<void> {
  mutate((db) => ({ spotChecks: db.spotChecks.filter((c) => c.id !== id) }));
  if (isTestMode() || !isApiId(id)) return;
  try {
    await runCommand('deletePresenceCheck', { id });
  } catch (error) {
    await invalidateBootstrap();
    throw new Error(await readApiError(error));
  }
}

// ── 관리자 AI 어시스턴트 ───────────────────────────────

export type AssistantAction =
  | {
      id: string;
      type: 'send_alert';
      title: string;
      content: string;
      linkUrl?: string | null;
      /** 'YYYY-MM-DD' — 이 날까지 보인다. null 이면 끌 때까지 */
      endDate?: string | null;
      allStudents: boolean;
      targets: { uid: string; name: string }[];
      /** 서버가 서명한 제안 — 실행할 때 그대로 돌려준다. 대상은 빼기만 할 수 있다 */
      signature: string;
      /** 기수 전체 · 대량 발송을 관리자가 확인했는지 */
      confirmBulk?: boolean;
    }
  | { id: string; type: 'create_notice'; title: string; content: string; important: boolean; signature: string };

export interface AssistantTurn {
  role: 'user' | 'assistant';
  content: string;
}

/** 어시스턴트 확인 카드의 제목 · 내용 최대 글자 수 — 서버(admin_assistant.py)와 같다 */
export const ASSISTANT_MAX_TITLE_CHARS = 100;
export const ASSISTANT_MAX_CONTENT_CHARS = 2000;
/** 이 인원 이상이거나 기수 전체면 실행 전에 확인 체크를 받는다 — 서버와 같다 */
export const ASSISTANT_BULK_TARGETS = 30;

/**
 * 대화를 보내고 답과 확인 카드(제안)를 받는다. 제안은 executeAssistantAction 을 불러야 반영된다.
 * context 는 서버가 서명한 조회 결과 토큰 — 다음 질문 때 그대로 돌려줘야 '아까 그 학생들'이 통한다.
 */
export async function askAdminAssistant(
  messages: AssistantTurn[],
  context = '',
): Promise<{ reply: string; actions: AssistantAction[]; context: string }> {
  if (isTestMode()) return { reply: '테스트 모드에서는 AI 어시스턴트를 쓸 수 없습니다.', actions: [], context: '' };
  try {
    const { data } = await http.post<{ reply?: string; actions?: AssistantAction[]; context?: string }>(
      '/admin/assistant',
      { messages, context, cohortId: apiCohortId() },
    );
    return { reply: data.reply ?? '', actions: data.actions ?? [], context: data.context ?? '' };
  } catch (error) {
    throw new Error(await readApiError(error));
  }
}

export async function executeAssistantAction(action: AssistantAction): Promise<void> {
  if (isTestMode()) return;
  try {
    await http.post('/admin/assistant/execute', { action, cohortId: apiCohortId() });
    await invalidateBootstrap();
  } catch (error) {
    throw new Error(await readApiError(error));
  }
}

/** 출결 신청 — 날짜를 주면 그날 것만 */
export function useAttendanceIssues(dateKey?: string): AttendanceIssue[] {
  return useDb((db) =>
    dateKey === undefined ? db.attendanceIssues : db.attendanceIssues.filter((i) => i.dateKey === dateKey),
  );
}

// ── 출결 신청(예외 출결) ───────────────────────────────

export function useMyAttendanceRequests(uid: string): AttendanceIssue[] {
  return useDb((db) =>
    db.attendanceIssues
      .filter((i) => i.userId === uid)
      .sort((a, b) => b.dateKey.localeCompare(a.dateKey) || (b.submittedAt?.getTime() ?? 0) - (a.submittedAt?.getTime() ?? 0)),
  );
}

/** 학생 신청 · 고치기 — 증빙은 먼저 올리고 키를 붙인다. 반려된 것을 고치면 다시 확인 대기로 간다 */
export async function submitAttendanceRequest(
  draft: AttendanceRequestDraft,
  file: File | null,
  owner: User,
): Promise<string> {
  const evidence = file ? await uploadRecordEvidence(file) : undefined;
  if (isTestMode()) {
    const id = draft.id ?? nextId('ar');
    const previous = getDb().attendanceIssues.find((i) => i.id === id);
    const keepEvidence = evidence === undefined && draft.removeEvidence !== true;
    const saved: AttendanceIssue = {
      id,
      userId: owner.uid,
      dateKey: draft.dateKey,
      issueType: draft.issueType,
      status: 'submitted',
      reason: draft.reason.trim(),
      timeFrom: draft.timeFrom,
      timeTo: draft.timeTo,
      officialLeaveUsed: draft.officialLeaveUsed,
      officialLeaveType: draft.officialLeaveUsed ? draft.officialLeaveType : undefined,
      officialLeaveOther: draft.officialLeaveUsed ? draft.officialLeaveOther : undefined,
      evidenceName: evidence?.name ?? (keepEvidence ? previous?.evidenceName : undefined),
      evidenceUrl: evidence?.url ?? (keepEvidence ? previous?.evidenceUrl : undefined),
      submittedAt: previous?.submittedAt ?? new Date(),
    };
    saved.label = requestLabel(saved);
    mutate((db) => ({ attendanceIssues: [saved, ...db.attendanceIssues.filter((i) => i.id !== id)] }));
    return id;
  }
  try {
    const data = await runCommand('submitAttendanceRequest', {
      ...draft,
      id: draft.id !== undefined && isApiId(draft.id) ? draft.id : undefined,
      evidence: evidence && { key: evidence.key, name: evidence.name, contentType: evidence.contentType, size: evidence.size },
    });
    return String(data.id ?? '');
  } catch (error) {
    throw new Error(await readApiError(error));
  }
}

/**
 * 테스트 모드 출석부 반영 — 서버(attendance_requests.py)와 같은 규칙.
 * 신청이 처음 덮어쓸 때 원래 상태를 기억했다가, 승인이 모두 빠지면 되돌린다.
 */
const attendanceBeforeRequests = new Map<string, Pick<Attendance, 'status' | 'statusSource'> | null>();

function attendanceOf(userId: string, dateKey: string): Attendance | undefined {
  return getDb().attendances.find((a) => a.userId === userId && a.dateKey === dateKey);
}

function syncLocalAttendance(userId: string, dateKey: string): void {
  const approved = getDb().attendanceIssues.filter(
    (i) => i.userId === userId && i.dateKey === dateKey && i.status === 'approved',
  );
  const key = `${userId}|${dateKey}`;
  const current = attendanceOf(userId, dateKey);
  const status = resultingStatus(approved);
  if (status !== undefined) {
    if (current?.statusSource !== 'form') {
      attendanceBeforeRequests.set(key, current ? { status: current.status, statusSource: current.statusSource } : null);
    }
    stampAttendance(userId, dateKey, { status, statusSource: 'form' });
    return;
  }
  if (current?.statusSource !== 'form') return;
  const before = attendanceBeforeRequests.get(key) ?? null;
  attendanceBeforeRequests.delete(key);
  stampAttendance(userId, dateKey, { status: before?.status, statusSource: before?.statusSource });
}

export async function cancelAttendanceRequest(id: string): Promise<void> {
  const before = currentDb().attendanceIssues;
  const target = before.find((i) => i.id === id);
  mutate((db) => ({ attendanceIssues: db.attendanceIssues.filter((i) => i.id !== id) }));
  if (isTestMode()) {
    if (target?.status === 'approved') syncLocalAttendance(target.userId, target.dateKey);
    return;
  }
  if (!isApiId(id)) return;
  try {
    await runCommand('cancelAttendanceRequest', { id });
  } catch (error) {
    mutate(() => ({ attendanceIssues: before }));
    throw new Error(await readApiError(error));
  }
}

/** 승인 · 반려(여러 건) — 승인하면 그날 출석부 상태도 바꾸고, 승인을 거두면 원래대로 돌린다 */
export async function reviewAttendanceRequests(
  ids: string[],
  decision: AttendanceRequestStatus,
  reviewer: User,
  comment?: string,
): Promise<void> {
  const picked = new Set(ids);
  const now = new Date();
  const changedDays = new Set(
    currentDb()
      .attendanceIssues.filter((i) => picked.has(i.id) && (decision === 'approved' || i.status === 'approved'))
      .map((i) => `${i.userId}|${i.dateKey}`),
  );
  mutate((db) => ({
    attendanceIssues: db.attendanceIssues.map((i) =>
      picked.has(i.id)
        ? {
            ...i,
            status: decision,
            reviewComment: comment?.trim() || undefined,
            reviewedBy: decision === 'submitted' ? undefined : reviewer.uid,
            reviewedAt: decision === 'submitted' ? undefined : now,
          }
        : i,
    ),
  }));
  if (isTestMode()) {
    changedDays.forEach((day) => {
      const [userId, dateKey] = day.split('|');
      syncLocalAttendance(userId, dateKey);
    });
    return;
  }
  const apiIds = ids.filter(isApiId);
  if (apiIds.length === 0) return;
  try {
    await runCommand('reviewAttendanceRequest', { ids: apiIds, decision, comment });
  } catch (error) {
    await invalidateBootstrap();
    throw new Error(await readApiError(error));
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

export async function createResume(resume: Omit<Resume, 'id' | 'updatedAt'>): Promise<string> {
  if (!isTestMode()) {
    const result = await runCommand('upsert', {
      table: 'resumes', action: 'insert', ...resumeForServer(resume), cohortId: apiCohortId(),
    });
    return String(result.id);
  }
  const id = nextId('r');
  mutate((db) => ({ resumes: [{ ...resume, id, updatedAt: new Date() }, ...db.resumes] }));
  return id;
}

const pendingResumeWrites = new Map<string, Promise<unknown>>();

export function updateResume(id: string, patch: Partial<Resume>): Promise<void> {
  const update = (db: Database): Database => ({
    ...db,
    resumes: db.resumes.map((r) => (r.id === id ? { ...r, ...patch, updatedAt: new Date() } : r)),
  });
  if (isTestMode()) {
    mutate((db) => ({ resumes: update(db).resumes }));
    return Promise.resolve();
  }
  queryClient.setQueryData<Database>(queryKeys.bootstrap, (db) => db && update(db));
  const previous = pendingResumeWrites.get(id) ?? Promise.resolve();
  const request = previous.catch(() => undefined).then(async () => {
    await runCommand('upsert', { table: 'resumes', id, action: 'update', ...resumeForServer(patch) });
  });
  pendingResumeWrites.set(id, request);
  void request.finally(() => {
    if (pendingResumeWrites.get(id) === request) pendingResumeWrites.delete(id);
  }).catch(() => undefined);
  return request;
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

/** 단답 비교 — 앞뒤 공백을 지우고 소문자, 가운데 공백은 하나로(서버 normalize_short_answer 와 같다) */
const normalizeShortAnswer = (value: unknown) => String(value ?? '').trim().toLowerCase().replace(/\s+/g, ' ');

/** 데모(테스트)만 화면에서 채점한다. 실제 앱은 서버가 채점한다 — 화면이 정답을 가지고 있지 않다. */
function gradeLocally(
  questions: AssessmentQuestion[],
  rawAnswers: Record<string, number | string | null>,
): { answers: Record<string, AssessmentAnswerEntry>; total: number } {
  const answers: Record<string, AssessmentAnswerEntry> = {};
  let total = 0;
  for (const q of questions) {
    const value = rawAnswers[q.id] ?? null;
    const correct =
      q.type === 'multipleChoice'
        ? typeof value === 'number' && value === q.correctIndex
        : normalizeShortAnswer(value) !== '' &&
          q.acceptedAnswers.some((a) => normalizeShortAnswer(a) === normalizeShortAnswer(value));
    const score = correct ? q.points : 0;
    total += score;
    answers[q.id] = { value, autoScore: score, finalScore: score, isCorrect: correct };
  }
  return { answers, total };
}

/** 응시할 문항 — 정답 · 해설이 빠진 시험지(getAssessmentForTake). 공개 · 기간 · 이미 냈는지는 서버가 본다. */
export async function fetchAssessmentForTake(assessmentId: string): Promise<AssessmentQuestion[]> {
  if (isTestMode()) return getDb().assessmentQuestions[assessmentId] ?? [];
  const { data } = await http.get<{ questions: AssessmentQuestion[] }>(
    `/assessments/${encodeURIComponent(assessmentId)}/take`,
  );
  return data.questions.map((q) => ({ ...q, acceptedAnswers: [] }));
}

export interface AssessmentReview {
  questions: AssessmentQuestion[];
  submission: AssessmentSubmission;
}

/** 결과 — 정답 · 해설과 내 답(getAssessmentReview). 낸 뒤에만 온다. */
export async function fetchAssessmentReview(assessmentId: string, user: User): Promise<AssessmentReview | null> {
  if (isTestMode()) {
    const db = getDb();
    const submission = db.assessmentSubmissions.find((s) => s.assessmentId === assessmentId && s.userId === user.uid);
    return submission === undefined ? null : { questions: db.assessmentQuestions[assessmentId] ?? [], submission };
  }
  const { data } = await http.get<{
    questions: (AssessmentQuestion & { correctIndex: number | null; explanation: string | null })[];
    submission: { id: string; totalScore: number; autoTotalScore: number; submittedAt: string | null; answers: Record<string, AssessmentAnswerEntry> };
  }>(`/assessments/${encodeURIComponent(assessmentId)}/review`);
  return {
    questions: data.questions.map((q) => ({
      ...q,
      correctIndex: q.correctIndex ?? undefined,
      explanation: q.explanation ?? undefined,
      sourceDay: q.sourceDay ?? undefined,
      sourceTopic: q.sourceTopic ?? undefined,
    })),
    submission: {
      id: data.submission.id,
      assessmentId,
      userId: user.uid,
      userDisplayName: user.displayName,
      answers: data.submission.answers,
      autoTotalScore: data.submission.autoTotalScore,
      totalScore: data.submission.totalScore,
      submittedAt: data.submission.submittedAt ? new Date(data.submission.submittedAt) : undefined,
    },
  };
}

/**
 * 제출 — 답만 보낸다. 점수는 서버가 매겨 돌려준다(submitAssessment). 한 사람 한 번, 응시 기간 안에서만.
 * 실패(기간 끝남 · 이미 냄)하면 그 이유로 throw 한다.
 */
export async function submitAssessment(
  assessment: Assessment,
  questions: AssessmentQuestion[],
  user: User,
  rawAnswers: Record<string, number | string | null>,
): Promise<AssessmentSubmission> {
  let answers: Record<string, AssessmentAnswerEntry>;
  let total: number;
  let id = `${assessment.id}_${user.uid}`;
  if (isTestMode()) {
    ({ answers, total } = gradeLocally(questions, rawAnswers));
  } else {
    const result = await runCommand('submitAssessment', { assessmentId: assessment.id, answers: rawAnswers });
    answers = (result.answers ?? {}) as Record<string, AssessmentAnswerEntry>;
    total = Number(result.totalScore ?? 0);
    id = String(result.id ?? id);
  }
  const submission: AssessmentSubmission = {
    id,
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

/** 수업 파일 하나의 원문 — 노트의 「연습장에서 열기」. 노트를 만든 커밋 그대로 읽는다 */
export async function fetchLessonFile(sourceId: string, path: string, commit: string): Promise<{ path: string; commit: string; text: string }> {
  if (isTestMode()) throw new Error('데모에서는 수업 파일을 열 수 없어요.');
  const { data } = await http.post<{ path: string; commit: string; text: string }>('/study-notes/file', { sourceId, path, commit });
  return data;
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

/** 이번 주 커리큘럼 YouTube 추천. 서버가 12시간 캐시하므로 화면을 열 때마다 불러도 된다. force 는 강사·관리자만 */
export async function fetchWeeklyYoutube(cohortId: string, force = false): Promise<WeeklyYoutube> {
  if (isTestMode()) {
    return { cohortId, weekKey: null, weekLabel: null, topics: [], videos: [], cached: false, fetchedAt: null, message: null };
  }
  const { data } = await http.get<WeeklyYoutube>('/study/youtube-weekly', { params: { cohortId, force } });
  return data;
}

export function useWeeklyYoutube(cohortId: string) {
  return useQuery({
    queryKey: ['youtube-weekly', cohortId],
    queryFn: () => fetchWeeklyYoutube(cohortId),
    enabled: !isTestMode() && cohortId !== '',
    staleTime: 30 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
}

// ── 정기 상담 (관리자 전용 · bootstrap 밖) ───────────────────────

export type CounselNoteDraft = Pick<
  CounselNote,
  'round' | 'counseledOn' | 'category' | 'content' | 'followUp' | 'followUpDone' | 'nextOn'
>;

const counselKey = ['counsel-notes'] as const;

/** 한 학생의 상담 기록 전체(내용 포함) */
export function useStudentCounselNotes(uid: string | undefined) {
  return useQuery({
    queryKey: [...counselKey, 'student', uid],
    queryFn: async () =>
      (await http.get<{ notes: CounselNote[] }>('/counsel-notes', { params: { student: uid } })).data.notes,
    enabled: !isTestMode() && !!uid,
  });
}

/** 기수 전체 상담 요약(내용 제외) — 상담 현황 화면 */
export function useCohortCounselNotes(cohortId: string) {
  return useQuery({
    queryKey: [...counselKey, 'cohort', cohortId],
    queryFn: async () =>
      (await http.get<{ notes: CounselNote[] }>('/counsel-notes', { params: { cohort: cohortId } })).data.notes,
    enabled: !isTestMode() && cohortId !== '',
  });
}

async function refreshCounsel(): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: counselKey });
}

export async function createCounselNote(uid: string, draft: CounselNoteDraft): Promise<void> {
  await http.post('/counsel-notes', { uid, ...draft });
  await refreshCounsel();
}

export async function updateCounselNote(id: string, change: Partial<CounselNoteDraft>): Promise<void> {
  await http.patch(`/counsel-notes/${id}`, change);
  await refreshCounsel();
}

export async function deleteCounselNote(id: string): Promise<void> {
  await http.delete(`/counsel-notes/${id}`);
  await refreshCounsel();
}

// ── 마일리지 퀘스트 (bootstrap 밖) ───────────────────────────

export type QuestDraft = Pick<
  Quest,
  'title' | 'description' | 'reward' | 'evidenceType' | 'approval' | 'maxCompletions' | 'startOn' | 'endOn' | 'published' | 'closed'
>;

const questKey = ['quests'] as const;

/** 관리자: 기수 퀘스트 + 제출 수. 학생: 공개 퀘스트 + 내 제출 */
export function useQuests(cohortId: string) {
  return useQuery({
    queryKey: [...questKey, 'list', cohortId],
    queryFn: async () =>
      (await http.get<{ quests: Quest[]; submissions?: QuestSubmission[] }>('/quests', { params: { cohort: cohortId } }))
        .data,
    enabled: !isTestMode() && cohortId !== '',
  });
}

export function useQuestSubmissions(cohortId: string, status: string) {
  return useQuery({
    queryKey: [...questKey, 'submissions', cohortId, status],
    queryFn: async () =>
      (
        await http.get<{ submissions: QuestSubmission[] }>('/quest-submissions', {
          params: { cohort: cohortId, status },
        })
      ).data.submissions,
    enabled: !isTestMode() && cohortId !== '',
  });
}

/** 지급 · 회수가 일어나면 잔액 · 마일리지 내역(bootstrap)도 다시 받는다 */
async function refreshQuests(mileageChanged: boolean): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: questKey });
  if (mileageChanged) await invalidateBootstrap();
}

export async function createQuest(cohortId: string, draft: QuestDraft): Promise<void> {
  await http.post('/quests', { cohortId, ...draft });
  await refreshQuests(false);
}

export async function updateQuest(id: string, change: Partial<QuestDraft>): Promise<void> {
  await http.patch(`/quests/${id}`, change);
  await refreshQuests(false);
}

export async function submitQuest(
  id: string,
  evidence: { text?: string; link?: string; fileKeys?: string[] },
): Promise<QuestSubmission> {
  const { data } = await http.post<{ submission: QuestSubmission }>(`/quests/${id}/submit`, evidence);
  await refreshQuests(data.submission.grantedAmount > 0);
  return data.submission;
}

export async function reviewQuestSubmission(
  id: string,
  decision: 'approve' | 'reject' | 'revoke',
  comment = '',
): Promise<void> {
  await http.post(`/quest-submissions/${id}/review`, { decision, comment });
  await refreshQuests(decision !== 'reject');
}

/** 관리자 — 공공데이터포털에서 시험 일정을 지금 다시 받는다 */
export async function syncQualExams(): Promise<Record<string, number>> {
  if (isTestMode()) return {};
  const { data } = await http.post<{ counts: Record<string, number> }>('/qual-exams/sync', {});
  await invalidateBootstrap();
  return data.counts;
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

/** 웹 실습 채점 결과 — 검사문마다 통과 여부. error 는 채점 자체를 못 했을 때(문법 · 서버) */
export interface WebGrade {
  passed: boolean;
  checks: { message: string; ok: boolean }[];
  error: string;
}

/**
 * 웹 실습(web_task) 채점 — 서버의 jsdom 이 그 문제의 검사문(DB)으로 본다. 검사문은 브라우저에 없다.
 * setId · index 는 원래 세트의 문제 자리(다시 풀 문제도 원래 자리 — usePracticeSetMode.originOf)
 */
export async function gradeWebProblem(setId: string, index: number, html: string): Promise<WebGrade> {
  if (isTestMode()) return { passed: false, checks: [], error: '데모에서는 웹 실습 채점을 할 수 없어요.' };
  const { data } = await http.post<WebGrade>('/practice-web-grade', { setId, index, html });
  return { passed: Boolean(data.passed), checks: data.checks ?? [], error: data.error ?? '' };
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

// ── 학생이 만드는 복습 문제 — 자기 노트 · 연습장 파일로. 만든 세트는 나만 본다 ─────────

export interface PracticeJob {
  id: string;
  origin: 'note' | 'file';
  label: string;
  status: 'running' | 'done' | 'failed';
  /** 다 만들면 새 세트 id — 연습장 ?set= 으로 연다 */
  setId: string | null;
  message: string;
}

export interface PracticeQuota {
  used: number;
  limit: number;
  /** 한 번에 만드는 문제 수 */
  count: number;
}

const DEMO_ONLY = '데모에서는 문제를 만들 수 없어요 — 서버에 연결된 앱에서 써 주세요.';

export async function fetchPracticeQuota(): Promise<PracticeQuota> {
  if (isTestMode()) return { used: 0, limit: 5, count: 6 };
  const { data } = await http.get<PracticeQuota>('/practice-custom');
  return data;
}

/** 내 노트로 — 노트가 정리한 수업 파일로 문제를 만든다(몇 분). 끝났는지는 fetchPracticeJob */
export async function startPracticeFromNote(noteId: string): Promise<PracticeJob> {
  if (isTestMode()) throw new Error(DEMO_ONLY);
  const { data } = await http.post<PracticeJob>(`/practice-custom/note/${encodeURIComponent(noteId)}`);
  return data;
}

/** 연습장에서 연 노트북으로 — 셀을 .py 글로 보낸다 */
export async function startPracticeFromFile(name: string, content: string): Promise<PracticeJob> {
  if (isTestMode()) throw new Error(DEMO_ONLY);
  const { data } = await http.post<PracticeJob>('/practice-custom/file', { name, content });
  return data;
}

export async function fetchPracticeJob(id: string): Promise<PracticeJob> {
  const { data } = await http.get<PracticeJob>(`/practice-custom/${encodeURIComponent(id)}`);
  return data;
}

// ── 연습장 튜터 — 문제 셀은 3단계 힌트, 일반 셀은 코드 · 오류 설명. 대화는 서버가 기억한다 ─────────

export type TutorMode = 'problem' | 'cell';
export type TutorKind = 'hint' | 'explain' | 'offtopic' | 'locked';

export interface TutorTurn {
  role: 'user' | 'assistant';
  text: string;
  kind: TutorKind | null;
  hintLevel: number | null;
  /** 답이 가리킨 코드 줄(1부터) */
  lines: number[];
  at: string;
}

export interface TutorReply {
  reply: string;
  kind: TutorKind;
  lines: number[];
  /** 문제 셀의 지금 힌트 단계(1~3). 일반 셀은 null */
  hintLevel: number | null;
  llm: boolean;
}

export interface TutorQuestion {
  mode: TutorMode;
  /** more = 「힌트 더」, answer = 「정답 알려 줘」 */
  action?: 'ask' | 'more' | 'answer';
  question?: string;
  /** 문제 셀 — 원래 세트 · 번호(다시 풀 문제도 원래 자리) */
  setId?: string;
  index?: number;
  /** 오답노트 대화 — 'retry:YYYY-MM-DD' */
  thread?: string;
  code: string;
  run: string;
  grade: string;
}

export async function askTutor(body: TutorQuestion): Promise<TutorReply> {
  if (isTestMode()) return demoTutorAsk(body);
  const { data } = await http.post<TutorReply>('/practice-tutor', body);
  return data;
}

/** 튜터 창을 다시 열 때 — 지난 대화와 지금 힌트 단계 */
export async function fetchTutorThread(
  mode: TutorMode,
  setId?: string,
  index?: number,
  thread?: string,
): Promise<{ turns: TutorTurn[]; hintLevel: number }> {
  if (isTestMode()) return demoTutorThread(mode, setId, index, thread);
  const { data } = await http.get<{ turns: TutorTurn[]; hintLevel: number }>('/practice-tutor', {
    params: mode === 'problem' ? { mode, setId, index, thread } : { mode },
  });
  return data;
}

/** 튜터 「새 대화」 — 이 문제(또는 일반 셀)의 내 대화를 지운다. 힌트 단계도 처음부터 */
export async function resetTutorThread(mode: TutorMode, setId?: string, index?: number, thread?: string): Promise<void> {
  if (isTestMode()) {
    await demoTutorReset(mode, setId, index, thread);
    return;
  }
  await http.delete('/practice-tutor', { params: mode === 'problem' ? { mode, setId, index, thread } : { mode } });
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

/** 설문 등록 · 수정. 새 설문이면 task.id 를 비워 보낸다. 서버가 붙인 id 를 돌려준다 */
export async function saveFormTask(task: FormTask): Promise<string> {
  const exists = currentDb().formTasks.some((t) => t.id === task.id);
  if (isTestMode()) {
    const id = exists ? task.id : nextId('form');
    mutate((db) => ({
      formTasks: exists
        ? db.formTasks.map((t) => (t.id === task.id ? { ...task, id } : t))
        : [{ ...task, id }, ...db.formTasks],
    }));
    return id;
  }
  try {
    const data = await runCommand('saveFormTask', {
      id: exists ? task.id : undefined,
      cohortId: apiCohortId(),
      title: task.title,
      description: task.description,
      mode: task.mode === 'builtin' ? 'builtin' : 'external_form',
      formUrl: task.formUrl,
      questions: task.mode === 'builtin' ? task.questions : [],
      notionGuideUrl: task.notionGuideUrl,
      dueAt: task.dueAt.toISOString(),
      published: task.published,
    });
    return String(data.id ?? task.id);
  } catch (error) {
    throw new Error(await readApiError(error));
  }
}

export async function deleteFormTask(id: string): Promise<void> {
  const before = currentDb();
  mutate((db) => ({
    formTasks: db.formTasks.filter((t) => t.id !== id),
    formResponses: db.formResponses.filter((r) => r.taskId !== id),
  }));
  if (isTestMode()) return;
  try {
    await runCommand('deleteFormTask', { id });
  } catch (error) {
    mutate(() => ({ formTasks: before.formTasks, formResponses: before.formResponses }));
    throw new Error(await readApiError(error));
  }
}

/** LMS 설문 제출 — 마감 전이면 다시 내서 고칠 수 있다. 서버가 정리한 답으로 화면을 맞춘다 */
export async function submitFormResponse(
  task: FormTask,
  answers: Record<string, FormAnswer>,
  user: User,
): Promise<void> {
  let saved = answers;
  let submittedAt = new Date();
  if (!isTestMode()) {
    try {
      const data = await runCommand('submitFormResponse', { taskId: task.id, answers });
      if (data.answers && typeof data.answers === 'object') saved = data.answers as Record<string, FormAnswer>;
      if (typeof data.submittedAt === 'string') submittedAt = new Date(data.submittedAt);
    } catch (error) {
      throw new Error(await readApiError(error));
    }
  }
  mutate((db) => {
    const previous = db.formResponses.find((r) => r.taskId === task.id && r.userId === user.uid);
    return {
      formResponses: [
        ...db.formResponses.filter((r) => r !== previous),
        {
          id: previous?.id ?? nextId('fr'),
          taskId: task.id,
          userId: user.uid,
          userEmail: user.personalEmail ?? user.email,
          userDisplayName: user.displayName,
          source: 'builtin',
          answers: saved,
          submittedAt,
        },
      ],
      formTasks: previous
        ? db.formTasks
        : db.formTasks.map((t) => (t.id === task.id ? { ...t, responseCount: t.responseCount + 1 } : t)),
    };
  });
}

/** 외부 폼 링크를 열면 제출로 친다(외부 폼은 실제 제출을 알 길이 없다) */
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

/** 시험 일정을 마지막으로 받은 때 */
export function useQualExamsSyncedAt(): Date | undefined {
  return useDb((db) => db.qualExamsSyncedAt);
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

const fullSetFlights = new Map<string, Promise<void>>();

/** bootstrap 은 문제 본문을 뺀 세트(partial)를 보낸다 — 본문을 받아 캐시의 세트를 바꾼다. 같은 세트는 한 번만 요청한다 */
export function loadFullPracticeSets(ids: string[]): Promise<void> {
  if (isTestMode()) return Promise.resolve();
  const sets = getBootstrapDb().practiceSets;
  const unique = [...new Set(ids)];
  const wanted = unique.filter((id) => sets.find((s) => s.id === id)?.partial && !fullSetFlights.has(id));
  if (wanted.length > 0) {
    const request = http
      .get<{ practiceSets?: PracticeSet[] }>('/practice-sets', { params: { ids: wanted.join(',') } })
      .then(({ data }) => {
        const full = new Map((data.practiceSets ?? []).map((s) => [s.id, s]));
        queryClient.setQueryData<Database>(queryKeys.bootstrap, (prev) =>
          prev ? { ...prev, practiceSets: prev.practiceSets.map((s) => full.get(s.id) ?? s) } : prev,
        );
      })
      .finally(() => wanted.forEach((id) => fullSetFlights.delete(id)));
    wanted.forEach((id) => fullSetFlights.set(id, request));
  }
  return Promise.all(unique.map((id) => fullSetFlights.get(id)).filter(Boolean)).then(() => undefined);
}

/** 세트 본문이 다 왔는지 — 연습장처럼 문제 본문이 필요한 화면이 연다. 없는 세트는 기다리지 않는다 */
export function useFullPracticeSets(ids: string[]): { ready: boolean; failed: boolean } {
  const key = [...new Set(ids)].sort().join(',');
  const ready = useDb((db) => key.split(',').every((id) => !id || !db.practiceSets.find((s) => s.id === id)?.partial));
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!key) return;
    setFailed(false);
    loadFullPracticeSets(key.split(',')).catch(() => setFailed(true));
  }, [key]);

  return { ready, failed: failed && !ready };
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
