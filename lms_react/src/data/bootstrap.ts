import type {
  AlertPopup,
  Assessment,
  AssessmentQuestion,
  AssessmentAnswerEntry,
  AssessmentSubmission,
  Attendance,
  Cohort,
  CurriculumSheet,
  FormResponse,
  FormTask,
  InflearnPackage,
  MileageCartItem,
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
  ProjectTeam,
  SeatingAssignment,
  SeatingCellType,
  SeatingRoom,
  StudyNote,
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

/**
 * DB 의 jsonb 칸 — 서버(lms_api)는 이 칸을 객체가 아니라 JSON 글자로 보낸다.
 * 스키마(scripts/firestore_to_postgres/schema.sql)의 jsonb 칸 이름을 camelCase 로 적었다. 받는 입구에서 한 번 푼다.
 */
const JSONB_FIELDS = new Set([
  'accrualRules', 'before', 'categoryLimits', 'content', 'courses', 'data', 'details', 'files', 'jobPreferences',
  'payload', 'requirements', 'response', 'scopeValue', 'sections', 'sessions', 'socialLinks', 'telemetry', 'units', 'value',
]);

export function parseJsonb(row: Record<string, unknown>): Record<string, unknown> {
  let out: Record<string, unknown> | null = null;
  for (const key of Object.keys(row)) {
    const v = row[key];
    if (!JSONB_FIELDS.has(key) || typeof v !== 'string') continue;
    try {
      (out ??= { ...row })[key] = JSON.parse(v);
    } catch {
      // JSON 이 아니면 글자 그대로 둔다
    }
  }
  return out ?? row;
}

function rowsOf(payload: Record<string, unknown>, key: string): Record<string, unknown>[] {
  const value = payload[key];
  return Array.isArray(value) ? (value as Record<string, unknown>[]).map(parseJsonb) : [];
}

/** 노트 한 행 — bootstrap 의 studyNotes 와 /study-notes API 가 같은 모양을 준다 */
export function mapStudyNote(raw: Record<string, unknown>): StudyNote {
  const row = parseJsonb(raw);
  const text = (v: unknown) => (v == null || v === '' ? undefined : String(v));
  return {
    id: String(row.id ?? row.pk ?? ''),
    sourceId: String(row.sourceId ?? row.source_id ?? ''),
    status: String(row.status ?? 'done'),
    errorMessage: text(row.errorMessage ?? row.error_message),
    message: text(row.message),
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
  };
}

function withJobDefaults(value: unknown): User['jobPreferences'] {
  const v = (value && typeof value === 'object' ? value : {}) as Partial<User['jobPreferences']>;
  const list = (x: unknown) => (Array.isArray(x) ? (x as string[]) : []);
  return { ...v, targetRoles: list(v.targetRoles), regions: list(v.regions), employmentTypes: list(v.employmentTypes) };
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
    socialLinks: ((row.socialLinks ?? row.social_links) as Record<string, string> | null) ?? {},
    // 강사 · 관리자는 DB 에 {} 로 들어 있다 — 빠진 목록은 빈 목록으로(화면이 .length 에서 멈췄다)
    jobPreferences: withJobDefaults(row.jobPreferences ?? row.job_preferences),
    photoUrl: row.photoUrl || row.photo_url ? String(row.photoUrl ?? row.photo_url) : undefined,
    mileageBalance: Number(row.mileageBalance ?? row.mileage_balance ?? 0),
    createdAt: asDate(row.createdAt ?? row.created_at),
    lastLoginAt: asDate(row.lastLoginAt ?? row.last_login),
  };
}

export function mapNotice(row: Record<string, unknown>): Notice {
  return {
    id: String(row.pk ?? row.id ?? ''),
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
    id: String(row.pk ?? row.id ?? ''),
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
    id: String(row.pk ?? row.id ?? ''),
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
    startDate: asDate(row.startDate ?? row.start_date),
    endDate: asDate(row.endDate ?? row.end_date),
    termNumber: row.termNumber == null && row.term_number == null ? undefined : Number(row.termNumber ?? row.term_number),
    classroomName: row.classroomName || row.classroom_name ? String(row.classroomName ?? row.classroom_name) : undefined,
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
    content: withResumeDefaults(row.content),
    isBaseResume: Boolean(row.isBaseResume ?? row.is_base_resume),
    feedbackCount: Number(row.feedbackCount ?? row.feedback_count ?? 0),
    lastSeenFeedbackCount: Number(row.lastSeenFeedbackCount ?? 0),
    readFeedbackIds: Array.isArray(row.readFeedbackIds) ? (row.readFeedbackIds as string[]) : [],
    revisionCount: Number(row.revisionCount ?? 0),
    updatedAt: asDate(row.updatedAt ?? row.updated_at),
  };
}

const EMPTY_INTRO = { subtitle: '', body: '' };

/** 이력서 내용 — 빠진 칸은 빈 값으로 채워 받는다. 화면은 모든 칸이 있다고 보고 그린다 */
function withResumeDefaults(value: unknown): Resume['content'] {
  const c = (value && typeof value === 'object' ? value : {}) as Partial<Resume['content']>;
  const list = <T,>(v: T[] | undefined): T[] => (Array.isArray(v) ? v : []);
  const intro = (c.selfIntroduction ?? {}) as Partial<Resume['content']['selfIntroduction']>;
  return {
    basicInfo: { name: '', phone: '', email: '', birthDate: '', githubUrl: '', blogUrl: '', ...(c.basicInfo ?? {}) },
    coreCompetencies: { text: '', ...(c.coreCompetencies ?? {}) },
    experience: list(c.experience),
    education: list(c.education),
    techStack: list(c.techStack),
    certifications: list(c.certifications),
    awards: list(c.awards),
    trainingExperience: list(c.trainingExperience),
    otherActivities: list(c.otherActivities),
    projects: list(c.projects),
    selfIntroduction: {
      intro: { ...EMPTY_INTRO, ...intro.intro },
      motivation: { ...EMPTY_INTRO, ...intro.motivation },
      challenge: { ...EMPTY_INTRO, ...intro.challenge },
      growth: { ...EMPTY_INTRO, ...intro.growth },
      strengthsWeaknesses: { ...EMPTY_INTRO, ...intro.strengthsWeaknesses },
      aspiration: { ...EMPTY_INTRO, ...intro.aspiration },
    },
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

function mapCurriculumRow(row: Record<string, unknown>): CurriculumSheet['rows'][number] {
  return {
    dayIndex: Number(row.dayIndex ?? row.day_index ?? 0),
    dateLabel: String(row.dateLabel ?? row.date_label ?? ''),
    subject: String(row.subject ?? ''),
    topic: String(row.topic ?? ''),
    detail: String(row.detail ?? ''),
    order: Number(row.order ?? 0),
  };
}

function mapCartItem(row: Record<string, unknown>): MileageCartItem {
  return {
    productId: String(row.productId ?? row.product_id ?? ''),
    productName: String(row.productName ?? row.product_name ?? ''),
    category: String(row.category ?? ''),
    pricingType: (row.pricingType as MileageCartItem['pricingType']) || 'fixed',
    unitPrice: Number(row.unitPrice ?? row.unit_price ?? 0),
    quantity: Number(row.quantity ?? 1),
    purchaseLink: row.purchaseLink ? String(row.purchaseLink) : undefined,
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
    const rowCount = Number(r.rows ?? 0);
    const colCount = Number(r.cols ?? 0);
    const stored = cells
      .filter((c) => String(c.roomId) === pk)
      .map((c) => ({
        seatId: String(c.seatId ?? ''),
        row: Number(c.row ?? 0),
        col: Number(c.col ?? 0),
        label: String(c.label ?? ''),
        type: (String(c.type ?? 'seat') as SeatingCellType) || 'seat',
        groupId: c.groupId ? String(c.groupId) : undefined,
      }));
    // DB 는 빈 칸을 두지 않는다. 화면(격자 편집 · 놓을 자리)은 rows×cols 전부를 기대하므로 빈 칸을 채운다
    const at = new Map(stored.map((c) => [`${c.row},${c.col}`, c]));
    const full: SeatingRoom['cells'] = [];
    for (let row = 0; row < rowCount; row++) {
      for (let col = 0; col < colCount; col++) {
        full.push(at.get(`${row},${col}`) ?? { seatId: '', row, col, label: '', type: 'empty' });
      }
    }
    return {
      id,
      cohortId: String(r.cohortId ?? fallbackCohort),
      rows: rowCount,
      cols: colCount,
      roomNumber: r.roomNumber ? String(r.roomNumber) : undefined,
      cells: full,
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

  const seatingMeta: Database['seatingMeta'] = {};
  const byCohort = (payload.publishedSeatingRooms ?? {}) as Record<string, unknown>;
  for (const [cohortId, pk] of Object.entries(byCohort)) {
    seatingMeta[cohortId] = { publishedRoomId: roomIdByPk.get(String(pk)) ?? String(pk) };
  }
  const publishedPk = payload.publishedSeatingRoomId;
  if (publishedPk != null && seatingMeta[fallbackCohort] === undefined) {
    seatingMeta[fallbackCohort] = { publishedRoomId: roomIdByPk.get(String(publishedPk)) ?? String(publishedPk) };
  }
  return { seatingRooms, seatingAssignments, seatingMeta };
}

/** 프로젝트 팀 — 팀원은 project_team_members 로 따로 온다(팀을 숫자 pk 로 가리킨다) */
function mapTeams(payload: Record<string, unknown>, fallbackCohort: string): ProjectTeam[] {
  const members = rowsOf(payload, 'projectTeamMembers');
  return rowsOf(payload, 'projectTeams').map((t) => {
    const pk = String(t.pk ?? t.id);
    return {
      id: String(t.id ?? t.pk ?? ''),
      cohortId: String(t.cohortId ?? fallbackCohort),
      name: String(t.name ?? ''),
      memberIds: members.filter((m) => String(m.teamId) === pk).map((m) => String(m.userId ?? '')).filter(Boolean),
      sortOrder: Number(t.sortOrder ?? 0),
      colorIndex: Number(t.colorIndex ?? 0),
      updatedAt: asDate(t.updatedAt),
    };
  });
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

/**
 * 서버는 목록에 사람 **이름**을 넣어 보내지 않는다(칸이 없다). 화면은 이름으로 그리므로
 * 받은 명단에서 채운다. 이걸 안 하면 이력서 · 기록실 · 마일리지에 계정 id 가 그대로 보인다.
 */
function withNames<T extends { userId: string; userDisplayName?: string }>(
  rows: T[],
  nameOf: Map<string, string>,
): T[] {
  return rows.map((r) => (r.userDisplayName ? r : { ...r, userDisplayName: nameOf.get(r.userId) ?? '' }));
}

/** 딸린 표를 열쇠별로 묶는다 — 커리큘럼 행 · 구매 상품 · 답안을 붙일 때 */
function groupBy<T>(rows: T[], key: (row: T) => string): Map<string, T[]> {
  const out = new Map<string, T[]>();
  for (const row of rows) {
    const k = key(row);
    const list = out.get(k);
    if (list) list.push(row);
    else out.set(k, [row]);
  }
  return out;
}

export function mapBootstrap(payload: Record<string, unknown>): Database {
  const me = parseJsonb((payload.me ?? {}) as Record<string, unknown>);
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
  const nameOf = new Map(users.map((u) => [u.uid, u.displayName]));
  const studentsOf = new Map<string, number>();
  for (const u of users) {
    if (u.role === 'student' && u.isActive) studentsOf.set(u.cohortId, (studentsOf.get(u.cohortId) ?? 0) + 1);
  }

  // 커리큘럼 행 — 표(curriculum_rows)로 따로 온다
  const rowsBySheet = groupBy(rowsOf(payload, 'curriculumRows'), (r) => String(r.sheetId ?? r.sheet_id ?? ''));
  const sheets = rowsOf(payload, 'curriculumSheets').map((s) => {
    const sheet = mapSheet(s);
    const rows = rowsBySheet.get(String(s.pk ?? s.id ?? '')) ?? [];
    return sheet.rows.length > 0 ? sheet : { ...sheet, rows: rows.map(mapCurriculumRow) };
  });

  // 구매 요청에 담긴 상품
  const itemsByRequest = groupBy(
    rowsOf(payload, 'purchaseRequestItems'),
    (r) => String(r.requestId ?? r.request_id ?? ''),
  );
  const purchases = rowsOf(payload, 'purchaseRequests').map((r) => {
    const request = mapPurchase(r);
    const items = itemsByRequest.get(String(r.pk ?? r.id ?? '')) ?? [];
    return request.items.length > 0 ? request : { ...request, items: items.map(mapCartItem) };
  });

  // 평가 답안 — 문항 번호를 화면 id 로 되돌려 묶는다
  const answersBySubmission = groupBy(
    rowsOf(payload, 'assessmentAnswers'),
    (r) => String(r.submissionId ?? r.submission_id ?? ''),
  );
  const questionIdByPk = new Map(
    rowsOf(payload, 'assessmentQuestions').map((q) => [String(q.pk ?? q.id ?? ''), String(q.id ?? q.pk ?? '')]),
  );
  const assessmentSubmissions = rowsOf(payload, 'assessmentSubmissions').map((row) => {
    const submission = mapAssessmentSubmission(row);
    if (Object.keys(submission.answers).length > 0) return submission;
    const answers: AssessmentSubmission['answers'] = {};
    for (const a of answersBySubmission.get(String(row.pk ?? row.id ?? '')) ?? []) {
      const key = questionIdByPk.get(String(a.questionId ?? a.question_id ?? '')) ?? String(a.questionId ?? '');
      answers[key] = {
        value: (a.value ?? null) as AssessmentAnswerEntry['value'],
        autoScore: Number(a.autoScore ?? a.auto_score ?? 0),
        finalScore: Number(a.finalScore ?? a.final_score ?? 0),
        isCorrect: Boolean(a.isCorrect ?? a.is_correct),
      };
    }
    return { ...submission, answers };
  });

  return {
    ...emptyDb(),
    users,
    cohorts: cohorts.map((c) => (c.studentCount > 0 ? c : { ...c, studentCount: studentsOf.get(c.cohortId) ?? 0 })),
    notices: rowsOf(payload, 'notices').map(mapNotice),
    scheduledNotices: rowsOf(payload, 'scheduledNotices').map(mapScheduled),
    alertPopups: rowsOf(payload, 'alertPopups').map(mapAlert),
    todos: rowsOf(payload, 'todos').map(mapTodo),
    submissions: withNames(rowsOf(payload, 'submissions').map(mapSubmission), nameOf),
    attendances: rowsOf(payload, 'attendances').map(mapAttendance),
    seatPresence: rowsOf(payload, 'seatPresences').map((row) => ({
      dateKey: String(row.presenceDate ?? row.presence_date ?? '').slice(0, 10),
      period: Number(row.period),
      userId: String(row.userId ?? row.user_id ?? ''),
      state: row.state === 'confirmed' || row.state === 'held' ? row.state : 'unknown',
    })),
    resumes: withNames(mapResumes(rowsOf(payload, 'resumes')), nameOf),
    resumeFeedbacks: rowsOf(payload, 'resumeFeedbacks').map(mapResumeFeedback),
    assessments: rowsOf(payload, 'assessments').map(mapAssessment),
    assessmentQuestions: grouped,
    assessmentSubmissions: withNames(assessmentSubmissions, nameOf),
    inflearnPackages: rowsOf(payload, 'inflearnPackages').map(mapInflearn),
    youtubeRecommendations: rowsOf(payload, 'youtubeRecommendations').map(mapYoutube),
    studySources: rowsOf(payload, 'studySources').map((row) => ({
      id: String(row.id ?? row.pk ?? ''),
      cohortId: row.cohortId ? String(row.cohortId) : undefined,
      title: String(row.title ?? ''),
      repoUrl: String(row.repoUrl ?? row.repo_url ?? ''),
      branch: String(row.branch ?? 'main'),
      allowedPrefixes: Array.isArray(row.allowedPrefixes) ? (row.allowedPrefixes as string[]) : [],
      isActive: Boolean(row.isActive ?? row.is_active ?? true),
      sortOrder: Number(row.sortOrder ?? row.sort_order ?? 0),
    })),
    studyNotes: rowsOf(payload, 'studyNotes').map(mapStudyNote),
    curriculumSheets: sheets,
    formTasks: rowsOf(payload, 'formTasks').map(mapFormTask),
    formResponses: withNames(rowsOf(payload, 'formResponses').map(mapFormResponse), nameOf),
    mileageProducts: rowsOf(payload, 'mileageProducts').map(mapProduct),
    mileageTransactions: withNames(rowsOf(payload, 'mileageTransactions').map(mapTx), nameOf),
    purchaseRequests: withNames(purchases, nameOf),
    mileageSettings: mapMileageSettings(settingsRow),
    ...mapSeating(payload, users, sessionCohort),
    projectTeams: mapTeams(payload, sessionCohort),
    // 복습 문제 — 서버(practice_service.py)가 화면 모양 그대로 보낸다. 날짜만 Date 로
    practiceSets: rowsOf(payload, 'practiceSets') as unknown as Database['practiceSets'],
    practiceAttempts: rowsOf(payload, 'practiceAttempts').map((a) => ({
      ...(a as unknown as Database['practiceAttempts'][number]),
      answeredAt: asDate(a.answeredAt) ?? new Date(0),
    })),
    practiceReports: rowsOf(payload, 'practiceReports').map((r) => ({
      ...(r as unknown as Database['practiceReports'][number]),
      createdAt: asDate(r.createdAt) ?? new Date(0),
    })),
    practiceReviews: rowsOf(payload, 'practiceReviews').map((v) => ({
      ...(v as unknown as Database['practiceReviews'][number]),
      decidedAt: asDate(v.decidedAt) ?? new Date(0),
    })),
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
