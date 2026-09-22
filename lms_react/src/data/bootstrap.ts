import type {
  AlertPopup,
  Assessment,
  AssessmentQuestion,
  AssessmentSubmission,
  Attendance,
  Cohort,
  CurriculumSheet,
  FormResponse,
  FormTask,
  InflearnPackage,
  MileageProduct,
  MileageSettings,
  MileageTransaction,
  Notice,
  PurchaseRequest,
  QualExamSchedule,
  Resume,
  ResumeFeedback,
  ScheduleRepeatType,
  ScheduledNotice,
  SeatingAssignment,
  SeatingCellType,
  SeatingRoom,
  Submission,
  Todo,
  User,
  YoutubeRecommendation,
} from '../domain/types';
import { resumeStatusFromServer } from '../features/resume/resumeGroups';
import { http } from './http';
import { emptyDb, type Database } from './store';

function asDate(value: unknown): Date | undefined {
  if (value == null || value === '') return undefined;
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? undefined : date;
}

function hhmm(value: unknown): string | undefined {
  if (value == null || value === '') return undefined;
  const text = String(value);
  return text.length >= 5 ? text.slice(0, 5) : text;
}

function rowsOf(payload: Record<string, unknown>, key: string): Record<string, unknown>[] {
  const value = payload[key];
  return Array.isArray(value) ? (value as Record<string, unknown>[]) : [];
}

export function mapUser(row: Record<string, unknown>): User {
  return {
    uid: String(row.firebase_uid ?? row.uid ?? ''),
    email: String(row.email ?? ''),
    personalEmail: row.personalEmail || row.personal_email ? String(row.personalEmail ?? row.personal_email) : undefined,
    displayName: String(row.displayName ?? row.display_name ?? ''),
    role: (row.role as User['role']) || 'student',
    cohortId: String(row.cohortId ?? row.cohort_code ?? ''),
    cohortName: String(row.cohortName ?? row.cohort_name ?? ''),
    seatNumber: row.seatNumber == null && row.seat_number == null ? undefined : Number(row.seatNumber ?? row.seat_number),
    isActive: Boolean(row.isActive ?? row.is_active ?? true),
    mustChangePassword: Boolean(row.mustChangePassword ?? row.must_change_password),
    motto: row.motto ? String(row.motto) : undefined,
    skills: Array.isArray(row.skills) ? (row.skills as string[]) : [],
    socialLinks: (row.socialLinks as Record<string, string>) ?? (row.social_links as Record<string, string>) ?? {},
    jobPreferences: (row.jobPreferences as User['jobPreferences']) ??
      (row.job_preferences as User['jobPreferences']) ?? {
        targetRoles: [],
        regions: [],
        employmentTypes: [],
      },
    photoUrl: row.photoUrl || row.photo_url ? String(row.photoUrl ?? row.photo_url) : undefined,
    mileageBalance: Number(row.mileageBalance ?? row.mileage_balance ?? 0),
    createdAt: asDate(row.createdAt ?? row.created_at),
    lastLoginAt: asDate(row.lastLoginAt ?? row.last_login),
  };
}

export function mapNotice(row: Record<string, unknown>): Notice {
  return {
    id: String(row.id ?? row.pk ?? ''),
    title: String(row.title ?? ''),
    content: String(row.content ?? ''),
    authorName: String(row.authorName ?? row.author_name ?? ''),
    authorId: row.authorId == null && row.author_id == null ? undefined : String(row.authorId ?? row.author_id),
    isFavorite: Boolean(row.isFavorite ?? row.is_favorite),
    priority: Number(row.priority ?? 0),
    source: row.source ? String(row.source) : undefined,
    channelLabel: row.channelLabel ? String(row.channelLabel) : undefined,
    scheduledNoticeId: row.scheduledNoticeId == null ? undefined : String(row.scheduledNoticeId),
    imageUrl: row.imageUrl ? String(row.imageUrl) : undefined,
    createdAt: asDate(row.createdAt ?? row.created_at) ?? new Date(),
  };
}

export function mapScheduled(row: Record<string, unknown>): ScheduledNotice {
  const repeat = String(row.repeatType ?? row.repeat_type ?? 'once');
  return {
    id: String(row.id ?? row.pk ?? ''),
    title: String(row.title ?? ''),
    content: String(row.content ?? ''),
    authorName: String(row.authorName ?? row.author_name ?? ''),
    isFavorite: Boolean(row.isFavorite ?? row.is_favorite),
    repeatType: (repeat === 'daily' || repeat === 'weekly' ? repeat : 'once') as ScheduleRepeatType,
    publishTime: hhmm(row.publishTime ?? row.publish_time) ?? '09:00',
    publishAt: asDate(row.publishAt ?? row.publish_at),
    weekday: Number(row.weekday ?? 1),
    isActive: Boolean(row.isActive ?? row.is_active),
    lastPublishedAt: asDate(row.lastPublishedAt ?? row.last_published_at),
    nextPublishAt: asDate(row.nextPublishAt ?? row.next_publish_at),
    createdAt: asDate(row.createdAt ?? row.created_at),
  };
}

export function mapAlert(row: Record<string, unknown>): AlertPopup {
  return {
    id: String(row.id ?? row.pk ?? ''),
    title: String(row.title ?? ''),
    content: String(row.content ?? ''),
    authorName: String(row.authorName ?? row.author_name ?? ''),
    isActive: Boolean(row.isActive ?? row.is_active),
    sortOrder: Number(row.sortOrder ?? row.sort_order ?? 0),
    linkUrl: row.linkUrl || row.link_url ? String(row.linkUrl ?? row.link_url) : undefined,
    startTime: hhmm(row.startTime ?? row.start_time),
    endTime: hhmm(row.endTime ?? row.end_time),
    createdAt: asDate(row.createdAt ?? row.created_at),
  };
}

export function mapCohort(row: Record<string, unknown>): Cohort {
  return {
    cohortId: String(row.cohortId ?? row.code ?? ''),
    name: String(row.name ?? ''),
    description: row.description ? String(row.description) : undefined,
    isActive: Boolean(row.isActive ?? row.is_active ?? true),
    status: (row.status as Cohort['status']) || 'active',
    studentCount: Number(row.studentCount ?? row.student_count ?? 0),
    createdAt: asDate(row.createdAt ?? row.created_at),
  };
}

function mapAttendance(row: Record<string, unknown>): Attendance {
  return {
    id: String(row.id ?? row.pk ?? ''),
    userId: String(row.userId ?? row.user_id ?? ''),
    userDisplayName: row.userDisplayName ? String(row.userDisplayName) : undefined,
    type: String(row.type ?? 'checkIn'),
    dateKey: String(row.dateKey ?? row.date_key ?? '').slice(0, 10),
    status: row.status as Attendance['status'],
    checkInTime: hhmm(row.checkInTime ?? row.check_in_time),
    checkOutTime: hhmm(row.checkOutTime ?? row.check_out_time),
    statusSource: row.statusSource || row.status_source ? String(row.statusSource ?? row.status_source) : undefined,
  };
}

function mapTodo(row: Record<string, unknown>): Todo {
  return {
    id: String(row.id ?? row.pk ?? ''),
    title: String(row.title ?? ''),
    isCompleted: Boolean(row.isCompleted ?? row.is_completed),
    createdAt: asDate(row.createdAt ?? row.created_at),
  };
}

function mapSubmission(row: Record<string, unknown>): Submission {
  return {
    id: String(row.id ?? row.pk ?? ''),
    userId: String(row.userId ?? row.user_id ?? ''),
    userDisplayName: String(row.userDisplayName ?? row.user_display_name ?? ''),
    title: String(row.title ?? ''),
    type: (row.type as Submission['type']) || 'study',
    status: (row.status as Submission['status']) || 'pending',
    submittedAt: asDate(row.submittedAt ?? row.submitted_at),
    reviewComment: row.reviewComment ? String(row.reviewComment) : undefined,
    fileUrls: Array.isArray(row.fileUrls) ? (row.fileUrls as string[]) : Array.isArray(row.file_urls) ? (row.file_urls as string[]) : [],
    mileageGranted: Boolean(row.mileageGranted ?? row.mileage_granted),
    mileageAmount: Number(row.mileageAmount ?? row.mileage_amount ?? 0),
  };
}

function mapResume(row: Record<string, unknown>): Resume {
  return {
    id: String(row.id ?? row.pk ?? ''),
    userId: String(row.userId ?? row.user_id ?? ''),
    userDisplayName: row.userDisplayName ? String(row.userDisplayName) : undefined,
    title: String(row.title ?? ''),
    status: resumeStatusFromServer(row.status),
    sections: (row.sections as Record<string, boolean>) ?? {},
    content: (row.content as Resume['content']) ?? ({} as Resume['content']),
    isBaseResume: Boolean(row.isBaseResume ?? row.is_base_resume),
    feedbackCount: Number(row.feedbackCount ?? row.feedback_count ?? 0),
    lastSeenFeedbackCount: Number(row.lastSeenFeedbackCount ?? 0),
    readFeedbackIds: Array.isArray(row.readFeedbackIds) ? (row.readFeedbackIds as string[]) : [],
    revisionCount: Number(row.revisionCount ?? 0),
    updatedAt: asDate(row.updatedAt ?? row.updated_at),
  };
}

/** 원본 · 사본 관계는 DB 가 숫자 pk 로 가리킨다. 화면이 쓰는 공개 id 로 바꿔 붙인다 */
function mapResumes(rows: Record<string, unknown>[]): Resume[] {
  const idByPk = new Map(rows.map((r) => [String(r.pk ?? r.id), String(r.id ?? r.pk ?? '')]));
  const ref = (value: unknown) => (value == null || value === '' ? undefined : idByPk.get(String(value)) ?? String(value));
  return rows.map((row) => ({
    ...mapResume(row),
    baseResumeId: ref(row.baseResumeId),
    sourceTailoredResumeId: ref(row.sourceTailoredResumeId),
    linkedJobId: row.linkedJobId ? String(row.linkedJobId) : undefined,
  }));
}

function mapResumeFeedback(row: Record<string, unknown>): ResumeFeedback {
  return {
    id: String(row.id ?? row.pk ?? ''),
    resumeId: String(row.resumeId ?? row.resume_id ?? ''),
    sectionKey: String(row.sectionKey ?? row.section_key ?? ''),
    content: String(row.content ?? ''),
    authorId: String(row.authorId ?? row.author_id ?? ''),
    authorName: String(row.authorName ?? row.author_name ?? ''),
    parentId: String(row.parentId ?? row.parent_id ?? ''),
    createdAt: asDate(row.createdAt ?? row.created_at),
  };
}

function mapAssessment(row: Record<string, unknown>): Assessment {
  return {
    id: String(row.id ?? row.pk ?? ''),
    title: String(row.title ?? ''),
    tags: Array.isArray(row.tags) ? (row.tags as string[]) : [],
    questionCount: Number(row.questionCount ?? row.question_count ?? 0),
    maxScore: Number(row.maxScore ?? row.max_score ?? 0),
    startAt: asDate(row.startAt ?? row.start_at) ?? new Date(),
    endAt: asDate(row.endAt ?? row.end_at) ?? new Date(),
    thumbnailUrl: row.thumbnailUrl ? String(row.thumbnailUrl) : undefined,
    published: Boolean(row.published),
    createdBy: row.createdBy ? String(row.createdBy) : undefined,
    createdAt: asDate(row.createdAt ?? row.created_at),
  };
}

function mapQuestion(row: Record<string, unknown>): AssessmentQuestion & { assessmentId: string } {
  return {
    id: String(row.id ?? row.pk ?? ''),
    assessmentId: String(row.assessmentId ?? row.assessment_id ?? ''),
    order: Number(row.order ?? 0),
    type: (row.type as AssessmentQuestion['type']) || 'multipleChoice',
    prompt: String(row.prompt ?? row.question ?? ''),
    points: Number(row.points ?? 1),
    choices: Array.isArray(row.choices) ? (row.choices as string[]) : [],
    correctIndex: row.correctIndex == null ? undefined : Number(row.correctIndex),
    acceptedAnswers: Array.isArray(row.acceptedAnswers) ? (row.acceptedAnswers as string[]) : [],
    explanation: row.explanation ? String(row.explanation) : undefined,
    origin: String(row.origin ?? 'manual'),
  };
}

function mapAssessmentSubmission(row: Record<string, unknown>): AssessmentSubmission {
  return {
    id: String(row.id ?? row.pk ?? ''),
    assessmentId: String(row.assessmentId ?? row.assessment_id ?? ''),
    userId: String(row.userId ?? row.user_id ?? ''),
    userDisplayName: String(row.userDisplayName ?? ''),
    answers: (row.answers as AssessmentSubmission['answers']) ?? {},
    autoTotalScore: Number(row.autoTotalScore ?? row.auto_total_score ?? 0),
    totalScore: Number(row.totalScore ?? row.total_score ?? 0),
    submittedAt: asDate(row.submittedAt ?? row.submitted_at),
    gradedAt: asDate(row.gradedAt ?? row.graded_at),
  };
}

function mapFormTask(row: Record<string, unknown>): FormTask {
  return {
    id: String(row.id ?? row.pk ?? ''),
    title: String(row.title ?? ''),
    description: String(row.description ?? ''),
    formUrl: String(row.formUrl ?? row.form_url ?? ''),
    notionGuideUrl: row.notionGuideUrl ? String(row.notionGuideUrl) : undefined,
    dueAt: asDate(row.dueAt ?? row.due_at) ?? new Date(),
    published: Boolean(row.published ?? true),
    responseCount: Number(row.responseCount ?? row.response_count ?? 0),
    createdAt: asDate(row.createdAt ?? row.created_at),
  };
}

function mapFormResponse(row: Record<string, unknown>): FormResponse {
  return {
    id: String(row.id ?? `${row.taskId ?? row.task_id}-${row.userId ?? row.user_id}`),
    userId: String(row.userId ?? row.user_id ?? ''),
    userEmail: String(row.userEmail ?? row.user_email ?? ''),
    userDisplayName: String(row.userDisplayName ?? ''),
    taskId: String(row.taskId ?? row.task_id ?? ''),
    source: String(row.source ?? 'manual'),
    submittedAt: asDate(row.submittedAt ?? row.submitted_at),
  };
}

function mapProduct(row: Record<string, unknown>): MileageProduct {
  return {
    id: String(row.id ?? row.pk ?? ''),
    name: String(row.name ?? ''),
    description: String(row.description ?? ''),
    imageUrl: row.imageUrl ? String(row.imageUrl) : undefined,
    category: String(row.category ?? ''),
    pricingType: (row.pricingType as MileageProduct['pricingType']) || (row.pricing_type as MileageProduct['pricingType']) || 'fixed',
    fixedPrice: row.fixedPrice == null && row.fixed_price == null ? undefined : Number(row.fixedPrice ?? row.fixed_price),
    isActive: Boolean(row.isActive ?? row.is_active ?? true),
    sortOrder: Number(row.sortOrder ?? row.sort_order ?? 0),
  };
}

function mapTx(row: Record<string, unknown>): MileageTransaction {
  return {
    id: String(row.id ?? row.pk ?? ''),
    userId: String(row.userId ?? row.user_id ?? ''),
    userDisplayName: String(row.userDisplayName ?? ''),
    amount: Number(row.amount ?? 0),
    reason: String(row.reason ?? ''),
    type: row.type ? String(row.type) : undefined,
    relatedId: row.relatedId ? String(row.relatedId) : undefined,
    adjustedBy: row.adjustedBy ? String(row.adjustedBy) : undefined,
    createdAt: asDate(row.createdAt ?? row.created_at),
  };
}

function mapPurchase(row: Record<string, unknown>): PurchaseRequest {
  return {
    id: String(row.id ?? row.pk ?? ''),
    userId: String(row.userId ?? row.user_id ?? ''),
    userDisplayName: String(row.userDisplayName ?? ''),
    items: Array.isArray(row.items) ? (row.items as PurchaseRequest['items']) : [],
    totalAmount: Number(row.totalAmount ?? row.total_amount ?? 0),
    status: (row.status as PurchaseRequest['status']) || 'pending',
    reviewComment: row.reviewComment ? String(row.reviewComment) : undefined,
    createdAt: asDate(row.createdAt ?? row.created_at),
  };
}

function mapMileageSettings(row: Record<string, unknown> | undefined): MileageSettings {
  if (!row) return { categoryLimits: {}, accrualRules: {} };
  return {
    categoryLimits: (row.categoryLimits as Record<string, number>) ?? (row.category_limits as Record<string, number>) ?? {},
    accrualRules: (row.accrualRules as Record<string, number>) ?? (row.accrual_rules as Record<string, number>) ?? {},
    updatedAt: asDate(row.updatedAt ?? row.updated_at),
  };
}

function mapInflearn(row: Record<string, unknown>): InflearnPackage {
  return {
    id: String(row.id ?? row.pk ?? ''),
    title: String(row.title ?? ''),
    subject: String(row.subject ?? ''),
    type: (row.type as InflearnPackage['type']) || 'review',
    summary: row.summary ? String(row.summary) : undefined,
    units: Array.isArray(row.units) ? (row.units as InflearnPackage['units']) : [],
    courses: Array.isArray(row.courses) ? (row.courses as InflearnPackage['courses']) : [],
    isPublished: Boolean(row.isPublished ?? row.is_published),
    sortOrder: Number(row.sortOrder ?? row.sort_order ?? 0),
    publishedAt: asDate(row.publishedAt ?? row.published_at),
  };
}

function mapYoutube(row: Record<string, unknown>): YoutubeRecommendation {
  return {
    id: String(row.id ?? row.pk ?? ''),
    title: String(row.title ?? ''),
    youtubeUrl: String(row.youtubeUrl ?? row.youtube_url ?? ''),
    videoId: row.videoId || row.video_id ? String(row.videoId ?? row.video_id) : undefined,
    description: row.description ? String(row.description) : undefined,
    tags: Array.isArray(row.tags) ? (row.tags as string[]) : [],
    isPublished: Boolean(row.isPublished ?? row.is_published),
    sortOrder: Number(row.sortOrder ?? row.sort_order ?? 0),
    createdAt: asDate(row.createdAt ?? row.created_at),
  };
}

function mapSheet(row: Record<string, unknown>): CurriculumSheet {
  return {
    id: String(row.id ?? row.pk ?? ''),
    title: String(row.title ?? ''),
    fileName: String(row.fileName ?? row.file_name ?? ''),
    rows: Array.isArray(row.rows) ? (row.rows as CurriculumSheet['rows']) : [],
    uploadedBy: row.uploadedBy ? String(row.uploadedBy) : undefined,
    uploadedAt: asDate(row.uploadedAt ?? row.uploaded_at),
  };
}

/**
 * 좌석 — 서버는 강의실 · 칸 · 배치 · 좌석 배정을 표 그대로 보낸다(seating_rooms / seating_cells /
 * seating_assignments / seat_assignments). 화면은 강의실 여러 개 중 하나를 확정하는 구조라 그대로 옮긴다.
 * 칸 · 배정은 강의실을 숫자 pk 로 가리키므로 pk → 공개 id 로 바꾼다.
 */
function mapSeating(
  payload: Record<string, unknown>,
  users: User[],
  fallbackCohort: string,
): Pick<Database, 'seatingRooms' | 'seatingAssignments' | 'seatingMeta'> {
  const rooms = rowsOf(payload, 'seatingRooms');
  const cells = rowsOf(payload, 'seatingCells');
  const assignments = rowsOf(payload, 'seatingAssignments');
  const seats = rowsOf(payload, 'seatAssignments');
  const roomIdByPk = new Map(rooms.map((r) => [String(r.pk ?? r.id), String(r.id ?? r.pk ?? '')]));
  const cohortByRoom = new Map(rooms.map((r) => [String(r.id ?? r.pk ?? ''), String(r.cohortId ?? fallbackCohort)]));
  const seatIdByCellPk = new Map(cells.map((c) => [String(c.pk ?? c.id), String(c.seatId ?? '')]));
  const nameOf = new Map(users.map((u) => [u.uid, u.displayName]));
  const roomOf = (row: Record<string, unknown>) => roomIdByPk.get(String(row.roomId ?? '')) ?? String(row.roomId ?? '');

  const seatingRooms: SeatingRoom[] = rooms.map((r) => {
    const id = String(r.id ?? r.pk ?? '');
    const pk = String(r.pk ?? r.id);
    return {
      id,
      cohortId: String(r.cohortId ?? fallbackCohort),
      rows: Number(r.rows ?? 0),
      cols: Number(r.cols ?? 0),
      roomNumber: r.roomNumber ? String(r.roomNumber) : undefined,
      cells: cells
        .filter((c) => String(c.roomId) === pk)
        .map((c) => ({
          seatId: String(c.seatId ?? ''),
          row: Number(c.row ?? 0),
          col: Number(c.col ?? 0),
          label: String(c.label ?? ''),
          type: (String(c.type ?? 'seat') as SeatingCellType) || 'seat',
          groupId: c.groupId ? String(c.groupId) : undefined,
        })),
      createdAt: asDate(r.createdAt),
      updatedAt: asDate(r.updatedAt),
    };
  });

  const seatingAssignments: SeatingAssignment[] = assignments.map((a) => {
    const roomId = roomOf(a);
    const map: Record<string, string> = {};
    const names: Record<string, string> = {};
    for (const s of seats) {
      if (roomOf(s) !== roomId) continue;
      const seatId = seatIdByCellPk.get(String(s.cellId ?? ''));
      const userId = s.userId ? String(s.userId) : '';
      if (!seatId || !userId) continue;
      map[seatId] = userId;
      names[seatId] = nameOf.get(userId) ?? '';
    }
    return {
      roomId,
      cohortId: cohortByRoom.get(roomId) ?? fallbackCohort,
      status: a.status === 'published' ? 'published' : 'draft',
      assignments: map,
      seatNames: names,
      publishedAt: asDate(a.publishedAt),
      updatedAt: asDate(a.updatedAt),
    };
  });

  const publishedPk = payload.publishedSeatingRoomId;
  const publishedRoomId = publishedPk == null ? undefined : roomIdByPk.get(String(publishedPk)) ?? String(publishedPk);
  const seatingMeta: Database['seatingMeta'] = publishedRoomId ? { [fallbackCohort]: { publishedRoomId } } : {};
  return { seatingRooms, seatingAssignments, seatingMeta };
}

function mapQualExams(payload: Record<string, unknown>): QualExamSchedule[] {
  const cache = rowsOf(payload, 'systemCache');
  const out: QualExamSchedule[] = [];
  for (const row of cache) {
    if (!String(row.key ?? '').toLowerCase().includes('qual')) continue;
    const data = row.data;
    const items = Array.isArray(data) ? data : data && typeof data === 'object' && Array.isArray((data as { items?: unknown[] }).items)
      ? (data as { items: unknown[] }).items
      : [];
    for (const item of items) {
      if (item && typeof item === 'object') out.push(item as QualExamSchedule);
    }
  }
  return out;
}

export function mapBootstrap(payload: Record<string, unknown>): Database {
  const me = (payload.me ?? {}) as Record<string, unknown>;
  const users = rowsOf(payload, 'users').map(mapUser);
  const cohorts = rowsOf(payload, 'cohorts').map(mapCohort);
  const sessionUid = String(me.uid ?? me.firebase_uid ?? '');
  const sessionCohort = String(me.cohortId ?? cohorts[0]?.cohortId ?? '');
  const dismissals: Record<string, Record<string, string>> = {};
  if (sessionUid) {
    dismissals[sessionUid] = {};
    for (const raw of rowsOf(payload, 'alertPopupDismissals')) {
      const popupId = String(raw.popupId ?? raw.popup_id ?? '');
      const dateKey = String(raw.dateKey ?? raw.date_key ?? '').slice(0, 10);
      if (popupId && dateKey) dismissals[sessionUid][popupId] = dateKey;
    }
  }
  const questions = rowsOf(payload, 'assessmentQuestions').map(mapQuestion);
  const grouped: Record<string, AssessmentQuestion[]> = {};
  for (const question of questions) {
    const list = grouped[question.assessmentId] ?? [];
    list.push(question);
    grouped[question.assessmentId] = list;
  }
  const settingsRow = rowsOf(payload, 'mileageSettings')[0];
  return {
    ...emptyDb(),
    users,
    cohorts,
    notices: rowsOf(payload, 'notices').map(mapNotice),
    scheduledNotices: rowsOf(payload, 'scheduledNotices').map(mapScheduled),
    alertPopups: rowsOf(payload, 'alertPopups').map(mapAlert),
    todos: rowsOf(payload, 'todos').map(mapTodo),
    submissions: rowsOf(payload, 'submissions').map(mapSubmission),
    attendances: rowsOf(payload, 'attendances').map(mapAttendance),
    resumes: mapResumes(rowsOf(payload, 'resumes')),
    resumeFeedbacks: rowsOf(payload, 'resumeFeedbacks').map(mapResumeFeedback),
    assessments: rowsOf(payload, 'assessments').map(mapAssessment),
    assessmentQuestions: grouped,
    assessmentSubmissions: rowsOf(payload, 'assessmentSubmissions').map(mapAssessmentSubmission),
    inflearnPackages: rowsOf(payload, 'inflearnPackages').map(mapInflearn),
    youtubeRecommendations: rowsOf(payload, 'youtubeRecommendations').map(mapYoutube),
    studySources: rowsOf(payload, 'studySources').map((row) => ({
      id: String(row.id ?? row.pk ?? ''),
      title: String(row.title ?? ''),
      repoUrl: String(row.repoUrl ?? row.repo_url ?? ''),
      branch: String(row.branch ?? 'main'),
      allowedPrefixes: Array.isArray(row.allowedPrefixes) ? (row.allowedPrefixes as string[]) : [],
      isActive: Boolean(row.isActive ?? row.is_active ?? true),
      sortOrder: Number(row.sortOrder ?? row.sort_order ?? 0),
    })),
    studyNotes: rowsOf(payload, 'studyNotes').map((row) => ({
      id: String(row.id ?? row.pk ?? ''),
      sourceId: String(row.sourceId ?? row.source_id ?? ''),
      status: String(row.status ?? 'done'),
      scopeType: ['date', 'prefix', 'files'].includes(String(row.scopeType))
        ? (String(row.scopeType) as 'date' | 'prefix' | 'files')
        : undefined,
      scopeValue: Array.isArray(row.scopeValue)
        ? (row.scopeValue as unknown[]).map(String)
        : row.scopeValue != null
          ? String(row.scopeValue)
          : undefined,
      scopeKey: row.scopeKey ? String(row.scopeKey) : undefined,
      reportMarkdown: String(row.reportMarkdown ?? row.report_markdown ?? ''),
      reviewMarkdown: String(row.reviewMarkdown ?? row.review_markdown ?? ''),
      files: Array.isArray(row.files) ? (row.files as { path: string; commit: string }[]) : [],
      createdAt: asDate(row.createdAt ?? row.created_at),
    })),
    curriculumSheets: rowsOf(payload, 'curriculumSheets').map(mapSheet),
    formTasks: rowsOf(payload, 'formTasks').map(mapFormTask),
    formResponses: rowsOf(payload, 'formResponses').map(mapFormResponse),
    mileageProducts: rowsOf(payload, 'mileageProducts').map(mapProduct),
    mileageTransactions: rowsOf(payload, 'mileageTransactions').map(mapTx),
    purchaseRequests: rowsOf(payload, 'purchaseRequests').map(mapPurchase),
    mileageSettings: mapMileageSettings(settingsRow),
    ...mapSeating(payload, users, sessionCohort),
    qualExams: mapQualExams(payload),
    aiLogs: rowsOf(payload, 'aiGenerationLogs').map((row) => ({
      id: String(row.id ?? row.pk ?? ''),
      type: String(row.type ?? ''),
      promptVersion: String(row.promptVersion ?? row.prompt_version ?? ''),
      model: String(row.model ?? ''),
      generatedCount: Number(row.generatedCount ?? 0),
      latencyMs: Number(row.latencyMs ?? row.latency_ms ?? 0),
      status: (row.status as 'success' | 'error') || 'success',
      createdAt: asDate(row.createdAt ?? row.created_at),
    })),
    alertDismissals: dismissals,
  };
}

let lastSessionUid = '';
let lastSessionCohortId = '';

export function lastBootstrapSession(): { uid: string; cohortId: string } {
  return { uid: lastSessionUid, cohortId: lastSessionCohortId };
}

export async function fetchBootstrap(): Promise<Database> {
  const { data } = await http.get<Record<string, unknown>>('/bootstrap');
  const db = mapBootstrap(data);
  const me = (data.me ?? {}) as Record<string, unknown>;
  lastSessionUid = String(me.uid ?? me.firebase_uid ?? '');
  lastSessionCohortId = String(me.cohortId ?? db.cohorts[0]?.cohortId ?? '');
  return db;
}
