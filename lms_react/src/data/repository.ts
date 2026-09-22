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
} from '../domain/types';
import { getDb, mutate, nextId, subscribe, type Database } from './store';
import { dateKeyOf } from './seed';
import { remapAssignments } from '../domain/seatingLayout';

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

/** 메모리 조회를 Query 모양으로 감싼다. 훗날 여기가 fetch 자리가 된다. */
function ready<T>(data: T): Query<T> {
  return { data, loading: false, error: null };
}

export function useDb<T>(select: (db: Database) => T): T {
  // 매 렌더마다 새 배열을 돌려주면 useSyncExternalStore가 값이 바뀐 줄 알고
  // 다시 그리고, 그 렌더가 또 새 배열을 만든다. 얕은 비교로 같으면 지난 값을
  // 그대로 돌려줘 그 고리를 끊는다.
  const cache = useRef<T | null>(null);

  const getSnapshot = useCallback(() => {
    const next = select(getDb());
    const prev = cache.current;
    if (prev !== null && shallowEqual(prev, next)) return prev;
    cache.current = next;
    return next;
  }, [select]);

  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
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
}

export function createUser(user: User): void {
  mutate((db) => ({ users: [...db.users, user] }));
}

export function createCohort(cohort: Cohort): void {
  mutate((db) => ({ cohorts: [...db.cohorts, cohort] }));
}

export function updateCohort(cohortId: string, patch: Partial<Cohort>): void {
  mutate((db) => ({
    cohorts: db.cohorts.map((c) => (c.cohortId === cohortId ? { ...c, ...patch } : c)),
  }));
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
  return id;
}

export function updateNotice(id: string, patch: Partial<Notice>): void {
  mutate((db) => ({
    notices: db.notices.map((n) => (n.id === id ? { ...n, ...patch } : n)),
  }));
}

export function deleteNotice(id: string): void {
  mutate((db) => ({ notices: db.notices.filter((n) => n.id !== id) }));
}

export function useScheduledNotices(): ScheduledNotice[] {
  return useDb((db) => db.scheduledNotices);
}

export function upsertScheduledNotice(notice: ScheduledNotice): void {
  mutate((db) => {
    const exists = db.scheduledNotices.some((n) => n.id === notice.id);
    return {
      scheduledNotices: exists
        ? db.scheduledNotices.map((n) => (n.id === notice.id ? notice : n))
        : [...db.scheduledNotices, { ...notice, id: notice.id || nextId('sn') }],
    };
  });
}

export function deleteScheduledNotice(id: string): void {
  mutate((db) => ({
    scheduledNotices: db.scheduledNotices.filter((n) => n.id !== id),
  }));
}

export function useAlertPopups(): AlertPopup[] {
  return useDb((db) => db.alertPopups);
}

export function upsertAlertPopup(popup: AlertPopup): void {
  mutate((db) => {
    const exists = db.alertPopups.some((p) => p.id === popup.id);
    return {
      alertPopups: exists
        ? db.alertPopups.map((p) => (p.id === popup.id ? popup : p))
        : [...db.alertPopups, { ...popup, id: popup.id || nextId('ap') }],
    };
  });
}

export function deleteAlertPopup(id: string): void {
  mutate((db) => ({ alertPopups: db.alertPopups.filter((p) => p.id !== id) }));
}

export function dismissAlertToday(uid: string, popupId: string): void {
  mutate((db) => ({
    alertDismissals: {
      ...db.alertDismissals,
      [uid]: { ...(db.alertDismissals[uid] ?? {}), [popupId]: dateKeyOf(new Date()) },
    },
  }));
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
}

export function toggleTodo(id: string): void {
  mutate((db) => ({
    todos: db.todos.map((t) => (t.id === id ? { ...t, isCompleted: !t.isCompleted } : t)),
  }));
}

export function deleteTodo(id: string): void {
  mutate((db) => ({ todos: db.todos.filter((t) => t.id !== id) }));
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
  return id;
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
  return id;
}

export function updateProjectTeam(team: ProjectTeam): void {
  mutate((db) => ({
    projectTeams: db.projectTeams.map((t) => (t.id === team.id ? { ...team, updatedAt: new Date() } : t)),
  }));
}

export function deleteProjectTeam(teamId: string): void {
  mutate((db) => ({ projectTeams: db.projectTeams.filter((t) => t.id !== teamId) }));
}

/** 팀 구성을 한 번에 갈아 끼운다. `id`가 빈 팀은 새로 만든다. */
export function replaceProjectTeams(cohortId: string, upserts: ProjectTeam[], deleteIds: string[]): void {
  mutate((db) => {
    const now = new Date();
    const kept = db.projectTeams.filter((t) => !deleteIds.includes(t.id));
    const updated = kept.map((t) => {
      const u = upserts.find((x) => x.id === t.id);
      return u === undefined ? t : { ...u, updatedAt: now };
    });
    const created = upserts
      .filter((u) => u.id === '')
      .map((u) => ({ ...u, id: nextId('team'), cohortId, updatedAt: now }));
    return { projectTeams: [...updated, ...created] };
  });
}

// ── 이력서 ─────────────────────────────────────────────

export function useResumes(): Resume[] {
  return useDb((db) => db.resumes);
}

/** ⬇︎ Query 로 바꾼 것 — 나머지 훅은 아직 예전 모양이다 (시범) */
export function useMyResumes(uid: string): Query<Resume[]> {
  return ready(useDb((db) => db.resumes.filter((r) => r.userId === uid)));
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
  return id;
}

export function updateResume(id: string, patch: Partial<Resume>): void {
  mutate((db) => ({
    resumes: db.resumes.map((r) => (r.id === id ? { ...r, ...patch, updatedAt: new Date() } : r)),
  }));
}

export function deleteResume(id: string): void {
  mutate((db) => ({ resumes: db.resumes.filter((r) => r.id !== id) }));
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
}

export function updateMileageSettings(patch: Partial<import('../domain/types').MileageSettings>): void {
  mutate((db) => ({
    mileageSettings: { ...db.mileageSettings, ...patch, updatedAt: new Date() },
  }));
}

// ── 자격 시험 ──────────────────────────────────────────

/** ⬇︎ Query 로 바꾼 것 (시범) */
export function useQualExams(): Query<QualExamSchedule[]> {
  return ready(useDb((db) => db.qualExams));
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
}

/** 강사 결정 — 숨김 유지 또는 다시 보이기 */
export function reviewPracticeProblem(decidedBy: string, setId: string, index: number, decision: PracticeReview['decision']): void {
  mutate((db) => ({
    practiceReviews: [
      ...db.practiceReviews.filter((r) => !(r.setId === setId && r.index === index)),
      { setId, index, decision, decidedBy, decidedAt: new Date() },
    ],
  }));
}
