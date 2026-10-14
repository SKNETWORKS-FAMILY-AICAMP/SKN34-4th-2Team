import type {
  AiEvalResult,
  AiGenerationLog,
  AlertPopup,
  Assessment,
  AssessmentQuestion,
  AssessmentSubmission,
  Attendance,
  AttendanceIssue,
  Cohort,
  CurriculumSheet,
  FormResponse,
  FormTask,
  InflearnPackage,
  MileageProduct,
  MileageSettings,
  MileageTransaction,
  Notice,
  PracticeAttempt,
  PracticeReport,
  PracticeReview,
  PracticeSet,
  Post,
  PostComment,
  PurchaseRequest,
  QualExamSchedule,
  Resume,
  ResumeFeedback,
  ScheduledNotice,
  ProjectTeam,
  SeatPresence,
  SeatingAssignment,
  SeatingRoom,
  SpotCheck,
  StudyNote,
  StudySource,
  Submission,
  Todo,
  User,
  YoutubeRecommendation,
} from '../domain/types';

export interface Database {
  users: User[];
  cohorts: Cohort[];
  notices: Notice[];
  scheduledNotices: ScheduledNotice[];
  alertPopups: AlertPopup[];
  posts: Post[];
  postComments: PostComment[];
  todos: Todo[];
  submissions: Submission[];
  attendances: Attendance[];
  resumes: Resume[];
  resumeFeedbacks: ResumeFeedback[];
  assessments: Assessment[];
  assessmentQuestions: Record<string, AssessmentQuestion[]>;
  assessmentSubmissions: AssessmentSubmission[];
  inflearnPackages: InflearnPackage[];
  youtubeRecommendations: YoutubeRecommendation[];
  studySources: StudySource[];
  studyNotes: StudyNote[];
  curriculumSheets: CurriculumSheet[];
  curriculumPdfs: { cohortId: string; filename: string }[];
  formTasks: FormTask[];
  formResponses: FormResponse[];
  mileageProducts: MileageProduct[];
  mileageTransactions: MileageTransaction[];
  purchaseRequests: PurchaseRequest[];
  mileageSettings: MileageSettings;
  seatingRooms: SeatingRoom[];
  /** 강의실마다 하나 — roomId로 찾는다. */
  seatingAssignments: SeatingAssignment[];
  /** cohortId → 학생에게 보이는 강의실 */
  seatingMeta: Record<string, { publishedRoomId?: string }>;
  projectTeams: ProjectTeam[];
  seatPresence: SeatPresence[];
  /** 불시 자리 점검 — 최근 것이 앞 */
  spotChecks: SpotCheck[];
  /** 출결 신청(예외 출결) */
  attendanceIssues: AttendanceIssue[];
  qualExams: QualExamSchedule[];
  qualExamsSyncedAt?: Date;
  /** 수업일마다 만든 실습 문제 세트 — 기수 공용 */
  practiceSets: PracticeSet[];
  /** 학생별 풀이 기록 — 복습 추천·강사 대시보드의 재료 */
  practiceAttempts: PracticeAttempt[];
  /** 「이 문제 이상해요」 신고 · 강사 결정 */
  practiceReports: PracticeReport[];
  practiceReviews: PracticeReview[];
  aiLogs: AiGenerationLog[];
  aiEvals: AiEvalResult[];
  /** 알림 팝업 「오늘 하루 보지 않기」 — uid → popupId → dateKey */
  alertDismissals: Record<string, Record<string, string>>;
  /** 로그인한 학생이 이미 확인한 알림 id */
  alertReadIds: string[];
}

/** 테스트·「데이터 초기화」용 */
export function emptyDb(): Database {
  return {
    users: [],
    cohorts: [],
    notices: [],
    scheduledNotices: [],
    alertPopups: [],
    posts: [],
    postComments: [],
    todos: [],
    submissions: [],
    attendances: [],
    resumes: [],
    resumeFeedbacks: [],
    assessments: [],
    assessmentQuestions: {},
    assessmentSubmissions: [],
    inflearnPackages: [],
    youtubeRecommendations: [],
    studySources: [],
    studyNotes: [],
    curriculumSheets: [],
    curriculumPdfs: [],
    formTasks: [],
    formResponses: [],
    mileageProducts: [],
    mileageTransactions: [],
    purchaseRequests: [],
    mileageSettings: { categoryLimits: {}, accrualRules: {} },
    seatingRooms: [],
    seatingAssignments: [],
    seatingMeta: {},
    projectTeams: [],
    seatPresence: [],
    spotChecks: [],
    attendanceIssues: [],
    qualExams: [],
    practiceSets: [],
    practiceAttempts: [],
    practiceReports: [],
    practiceReviews: [],
    aiLogs: [],
    aiEvals: [],
    alertDismissals: {},
    alertReadIds: [],
  };
}
