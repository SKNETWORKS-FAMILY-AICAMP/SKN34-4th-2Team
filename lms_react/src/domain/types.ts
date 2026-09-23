/**
 * 도메인 모델 — Flutter `lib/shared/models/*.dart`를 옮겼다.
 *
 * Firestore 직렬화(`fromFirestore`/`toFirestore`)는 빠졌다. 프로토타입의
 * 저장소는 메모리라서 문서를 오갈 일이 없다. 필드 이름과 뜻은 그대로다.
 * 날짜는 `Date`, Dart의 nullable은 `?`로 옮겼다.
 */

export type UserRole = 'admin' | 'instructor' | 'student';

/** 취업 희망 조건 — shared/models/job_preferences.dart */
export interface JobPreferences {
  /** 희망 직무. 매처의 ROLE_TERMS 키와 같은 문자열이어야 점수에 반영된다. */
  targetRoles: string[];
  /** 희망 근무지역. 공고의 지역 문자열에 포함되는지로 거른다(예: '서울' ⊂ '서울 성동구'). */
  regions: string[];
  /** 희망 고용형태. 공고의 고용형태와 정확히 같아야 통과한다(예: '정규직'). */
  employmentTypes: string[];
}

export interface User {
  uid: string;
  email: string;
  /** 구글폼 제출 매칭용 개인 이메일 */
  personalEmail?: string;
  displayName: string;
  role: UserRole;
  cohortId: string;
  cohortName: string;
  seatNumber?: number;
  isActive: boolean;
  mustChangePassword: boolean;
  motto?: string;
  skills: string[];
  socialLinks: Record<string, string>;
  jobPreferences: JobPreferences;
  birthDate?: string;
  photoUrl?: string;
  mileageBalance: number;
  createdAt?: Date;
  lastLoginAt?: Date;
}

/** 출결 상태 — core/constants/attendance_status.dart */
export type AttendanceStatusCode =
  | 'present'
  | 'late'
  | 'earlyLeave'
  | 'absent'
  | 'officialLeave';

export interface Attendance {
  id: string;
  userId: string;
  userDisplayName?: string;
  /** legacy: checkIn / checkOut */
  type: string;
  dateKey: string;
  status?: AttendanceStatusCode;
  checkInTime?: string;
  checkOutTime?: string;
  /** demo | form | manual */
  statusSource?: string;
  formAttendanceType?: string;
  officialLeaveUsed?: boolean;
  officialLeaveType?: string;
  officialLeaveOther?: string;
}

export interface Notice {
  id: string;
  title: string;
  content: string;
  authorName: string;
  authorId?: string;
  isFavorite: boolean;
  priority: number;
  source?: string;
  channelLabel?: string;
  scheduledNoticeId?: string;
  imageUrl?: string;
  createdAt?: Date;
}

export type ScheduleRepeatType = 'once' | 'daily' | 'weekly';

export interface ScheduledNotice {
  id: string;
  title: string;
  content: string;
  authorName: string;
  isFavorite: boolean;
  repeatType: ScheduleRepeatType;
  /** 'HH:mm' */
  publishTime: string;
  publishAt?: Date;
  weekday: number;
  isActive: boolean;
  lastPublishedAt?: Date;
  nextPublishAt?: Date;
  createdAt?: Date;
}

export interface AlertPopup {
  id: string;
  title: string;
  content: string;
  authorName: string;
  isActive: boolean;
  sortOrder: number;
  linkUrl?: string;
  /** 'HH:mm' */
  startTime?: string;
  endTime?: string;
  createdAt?: Date;
}

export interface Post {
  id: string;
  authorId: string;
  authorName: string;
  content: string;
  likeCount: number;
  commentCount: number;
  createdAt?: Date;
}

export interface Todo {
  id: string;
  title: string;
  isCompleted: boolean;
  createdAt?: Date;
}

/** 기록실 제출 — core/constants/record_types.dart */
export type RecordType =
  | 'certification'
  | 'study'
  | 'blog'
  | 'studyCert'
  | 'precourseQuiz';

export type SubmissionStatus = 'pending' | 'approved' | 'rejected';

export interface Submission {
  id: string;
  userId: string;
  userDisplayName: string;
  title: string;
  type: RecordType;
  status: SubmissionStatus;
  submittedAt?: Date;
  reviewComment?: string;
  certType?: string;
  fileUrls: string[];
  startAt?: Date;
  endAt?: Date;
  weekNumber?: number;
  weekLabel?: string;
  link?: string;
  quizScore?: number;
  learningDate?: Date;
  learningContent?: string;
  isTeamStudy?: boolean;
  mileageGranted: boolean;
  mileageAmount: number;
}

export type CohortStatus = 'planned' | 'active' | 'closed';

/** 학생 상담 내용 — student_intakes. 관리자가 학생을 등록할 때 함께 받는다 */
export interface StudentIntake {
  educationMajor: string;
  currentStatus: string;
  weeklyStudyHours: string;
  programmingLevel: string;
  collaborationTools: string;
  aiLlmExperience: string;
  motivation: string;
  desiredRole: string;
  postCompletionGoal: string;
  awards: string;
  projectLinks: string;
  teamRole: string;
  selfLearningStyle: string;
  slumpOvercomeExperience: string;
}

export interface Cohort {
  cohortId: string;
  name: string;
  description?: string;
  startDate?: Date;
  endDate?: Date;
  isActive: boolean;
  status: CohortStatus;
  termNumber?: number;
  classroomName?: string;
  studentCount: number;
  createdAt?: Date;
}

// ── 이력서 ─────────────────────────────────────────────

export interface ResumeBasicInfo {
  name: string;
  phone: string;
  email: string;
  birthDate: string;
  githubUrl: string;
  blogUrl: string;
}

export interface ResumeExperienceItem {
  id: string;
  company: string;
  role: string;
  startDate: string;
  endDate: string;
  isCurrent: boolean;
  description: string;
}

export interface ResumeEducationItem {
  id: string;
  school: string;
  major: string;
  startDate: string;
  endDate: string;
  /** 졸업 / 재학 / 수료 */
  status: string;
}

/** 기술스택은 이름 + 숙련도(고급·중급·초급) */
export interface ResumeTechStackItem {
  id: string;
  name: string;
  level: string;
}

export interface ResumeCertificationItem {
  id: string;
  name: string;
  issuer: string;
  acquiredDate: string;
}

export interface ResumeAwardItem {
  id: string;
  name: string;
  organization: string;
  date: string;
  description: string;
}

export interface ResumeTrainingItem {
  id: string;
  course: string;
  organization: string;
  startDate: string;
  endDate: string;
  description: string;
}

export interface ResumeActivityItem {
  id: string;
  name: string;
  startDate: string;
  endDate: string;
  description: string;
}

export interface ResumeProjectItem {
  id: string;
  name: string;
  startDate: string;
  endDate: string;
  role: string;
  techStack: string;
  description: string;
  url: string;
}

export interface ResumeIntroSection {
  subtitle: string;
  body: string;
}

/** 자기소개서 여섯 문항 */
export interface ResumeSelfIntroduction {
  intro: ResumeIntroSection;
  motivation: ResumeIntroSection;
  challenge: ResumeIntroSection;
  growth: ResumeIntroSection;
  strengthsWeaknesses: ResumeIntroSection;
  aspiration: ResumeIntroSection;
}

/** 이력서 본문 — shared/models/resume_content.dart 그대로 */
export interface ResumeContent {
  basicInfo: ResumeBasicInfo;
  coreCompetencies: { text: string };
  experience: ResumeExperienceItem[];
  education: ResumeEducationItem[];
  techStack: ResumeTechStackItem[];
  certifications: ResumeCertificationItem[];
  awards: ResumeAwardItem[];
  trainingExperience: ResumeTrainingItem[];
  otherActivities: ResumeActivityItem[];
  projects: ResumeProjectItem[];
  selfIntroduction: ResumeSelfIntroduction;
}

export type ResumeStatus = 'draft' | 'submitted' | 'feedbackRequested' | 'approved';

export interface Resume {
  id: string;
  userId: string;
  userDisplayName?: string;
  title: string;
  status: ResumeStatus;
  /** 섹션별 작성 완료 표시 */
  sections: Record<string, boolean>;
  content: ResumeContent;
  isBaseResume: boolean;
  /** 공고 맞춤 이력서면 만든 원본 이력서 id (resumes.base_resume_id) */
  baseResumeId?: string;
  /** AI 첨삭 작업본을 편집기로 옮긴 사본이면 그 작업본 id (resumes.source_tailored_resume_id) */
  sourceTailoredResumeId?: string;
  /** 맞춘 공고 id (resumes.linked_job_id) */
  linkedJobId?: string;
  feedbackCount: number;
  lastSeenFeedbackCount: number;
  readFeedbackIds: string[];
  revisionCount: number;
  updatedAt?: Date;
}

export interface ResumeFeedback {
  id: string;
  resumeId: string;
  sectionKey: string;
  content: string;
  authorId: string;
  authorName: string;
  parentId: string;
  createdAt?: Date;
}

export interface PostComment {
  id: string;
  postId: string;
  authorId: string;
  authorName: string;
  content: string;
  createdAt?: Date;
}

/** 이력서 첨삭 API sentence_reviews 항목과 대응하는 프런트 계약 */
export interface ResumeReviewSuggestion {
  index: number;
  fieldPath: string;
  originalQuote: string;
  suggestedRevision: string | null;
  reason: string;
  evidenceSources: string[];
  status: 'unchanged' | 'formatting' | 'improved' | 'needs_confirmation';
  editType: 'spelling' | 'tone' | 'clarity' | 'content';
}

// ── 성취도 평가 ────────────────────────────────────────

export type AssessmentQuestionType = 'multipleChoice' | 'shortAnswer';

export interface AssessmentQuestion {
  id: string;
  order: number;
  type: AssessmentQuestionType;
  prompt: string;
  points: number;
  choices: string[];
  correctIndex?: number;
  acceptedAnswers: string[];
  explanation?: string;
  /** manual | ai */
  origin: string;
  sourceDay?: number;
  sourceTopic?: string;
}

export interface Assessment {
  id: string;
  title: string;
  tags: string[];
  questionCount: number;
  maxScore: number;
  startAt: Date;
  endAt: Date;
  thumbnailUrl?: string;
  published: boolean;
  createdBy?: string;
  createdAt?: Date;
}

export interface AssessmentAnswerEntry {
  value: number | string | null;
  autoScore?: number;
  finalScore?: number;
  isCorrect?: boolean;
  comment?: string;
}

export interface AssessmentSubmission {
  id: string;
  assessmentId: string;
  userId: string;
  userDisplayName: string;
  answers: Record<string, AssessmentAnswerEntry>;
  autoTotalScore: number;
  totalScore: number;
  submittedAt?: Date;
  gradedAt?: Date;
}

// ── 학습실 ────────────────────────────────────────────

export type InflearnPackageType = 'review' | 'preview' | 'bonus';

export interface InflearnCourse {
  title: string;
  url: string;
}

export interface InflearnUnit {
  name: string;
  courses: InflearnCourse[];
}

export interface InflearnPackage {
  id: string;
  title: string;
  subject: string;
  type: InflearnPackageType;
  summary?: string;
  units: InflearnUnit[];
  courses: InflearnCourse[];
  isPublished: boolean;
  sortOrder: number;
  publishedAt?: Date;
}

export interface YoutubeRecommendation {
  id: string;
  title: string;
  youtubeUrl: string;
  videoId?: string;
  description?: string;
  tags: string[];
  isPublished: boolean;
  sortOrder: number;
  createdAt?: Date;
}

export interface StudyNoteFileRef {
  path: string;
  commit: string;
}

export interface StudySource {
  id: string;
  title: string;
  repoUrl: string;
  branch: string;
  allowedPrefixes: string[];
  isActive: boolean;
  sortOrder: number;
}

/** 노트 범위 종류 — study_notes.scope_type. prefix 는 폴더 */
export type StudyNoteScopeType = 'date' | 'prefix' | 'files';

export interface StudyNote {
  id: string;
  sourceId: string;
  /** ready(옛 데이터는 done) · generating(정리 중) · too_broad(파일이 너무 많음) · failed */
  status: string;
  /** failed 일 때 이유 */
  errorMessage?: string;
  /** generating · too_broad 일 때 안내 */
  message?: string;
  /** 범위 종류 · 값 · 키 — DB 의 scope_type / scope_value / scope_key 그대로(features/study/noteScope.ts) */
  scopeType?: StudyNoteScopeType;
  scopeValue?: string | string[];
  scopeKey?: string;
  reportMarkdown: string;
  reviewMarkdown: string;
  files: StudyNoteFileRef[];
  createdAt?: Date;
}

// ── 실습 문제 ─────────────────────────────────────────
// study_notes/practice 가 수업 저장소로 만들고 Pyodide 로 검증한 문제. 모양은 PracticeProblem.to_json() 그대로다.

/** code_scratch — 뼈대 없이 빈 에디터에서 함수를 처음부터 짠다. starterCode 는 「뼈대 받기」를 눌렀을 때만 쓴다 */
export type PracticeKind = 'concept' | 'code_output' | 'code_blank' | 'code_fix' | 'code_write' | 'code_scratch';

export interface PracticeProblem {
  kind: PracticeKind;
  topic: string;
  prompt: string;
  sourceFiles: string[];
  explanation: string;
  /** concept */
  choices: string[];
  answerIndex: number | null;
  /** code_* — 학생이 받는 코드. code_blank 는 `__1__` 자리가 빈칸 */
  starterCode: string;
  /** code_output — 검증기가 실제로 돌려 얻은 출력 */
  expectedStdout: string;
  /** code_blank — 빈칸 모범 답 */
  blankAnswers: string[];
  /** 통과했거나 여러 번 틀린 뒤에만 보인다. 서버를 붙이면 그때 받아 온다 */
  referenceSolution: string;
  /** 브라우저가 학생 코드 뒤에 이어 돌려 채점한다 */
  hiddenTests: string;
  packages: string[];
}

/** 기수 · 수업일 하나에 세트 하나. 반 전체가 같은 문제를 푼다. */
export interface PracticeSet {
  id: string;
  cohortId: string;
  /** 수업 저장소 이름 */
  sourceTitle: string;
  /** YYYY-MM-DD */
  lessonDate: string;
  /** 예: 멀티모달 3일차 */
  dayLabel: string;
  title: string;
  files: string[];
  model: string;
  problems: PracticeProblem[];
}

export interface PracticeAttempt {
  id: string;
  uid: string;
  setId: string;
  index: number;
  passed: boolean;
  tries: number;
  answeredAt: Date;
}

export type PracticeReportReason = 'unclear' | 'answer' | 'tests' | 'offtopic' | 'other';

/** 학생의 「이 문제 이상해요」 신고. 한 문제에 한 사람 한 번 */
export interface PracticeReport {
  id: string;
  uid: string;
  setId: string;
  index: number;
  reason: PracticeReportReason;
  note: string;
  createdAt: Date;
}

/** 강사가 신고를 보고 내린 결정 — 없으면 신고 수로 자동 판단(2명이면 숨김) */
export interface PracticeReview {
  setId: string;
  index: number;
  decision: 'hidden' | 'kept';
  decidedBy: string;
  decidedAt: Date;
}

// ── 커리큘럼 ───────────────────────────────────────────

export interface CurriculumRow {
  dayIndex: number;
  dateLabel: string;
  subject: string;
  topic: string;
  detail: string;
  order: number;
}

export interface CurriculumSheet {
  id: string;
  title: string;
  fileName: string;
  rows: CurriculumRow[];
  uploadedBy?: string;
  uploadedByName?: string;
  uploadedAt?: Date;
}

// ── 설문 · 제출 ────────────────────────────────────────

export interface FormTask {
  id: string;
  title: string;
  description: string;
  formUrl: string;
  notionGuideUrl?: string;
  dueAt: Date;
  published: boolean;
  responseCount: number;
  createdAt?: Date;
}

export interface FormResponse {
  id: string;
  userId: string;
  userEmail: string;
  userDisplayName: string;
  taskId: string;
  /** manual | google */
  source: string;
  submittedAt?: Date;
}

// ── 마일리지 ───────────────────────────────────────────

export interface MileageTransaction {
  id: string;
  userId: string;
  userDisplayName: string;
  amount: number;
  reason: string;
  /** earn | spend | adjust */
  type?: string;
  relatedId?: string;
  adjustedBy?: string;
  createdAt?: Date;
}

// DB · Flutter 원본과 같은 값을 쓴다(custom = 학생이 가격을 직접 넣는 상품)
export type MileagePricingType = 'fixed' | 'custom';

export interface MileageProduct {
  id: string;
  name: string;
  description: string;
  imageUrl?: string;
  category: string;
  pricingType: MileagePricingType;
  fixedPrice?: number;
  isActive: boolean;
  sortOrder: number;
}

export interface MileageCartItem {
  productId: string;
  productName: string;
  category: string;
  pricingType: MileagePricingType;
  unitPrice: number;
  quantity: number;
  purchaseLink?: string;
}

export type PurchaseRequestStatus = 'pending' | 'approved' | 'rejected';

export interface PurchaseRequest {
  id: string;
  userId: string;
  userDisplayName: string;
  items: MileageCartItem[];
  totalAmount: number;
  status: PurchaseRequestStatus;
  reviewComment?: string;
  createdAt?: Date;
}

export interface MileageSettings {
  categoryLimits: Record<string, number>;
  accrualRules: Record<string, number>;
  updatedAt?: Date;
}

// ── 좌석 ──────────────────────────────────────────────

/** 칸의 성격 — seating_cell_type.dart */
export type SeatingCellType = 'empty' | 'seat' | 'instructor' | 'door';

/**
 * 배치표의 한 칸 — seating_layout_model.dart의 SeatingCell
 *
 * 붙어 있는 같은 groupId의 좌석은 한 책상으로 묶여 테두리가 이어진다.
 */
export interface SeatingCell {
  seatId: string;
  row: number;
  col: number;
  label: string;
  type: SeatingCellType;
  groupId?: string;
}

/** 칸 격자만 — 틀 편집과 배치도 그리기가 함께 쓴다. */
export interface SeatingGrid {
  rows: number;
  cols: number;
  cells: SeatingCell[];
}

/**
 * 강의실 하나 — seating_room_model.dart (`cohorts/{id}/seatingRooms/{roomId}`)
 *
 * 기수마다 강의실을 여럿 만들어 둘 수 있고, 그중 하나만 학생에게 「확정」된다.
 * `cells`는 rows×cols 전부를 담는다. 빈 칸도 `empty`로 들어 있다.
 */
export interface SeatingRoom extends SeatingGrid {
  id: string;
  cohortId: string;
  /** 표시 이름 — 제목에 「자리 배치 · 기수 · 302호」로 붙는다. */
  roomNumber?: string;
  createdAt?: Date;
  updatedAt?: Date;
}

export type SeatingAssignmentStatus = 'draft' | 'published';

/**
 * 강의실별 배치 — seating_assignment_model.dart (`seatingAssignments/{roomId}`)
 *
 * `seatNames`는 확정할 때 찍어 두는 이름 사본이다. 학생 화면은 다른 학생의
 * 계정을 읽지 않고 이것만 본다.
 */
export interface SeatingAssignment {
  roomId: string;
  cohortId: string;
  status: SeatingAssignmentStatus;
  /** seatId → userId */
  assignments: Record<string, string>;
  /** seatId → 표시 이름 */
  seatNames: Record<string, string>;
  publishedAt?: Date;
  updatedAt?: Date;
}

/** 프로젝트 팀 — project_team_model.dart. 권장 인원 4~5명. */
export interface ProjectTeam {
  id: string;
  cohortId: string;
  name: string;
  memberIds: string[];
  sortOrder: number;
  colorIndex: number;
  updatedAt?: Date;
}

/**
 * 학생·강사가 보는 확정 배치 — 확정된 강의실과 그 배치를 한데 묶은 것.
 * 확정된 강의실이 없으면 `room`이 비고, 배치가 확정 전이면 `published`가 거짓이다.
 */
export interface PublishedSeating {
  room?: SeatingRoom;
  assignment?: SeatingAssignment;
  published: boolean;
}

/** 자리 확인(강사·관리자) — 좌석별 확인/보류 */
export type SeatPresenceState = 'unknown' | 'confirmed' | 'held';

export interface SeatPresence {
  dateKey: string;
  period: number;
  userId: string;
  state: SeatPresenceState;
}

// ── 자격 시험 일정 ─────────────────────────────────────

export interface QualExamSchedule {
  implYy: string;
  implSeq: number;
  qualgbCd: string;
  qualgbNm: string;
  description: string;
  docRegStartDt?: string;
  docRegEndDt?: string;
  docExamStartDt?: string;
  docExamEndDt?: string;
  docPassDt?: string;
  pracRegStartDt?: string;
  pracRegEndDt?: string;
  pracExamStartDt?: string;
  pracExamEndDt?: string;
  pracPassDt?: string;
}

// ── LLMOps ────────────────────────────────────────────

export interface AiGenerationLog {
  id: string;
  /** assessment | resume_coach | chatbot */
  type: string;
  promptVersion: string;
  model: string;
  generatedCount: number;
  /** 사람이 그대로 받아들인 수 / 고쳐 쓴 수 — 채택률·수정률의 분자다. */
  adoptedCount?: number;
  editedCount?: number;
  /** 「도움이 됐다」를 받은 수 */
  usefulCount?: number;
  latencyMs: number;
  status: 'success' | 'error';
  errorMessage?: string;
  tokenIn?: number;
  tokenOut?: number;
  createdByName?: string;
  createdAt?: Date;
}

export interface AiEvalResult {
  id: string;
  promptVersion: string;
  /** 어느 묶음으로 돌렸는가 — 화면에는 source=… 로 적힌다. */
  suite: string;
  model?: string;
  passRate: number;
  caseCount: number;
  avgLatencyMs?: number;
  ranAt: Date;
}
