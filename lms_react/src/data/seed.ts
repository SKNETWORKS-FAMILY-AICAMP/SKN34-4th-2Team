import type {
  AiEvalResult,
  PracticeAttempt,
  PracticeReport,
  ResumeContent,
  AiGenerationLog,
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
  Post,
  PostComment,
  PurchaseRequest,
  QualExamSchedule,
  Resume,
  ResumeFeedback,
  ScheduledNotice,
  ProjectTeam,
  SeatingAssignment,
  SeatingRoom,
  StudyNote,
  StudySource,
  Submission,
  Todo,
  User,
  YoutubeRecommendation,
} from '../domain/types';
import { MileageDefaultLimits } from '../domain/constants';
import { emptyGrid, placeFixture, placeTable } from '../domain/seatingLayout';

/**
 * 시연용 데이터 — Flutter `lib/shared/demo/`를 옮겼다.
 *
 * demo_accounts.dart의 계정 셋과 demo_lms_repository.dart의 시드가 출처다.
 * 날짜는 「오늘 기준 상대값」으로 두어, 언제 열어도 이번 주 이야기로 보인다.
 */
const now = new Date();

export function daysAgo(n: number): Date {
  const d = new Date(now);
  d.setDate(d.getDate() - n);
  return d;
}

export function hoursAgo(n: number): Date {
  const d = new Date(now);
  d.setHours(d.getHours() - n);
  return d;
}

export function daysAhead(n: number): Date {
  return daysAgo(-n);
}

export function dateKeyOf(d: Date): string {
  const p = (v: number) => String(v).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export const DemoConfig = {
  cohortId: 'cohort_34',
  cohortName: 'SK네트웍스 Family AI 캠프 34기',
} as const;

const emptyJobPreferences = { targetRoles: [], regions: [], employmentTypes: [] };

function student(
  uid: string,
  name: string,
  seat: number,
  extra: Partial<User> = {},
): User {
  return {
    uid,
    email: `${uid}@playdata.co.kr`,
    personalEmail: `${uid}@gmail.com`,
    displayName: name,
    role: 'student',
    cohortId: DemoConfig.cohortId,
    cohortName: DemoConfig.cohortName,
    seatNumber: seat,
    isActive: true,
    mustChangePassword: false,
    skills: [],
    socialLinks: {},
    jobPreferences: emptyJobPreferences,
    mileageBalance: 0,
    createdAt: daysAgo(90),
    ...extra,
  };
}

/** 로그인 계정 — 비밀번호는 셋 다 Playdata123! */
export const DemoAccounts = {
  password: 'Playdata123!',
  adminUid: 'demo-admin-001',
  studentUid: 'demo-student-001',
  instructorUid: 'demo-instructor-001',
} as const;

export const seedUsers: User[] = [
  {
    uid: DemoAccounts.adminUid,
    email: 'admin@playdata.co.kr',
    displayName: 'PLAYDATA 관리자',
    role: 'admin',
    cohortId: DemoConfig.cohortId,
    cohortName: DemoConfig.cohortName,
    isActive: true,
    mustChangePassword: false,
    skills: [],
    socialLinks: {},
    jobPreferences: emptyJobPreferences,
    mileageBalance: 0,
    createdAt: daysAgo(200),
  },
  {
    uid: DemoAccounts.instructorUid,
    email: 'instructor@playdata.co.kr',
    displayName: '김강사',
    role: 'instructor',
    cohortId: DemoConfig.cohortId,
    cohortName: DemoConfig.cohortName,
    isActive: true,
    mustChangePassword: false,
    skills: [],
    socialLinks: {},
    jobPreferences: emptyJobPreferences,
    mileageBalance: 0,
    createdAt: daysAgo(150),
  },
  student(DemoAccounts.studentUid, '이수민', 12, {
    email: 'student@playdata.co.kr',
    personalEmail: 'soomin.demo@gmail.com',
    motto: '기록이 실력이 된다',
    skills: ['Python', 'SQL', 'Pandas', 'Tableau'],
    socialLinks: { github: 'https://github.com/example', blog: 'https://velog.io/@example' },
    jobPreferences: {
      targetRoles: ['데이터 분석가', '데이터 엔지니어'],
      regions: ['서울', '경기'],
      employmentTypes: ['정규직'],
    },
    mileageBalance: 132000,
    birthDate: '2000-04-11',
  }),
  student('demo-student-002', '김하늘', 3, { mileageBalance: 85000, skills: ['Python', 'Django'] }),
  student('demo-student-003', '이도윤', 7, { mileageBalance: 41000, skills: ['SQL', 'Docker'] }),
  student('demo-student-004', '박서연', 15, { mileageBalance: 210000, skills: ['Python', 'AWS'] }),
  student('demo-student-005', '최지우', 21, { mileageBalance: 12000 }),
  student('demo-student-006', '정하준', 25, { mileageBalance: 0, isActive: false }),
  student('demo-student-007', '한예린', 9, { mileageBalance: 64000, skills: ['MySQL'] }),
  student('demo-student-008', '오시현', 18, { mileageBalance: 98000, skills: ['Flutter'] }),
];

export const seedCohorts: Cohort[] = [
  {
    cohortId: DemoConfig.cohortId,
    name: DemoConfig.cohortName,
    description: '데이터·AI 전 과정 6개월 부트캠프',
    startDate: daysAgo(90),
    endDate: daysAhead(90),
    isActive: true,
    status: 'active',
    termNumber: 34,
    classroomName: '강남 5강의장',
    studentCount: 8,
    createdAt: daysAgo(120),
  },
  {
    cohortId: 'cohort_33',
    name: 'SK네트웍스 Family AI 캠프 33기',
    startDate: daysAgo(280),
    endDate: daysAgo(95),
    isActive: false,
    status: 'closed',
    termNumber: 33,
    classroomName: '강남 4강의장',
    studentCount: 24,
    createdAt: daysAgo(310),
  },
  {
    cohortId: 'cohort_35',
    name: 'SK네트웍스 Family AI 캠프 35기',
    startDate: daysAhead(40),
    endDate: daysAhead(220),
    isActive: false,
    status: 'planned',
    termNumber: 35,
    classroomName: '미정',
    studentCount: 0,
    createdAt: daysAgo(10),
  },
];

export const seedNotices: Notice[] = [
  {
    id: 'n1',
    title: '[출결] 오늘 예외 출결 제출',
    content:
      '정상 출석 외에 지각 / 조퇴 / 외출 / 결석(공가 포함) 예정이 있으면 반드시 오늘 날짜로 구글폼을 제출해 주세요.',
    authorName: 'PLAYDATA 관리자',
    isFavorite: true,
    priority: 1,
    channelLabel: '출결',
    createdAt: hoursAgo(5),
  },
  {
    id: 'n2',
    title: '2차 프로젝트 팀 편성 결과',
    content:
      '2차 프로젝트 팀 편성표를 게시했습니다. 팀별 첫 미팅은 오늘 16:00, 강의장 뒤편에서 진행합니다.',
    authorName: '김강사',
    isFavorite: true,
    priority: 1,
    createdAt: daysAgo(1),
  },
  {
    id: 'n3',
    title: '수료 특강 안내 — 이력서 클리닉',
    content: '현직 데이터 분석가를 모시고 이력서 클리닉을 진행합니다. 신청은 설문·제출 메뉴에서 받습니다.',
    authorName: 'PLAYDATA 관리자',
    isFavorite: false,
    priority: 0,
    createdAt: daysAgo(3),
  },
  {
    id: 'n4',
    title: '강의장 좌석 재배치 안내',
    content: '다음 주 월요일부터 좌석이 변경됩니다. 자리 배치 메뉴에서 본인 좌석을 확인해 주세요.',
    authorName: 'PLAYDATA 관리자',
    isFavorite: false,
    priority: 0,
    createdAt: daysAgo(6),
  },
];

export const seedScheduledNotices: ScheduledNotice[] = [
  {
    id: 'sn1',
    title: '[출결] 오늘 예외 출결 제출',
    content: '정상 출석 외 예외 출결은 구글폼으로 제출해 주세요.',
    authorName: 'PLAYDATA 관리자',
    isFavorite: true,
    repeatType: 'daily',
    publishTime: '08:30',
    weekday: 1,
    isActive: true,
    lastPublishedAt: hoursAgo(5),
    nextPublishAt: daysAhead(1),
    createdAt: daysAgo(40),
  },
  {
    id: 'sn2',
    title: '[주간] 회고 작성 안내',
    content: '금요일 회고를 기록실에 남겨 주세요.',
    authorName: '김강사',
    isFavorite: false,
    repeatType: 'weekly',
    publishTime: '17:00',
    weekday: 5,
    isActive: true,
    createdAt: daysAgo(30),
  },
];

export const seedAlertPopups: AlertPopup[] = [
  {
    id: 'ap1',
    title: '오늘 16:00 팀 미팅',
    content: '2차 프로젝트 팀별 첫 미팅이 오늘 16:00에 있습니다.',
    authorName: 'PLAYDATA 관리자',
    isActive: true,
    sortOrder: 1,
    startTime: '09:00',
    endTime: '15:30',
    createdAt: hoursAgo(9),
  },
];

export const seedPosts: Post[] = [
  {
    id: 'p1',
    authorId: 'demo-student-002',
    authorName: '김하늘',
    content: '오늘 SQL 조인 실습 자료 공유합니다. 어려웠던 부분 댓글로 남겨 주세요!',
    likeCount: 7,
    commentCount: 3,
    createdAt: hoursAgo(4),
  },
  {
    id: 'p2',
    authorId: DemoAccounts.studentUid,
    authorName: '이수민',
    content: '스터디 3주차 정리 노션 링크 올려 뒀어요.',
    likeCount: 4,
    commentCount: 1,
    createdAt: daysAgo(1),
  },
];

export const seedPostComments: PostComment[] = [
  {
    id: 'pc1',
    postId: 'p1',
    authorId: DemoAccounts.studentUid,
    authorName: '이수민',
    content: '공유 감사합니다! 서브쿼리 부분을 다시 보고 있어요.',
    createdAt: hoursAgo(3),
  },
  {
    id: 'pc2',
    postId: 'p1',
    authorId: 'demo-student-004',
    authorName: '박서연',
    content: 'LEFT JOIN 예제가 특히 도움이 됐습니다.',
    createdAt: hoursAgo(2),
  },
  {
    id: 'pc3',
    postId: 'p1',
    authorId: 'demo-student-003',
    authorName: '정우진',
    content: '실습 문제도 같이 풀어 볼게요.',
    createdAt: hoursAgo(1),
  },
  {
    id: 'pc4',
    postId: 'p2',
    authorId: 'demo-student-002',
    authorName: '김하늘',
    content: '정리 잘 봤어요. 다음 스터디 때 같이 이야기해요!',
    createdAt: hoursAgo(20),
  },
];

export const seedTodos: Todo[] = [
  { id: 't1', title: '2차 프로젝트 주제 정리', isCompleted: false, createdAt: hoursAgo(20) },
  { id: 't2', title: 'SQL 스터디 복습', isCompleted: true, createdAt: daysAgo(2) },
  { id: 't3', title: '이력서 경력 섹션 채우기', isCompleted: false, createdAt: daysAgo(3) },
];

export const seedSubmissions: Submission[] = [
  {
    id: 'sub-demo-1',
    userId: 'demo-student-002',
    userDisplayName: '김하늘',
    title: 'PCCP Lv.2 취득',
    type: 'certification',
    status: 'pending',
    certType: 'PCCP',
    fileUrls: [],
    mileageGranted: false,
    mileageAmount: 0,
    submittedAt: hoursAgo(3),
  },
  {
    id: 'sub-demo-2',
    userId: 'demo-student-003',
    userDisplayName: '이도윤',
    title: 'Pandas groupby 정리',
    type: 'blog',
    status: 'pending',
    link: 'https://velog.io/@example/pandas-groupby',
    fileUrls: [],
    mileageGranted: false,
    mileageAmount: 0,
    submittedAt: hoursAgo(20),
  },
  {
    id: 'sub-demo-3',
    userId: DemoAccounts.studentUid,
    userDisplayName: '이수민',
    title: 'SQL 스터디 3주차',
    type: 'study',
    status: 'pending',
    weekNumber: 3,
    weekLabel: '3주차',
    isTeamStudy: true,
    fileUrls: [],
    mileageGranted: false,
    mileageAmount: 0,
    submittedAt: hoursAgo(26),
  },
  {
    id: 'sub-demo-4',
    userId: 'demo-student-004',
    userDisplayName: '박서연',
    title: 'SQLD 합격',
    type: 'certification',
    status: 'approved',
    certType: 'SQLD',
    fileUrls: [],
    mileageGranted: true,
    mileageAmount: 50000,
    submittedAt: daysAgo(3),
  },
  {
    id: 'sub-demo-5-1',
    userId: DemoAccounts.studentUid,
    userDisplayName: '이수민',
    title: '개강 전 학습인증 1회차',
    type: 'studyCert',
    status: 'approved',
    learningDate: daysAgo(52),
    learningContent: '파이썬 변수와 자료형 정리',
    fileUrls: [],
    mileageGranted: false,
    mileageAmount: 0,
    submittedAt: daysAgo(51),
  },
  {
    id: 'sub-demo-5-2',
    userId: DemoAccounts.studentUid,
    userDisplayName: '이수민',
    title: '개강 전 학습인증 2회차',
    type: 'studyCert',
    status: 'approved',
    learningDate: daysAgo(49),
    learningContent: '조건문·반복문 예제 풀이',
    fileUrls: [],
    mileageGranted: false,
    mileageAmount: 0,
    submittedAt: daysAgo(48),
  },
  {
    id: 'sub-demo-5-3',
    userId: DemoAccounts.studentUid,
    userDisplayName: '이수민',
    title: '개강 전 학습인증 3회차',
    type: 'studyCert',
    status: 'approved',
    learningDate: daysAgo(46),
    learningContent: '함수와 모듈 복습',
    fileUrls: [],
    mileageGranted: true,
    mileageAmount: 10000,
    submittedAt: daysAgo(45),
  },
  {
    id: 'sub-demo-5-4',
    userId: DemoAccounts.studentUid,
    userDisplayName: '이수민',
    title: '개강 전 학습인증 4회차',
    type: 'studyCert',
    status: 'approved',
    learningDate: daysAgo(43),
    learningContent: 'SQL SELECT 기본 문법',
    fileUrls: [],
    mileageGranted: false,
    mileageAmount: 0,
    submittedAt: daysAgo(42),
  },
  {
    id: 'sub-demo-5-5',
    userId: DemoAccounts.studentUid,
    userDisplayName: '이수민',
    title: '개강 전 학습인증 5회차',
    type: 'studyCert',
    status: 'approved',
    learningDate: daysAgo(40),
    learningContent: '파이썬 기초 문법 복습',
    fileUrls: [],
    mileageGranted: true,
    mileageAmount: 20000,
    submittedAt: daysAgo(38),
  },
  {
    id: 'sub-demo-6',
    userId: DemoAccounts.studentUid,
    userDisplayName: '이수민',
    title: '프리코스 퀴즈 1회차',
    type: 'precourseQuiz',
    status: 'rejected',
    quizScore: 55,
    reviewComment: '60점 미만입니다. 재응시 후 다시 제출해 주세요.',
    fileUrls: [],
    mileageGranted: false,
    mileageAmount: 0,
    submittedAt: daysAgo(45),
  },
];

// ── 출결 ──────────────────────────────────────────────

function seedAttendance(): Attendance[] {
  const rows: Attendance[] = [];
  const statuses = ['present', 'present', 'present', 'late', 'present'] as const;
  for (let i = 0; i < 30; i++) {
    const day = daysAgo(i);
    const weekday = day.getDay();
    if (weekday === 0 || weekday === 6) continue;
    for (const user of seedUsers.filter((u) => u.role === 'student' && u.isActive)) {
      const roll = (i + (user.seatNumber ?? 0)) % 11;
      const status =
        roll === 3 ? 'late' : roll === 7 ? 'officialLeave' : roll === 9 ? 'absent' : statuses[i % 5];
      rows.push({
        id: `att-${user.uid}-${dateKeyOf(day)}`,
        userId: user.uid,
        userDisplayName: user.displayName,
        type: 'checkIn',
        dateKey: dateKeyOf(day),
        status,
        checkInTime: status === 'late' ? '09:18' : '08:52',
        checkOutTime: status === 'absent' ? undefined : '18:02',
        statusSource: status === 'officialLeave' ? 'form' : 'demo',
        officialLeaveUsed: status === 'officialLeave' ? true : undefined,
        officialLeaveType: status === 'officialLeave' ? 'interview' : undefined,
      });
    }
  }
  return rows;
}

export const seedAttendances: Attendance[] = seedAttendance();

// ── 이력서 ─────────────────────────────────────────────

const demoResumeContent: ResumeContent = {
  basicInfo: {
    name: '이수민',
    phone: '',
    email: 'soomin.demo@gmail.com',
    birthDate: '2000-04-11',
    githubUrl: 'https://github.com/example-data',
    blogUrl: 'https://velog.io/@example-data',
  },
  coreCompetencies: {
    text:
      'Python·Pandas·SQL로 데이터 정제와 집계 파이프라인 구축, Airflow로 배치 스케줄링. ' +
      'Spark 기초와 Tensorflow 모델 학습 실습 경험.',
  },
  experience: [
    {
      id: 'exp1',
      company: '스타트업 인턴 (마케팅팀)',
      role: '데이터 분석 인턴',
      startDate: '2025-01',
      endDate: '2025-06',
      isCurrent: false,
      description: 'GA4 이벤트 로그를 정리해 주간 유입 리포트를 자동화했습니다.',
    },
  ],
  education: [
    {
      id: 'edu1',
      school: '경기전문대학',
      major: '빅데이터과(3년제)',
      startDate: '2020-03',
      endDate: '2023-02',
      status: '졸업',
    },
  ],
  techStack: [
    { id: 't1', name: 'Python', level: '고급' },
    { id: 't2', name: 'SQL', level: '고급' },
    { id: 't3', name: 'Pandas', level: '고급' },
    { id: 't4', name: 'Spark', level: '초급' },
    { id: 't5', name: 'Airflow', level: '중급' },
    { id: 't6', name: 'Tensorflow', level: '초급' },
  ],
  certifications: [
    { id: 'c1', name: 'SQLD', issuer: '한국데이터산업진흥원', acquiredDate: '2026-06' },
    { id: 'c2', name: 'ADsP', issuer: '한국데이터산업진흥원', acquiredDate: '2025-11' },
  ],
  awards: [
    {
      id: 'a1',
      name: '공공데이터 활용 아이디어 공모전 입선',
      organization: '한국지능정보사회진흥원',
      date: '2025-10',
      description: '지역별 대중교통 이용 데이터로 배차 개선안을 제안. 데이터 수집과 시각화를 맡았습니다.',
    },
  ],
  trainingExperience: [
    {
      id: 'tr1',
      course: 'SK네트웍스 Family AI 캠프 34기',
      organization: 'PLAYDATA',
      startDate: '2026-03',
      endDate: '2026-09',
      description: '데이터 분석·머신러닝·LLM 과정을 수료하며 팀 프로젝트 3회를 진행했습니다.',
    },
  ],
  otherActivities: [
    {
      id: 'ot1',
      name: 'SQL 스터디 리더',
      startDate: '2026-06',
      endDate: '2026-08',
      description: '주 1회 모여 쿼리 문제를 풀고 풀이를 공유했습니다.',
    },
  ],
  projects: [
    {
      id: 'prj1',
      name: '수강생 이탈 예측 모델',
      startDate: '2026-07',
      endDate: '2026-08',
      role: '데이터 수집·모델링',
      techStack: 'Python · scikit-learn · Pandas',
      description: '출결·과제 제출 로그로 이탈 위험군을 분류했습니다. F1 0.78.',
      url: 'https://github.com/example/churn',
    },
    {
      id: 'prj2',
      name: '강의 후기 감성 분석',
      startDate: '2026-09',
      endDate: '',
      role: '데이터 수집·전처리',
      techStack: 'Python · KoNLPy',
      description: '후기 3,000건을 수집해 긍·부정 키워드를 정리했습니다.',
      url: '',
    },
  ],
  selfIntroduction: {
    intro: {
      subtitle: '',
      body: '지표를 정의하고 근거를 모으는 일을 좋아합니다. 부트캠프에서 분석 과제를 맡을 때마다 먼저 물은 것은 「무엇을 재야 하는가」였습니다.',
    },
    motivation: { subtitle: '', body: '' },
    challenge: { subtitle: '', body: '' },
    growth: { subtitle: '', body: '' },
    strengthsWeaknesses: { subtitle: '', body: '' },
    aspiration: { subtitle: '', body: '' },
  },
};

export const seedResumes: Resume[] = [
  {
    id: 'r-demo-1',
    userId: DemoAccounts.studentUid,
    userDisplayName: '이수민',
    title: '데이터 분석가 지원 이력서',
    status: 'draft',
    content: demoResumeContent,
    sections: {
      basicInfo: true,
      coreCompetencies: true,
      experience: true,
      education: true,
      techStack: true,
      certifications: true,
      awards: true,
      trainingExperience: true,
      otherActivities: true,
      projects: true,
    },
    isBaseResume: true,
    feedbackCount: 0,
    lastSeenFeedbackCount: 0,
    readFeedbackIds: [],
    revisionCount: 1,
    updatedAt: hoursAgo(5),
  },
  {
    id: 'r-demo-2',
    userId: DemoAccounts.studentUid,
    userDisplayName: '이수민',
    title: '데이터 엔지니어 지원 이력서',
    status: 'feedbackRequested',
    content: demoResumeContent,
    sections: {
      basicInfo: true,
      coreCompetencies: true,
      education: true,
      techStack: true,
      certifications: true,
      awards: true,
      trainingExperience: true,
      otherActivities: true,
      projects: true,
      selfIntroduction: true,
    },
    isBaseResume: false,
    feedbackCount: 2,
    lastSeenFeedbackCount: 0,
    readFeedbackIds: [],
    revisionCount: 3,
    updatedAt: daysAgo(1),
  },
  {
    id: 'r-demo-3',
    userId: 'demo-student-002',
    userDisplayName: '김하늘',
    title: '백엔드 개발자 지원 이력서',
    status: 'feedbackRequested',
    content: {
      ...demoResumeContent,
      basicInfo: { ...demoResumeContent.basicInfo, name: '김하늘', email: 'haneul@gmail.com' },
      techStack: [
        { id: 't1', name: 'Python', level: '고급' },
        { id: 't2', name: 'Django', level: '중급' },
        { id: 't3', name: 'PostgreSQL', level: '초급' },
      ],
    },
    sections: { basicInfo: true, coreCompetencies: true, education: true, projects: true },
    isBaseResume: true,
    feedbackCount: 0,
    lastSeenFeedbackCount: 0,
    readFeedbackIds: [],
    revisionCount: 1,
    updatedAt: hoursAgo(30),
  },
  {
    id: 'r-demo-4',
    userId: 'demo-student-004',
    userDisplayName: '박서연',
    title: 'ML 엔지니어 지원 이력서',
    status: 'approved',
    content: {
      ...demoResumeContent,
      basicInfo: { ...demoResumeContent.basicInfo, name: '박서연', email: 'seoyeon@gmail.com' },
    },
    sections: { basicInfo: true, coreCompetencies: true, experience: true, projects: true },
    isBaseResume: true,
    feedbackCount: 4,
    lastSeenFeedbackCount: 4,
    readFeedbackIds: [],
    revisionCount: 5,
    updatedAt: daysAgo(4),
  },
];

export const seedResumeFeedbacks: ResumeFeedback[] = [
  {
    id: 'fb1',
    resumeId: 'r-demo-2',
    sectionKey: 'projects',
    content:
      '프로젝트 성과를 수치로 적어 주세요. "F1 0.78" 옆에 기준선(baseline) 대비 얼마나 올랐는지가 있으면 좋습니다.',
    authorId: DemoAccounts.instructorUid,
    authorName: '김강사',
    parentId: '',
    createdAt: hoursAgo(26),
  },
  {
    id: 'fb2',
    resumeId: 'r-demo-2',
    sectionKey: 'coreCompetencies',
    content: '첫 문장에 지원 직무를 명시하면 읽는 사람이 바로 맥락을 잡습니다.',
    authorId: DemoAccounts.instructorUid,
    authorName: '김강사',
    parentId: '',
    createdAt: hoursAgo(25),
  },
];

// ── 성취도 평가 ────────────────────────────────────────

export const seedAssessments: Assessment[] = [
  {
    id: 'a1',
    title: '34기 2차 성취도평가',
    tags: ['멀티모달', 'RAG'],
    questionCount: 4,
    // AI 출제 — 커리큘럼 11~15일차(멀티모달). 문항마다 근거 일수가 붙어 오답 → 복습으로 이어진다
    maxScore: 20,
    startAt: daysAgo(20),
    endAt: daysAhead(40),
    published: true,
    createdBy: DemoAccounts.instructorUid,
    createdAt: daysAgo(30),
  },
  {
    id: 'a2',
    title: '34기 1차 성취도평가',
    tags: ['Python', '기초'],
    questionCount: 2,
    maxScore: 10,
    startAt: daysAgo(80),
    endAt: daysAgo(40),
    published: true,
    createdBy: DemoAccounts.instructorUid,
    createdAt: daysAgo(90),
  },
  {
    id: 'a3',
    title: '34기 3차 성취도평가 (준비중)',
    tags: ['LLM'],
    questionCount: 0,
    maxScore: 0,
    startAt: daysAhead(30),
    endAt: daysAhead(60),
    published: false,
    createdBy: DemoAccounts.instructorUid,
    createdAt: daysAgo(2),
  },
];

export const seedAssessmentQuestions: Record<string, AssessmentQuestion[]> = {
  a1: [
    {
      id: 'q1',
      order: 0,
      type: 'multipleChoice',
      prompt: 'OpenCV로 읽은 이미지를 PIL로 넘기기 전에 해야 하는 처리는?',
      points: 5,
      choices: ['BGR → RGB로 채널 순서를 바꾼다', 'RGB → BGR로 채널 순서를 바꾼다', '흑백으로 바꾼다', '크기를 절반으로 줄인다'],
      correctIndex: 0,
      acceptedAnswers: [],
      explanation: 'OpenCV는 BGR, PIL은 RGB 순서를 쓴다. cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) 뒤에 Image.fromarray 로 넘긴다.',
      origin: 'ai',
      sourceDay: 15,
      sourceTopic: 'OpenCV 색상 채널 순서',
    },
    {
      id: 'q2',
      order: 1,
      type: 'shortAnswer',
      prompt: "'skiing_frame00300.jpg' 에서 프레임 번호를 정수로 뽑으면?",
      points: 5,
      choices: [],
      acceptedAnswers: ['300'],
      explanation: "정규식 _frame(\\d+)\\.jpg 로 '00300' 을 잡고 int() 로 바꾸면 300 이다.",
      origin: 'ai',
      sourceDay: 15,
      sourceTopic: '프레임 번호 추출',
    },
    {
      id: 'q3',
      order: 2,
      type: 'multipleChoice',
      prompt: 'CLIP에서 이미지와 텍스트 임베딩이 얼마나 비슷한지 재는 값은?',
      points: 5,
      choices: ['코사인 유사도', '유클리드 거리의 제곱', '픽셀 차이의 합', '문자열 길이 차이'],
      correctIndex: 0,
      acceptedAnswers: [],
      explanation: '두 임베딩의 내적을 크기의 곱으로 나눈 코사인 유사도로 가장 비슷한 텍스트를 고른다.',
      origin: 'ai',
      sourceDay: 11,
      sourceTopic: 'CLIP 코사인 유사도',
    },
    {
      id: 'q4',
      order: 3,
      type: 'shortAnswer',
      prompt: '입력 28×28, 커널 3, 스트라이드 1, 패딩 0인 합성곱의 출력 한 변 크기는?',
      points: 5,
      choices: [],
      acceptedAnswers: ['26'],
      explanation: '(입력 + 2×패딩 − 커널) ÷ 스트라이드 + 1 = (28 − 3) + 1 = 26.',
      origin: 'ai',
      sourceDay: 11,
      sourceTopic: '합성곱 출력 크기',
    },
  ],
  a2: [
    {
      id: 'q1',
      order: 0,
      type: 'multipleChoice',
      prompt: 'Python에서 리스트를 만드는 기호는?',
      points: 5,
      choices: ['()', '[]', '{}', '<>'],
      correctIndex: 1,
      acceptedAnswers: [],
      origin: 'manual',
    },
    {
      id: 'q2',
      order: 1,
      type: 'shortAnswer',
      prompt: 'None 타입을 나타내는 키워드는?',
      points: 5,
      choices: [],
      acceptedAnswers: ['None'],
      origin: 'manual',
    },
  ],
  a3: [],
};

export const seedAssessmentSubmissions: AssessmentSubmission[] = [
  {
    id: `a2_${DemoAccounts.studentUid}`,
    assessmentId: 'a2',
    userId: DemoAccounts.studentUid,
    userDisplayName: '이수민',
    answers: {
      q1: { value: 1, autoScore: 5, finalScore: 5, isCorrect: true },
      q2: { value: 'None', autoScore: 5, finalScore: 5, isCorrect: true },
    },
    autoTotalScore: 10,
    totalScore: 10,
    submittedAt: daysAgo(45),
    gradedAt: daysAgo(45),
  },
  {
    id: `a1_${DemoAccounts.studentUid}`,
    assessmentId: 'a1',
    userId: DemoAccounts.studentUid,
    userDisplayName: '이수민',
    answers: {
      q1: { value: 0, autoScore: 5, finalScore: 5, isCorrect: true },
      q2: { value: '00300', autoScore: 0, finalScore: 0, isCorrect: false },
      q3: { value: 0, autoScore: 5, finalScore: 5, isCorrect: true },
      q4: { value: '28', autoScore: 0, finalScore: 0, isCorrect: false },
    },
    autoTotalScore: 10,
    totalScore: 10,
    submittedAt: daysAgo(1),
    gradedAt: daysAgo(1),
  },
  {
    id: 'a1_demo-student-002',
    assessmentId: 'a1',
    userId: 'demo-student-002',
    userDisplayName: '김하늘',
    answers: {
      q1: { value: 1, autoScore: 5, finalScore: 5, isCorrect: true },
      q2: { value: 'target', autoScore: 0, finalScore: 0, isCorrect: false },
    },
    autoTotalScore: 5,
    totalScore: 5,
    submittedAt: daysAgo(6),
  },
  {
    id: 'a1_demo-student-004',
    assessmentId: 'a1',
    userId: 'demo-student-004',
    userDisplayName: '박서연',
    answers: {
      q1: { value: 0, autoScore: 0, finalScore: 0, isCorrect: false },
      q2: { value: 'label', autoScore: 5, finalScore: 5, isCorrect: true },
    },
    autoTotalScore: 5,
    totalScore: 5,
    submittedAt: daysAgo(5),
  },
];

// ── 학습실 ────────────────────────────────────────────

export const seedInflearnPackages: InflearnPackage[] = [
  {
    id: 'pkg1',
    title: '프로그래밍과 데이터 기초 예복습',
    subject: '프로그래밍과 데이터 기초',
    type: 'review',
    summary: '첫번째 교과목 예복습에 필요한 6개 강의입니다. 파이썬 기초를 반복 학습해 주세요.',
    isPublished: true,
    sortOrder: 1,
    publishedAt: daysAgo(70),
    courses: [],
    units: [
      {
        name: 'Python',
        courses: [
          { title: '단 60분! 파이썬 핵심 개념 초압축 강의', url: 'https://www.inflearn.com' },
          { title: '문과생도, 비전공자도, 누구나 배울 수 있는 파이썬(Python)!', url: 'https://www.inflearn.com' },
        ],
      },
      {
        name: 'Data base',
        courses: [
          { title: 'Do it! SQL 입문', url: 'https://www.inflearn.com' },
          { title: '초보자를 위한 BigQuery(SQL) 입문', url: 'https://www.inflearn.com' },
        ],
      },
      {
        name: 'Web Crawling',
        courses: [
          { title: '[신규 개정판] 이것이 진짜 크롤링이다 - 기본편', url: 'https://www.inflearn.com' },
          { title: '[Python 실전] 웹크롤링과 데이터분석', url: 'https://www.inflearn.com' },
        ],
      },
    ],
  },
  {
    id: 'pkg2',
    title: 'LLM 미리보기',
    subject: 'LLM',
    type: 'bonus',
    summary: '다가올 LLM 교과목 예습용 강의입니다.',
    isPublished: true,
    sortOrder: 3,
    publishedAt: daysAgo(70),
    units: [],
    courses: [
      { title: '입문자를 위한 LangChain 기초', url: 'https://www.inflearn.com' },
      { title: 'TypeScript로 시작하는 LangChain - LLM & RAG 입문', url: 'https://www.inflearn.com' },
    ],
  },
];

export const seedYoutubeRecommendations: YoutubeRecommendation[] = [
  {
    id: 'yt1',
    title: 'Flutter 입문 — 30분 핵심 정리',
    youtubeUrl: 'https://www.youtube.com/watch?v=VPvVD8t02U8',
    videoId: 'VPvVD8t02U8',
    tags: ['Flutter', 'Dart'],
    description: 'Flutter 위젯·상태관리 입문 영상',
    isPublished: true,
    sortOrder: 1,
    createdAt: daysAgo(70),
  },
  {
    id: 'yt2',
    title: 'Python 기초 — 변수와 자료형',
    youtubeUrl: 'https://www.youtube.com/watch?v=kqtD5dpn9C8',
    videoId: 'kqtD5dpn9C8',
    tags: ['Python', 'Django', 'FastAPI'],
    description: '파이썬 문법 기초',
    isPublished: true,
    sortOrder: 2,
    createdAt: daysAgo(70),
  },
  {
    id: 'yt3',
    title: 'SQL 입문 — SELECT부터 JOIN까지',
    youtubeUrl: 'https://www.youtube.com/watch?v=HXV3zeQKqGY',
    videoId: 'HXV3zeQKqGY',
    tags: ['SQL', 'MySQL', 'PostgreSQL'],
    description: 'SQL 기초 쿼리',
    isPublished: true,
    sortOrder: 3,
    createdAt: daysAgo(70),
  },
  {
    id: 'yt4',
    title: 'Docker 컨테이너 개념 한눈에',
    youtubeUrl: 'https://www.youtube.com/watch?v=fqMOX6JJhGo',
    videoId: 'fqMOX6JJhGo',
    tags: ['Docker', 'CI/CD', 'AWS'],
    description: 'Docker 입문',
    isPublished: true,
    sortOrder: 4,
    createdAt: daysAgo(70),
  },
];

export const seedStudySources: StudySource[] = [
  {
    id: 'src1',
    title: '34기 강의 자료 저장소',
    repoUrl: 'https://github.com/example/skn34-materials',
    branch: 'main',
    allowedPrefixes: ['python/', 'sql/', 'ml/'],
    isActive: true,
    sortOrder: 1,
  },
];

export const seedStudyNotes: StudyNote[] = [
  {
    id: 'note1',
    sourceId: 'src1',
    status: 'done',
    scopeType: 'prefix',
    scopeValue: 'python/day01',
    scopeKey: 'prefix_python_day01',
    reportMarkdown:
      '## 1일차 요약\n\n- 변수와 자료형: 파이썬은 동적 타입이다.\n- 조건문·반복문의 들여쓰기 규칙\n- 리스트 컴프리헨션 기초',
    reviewMarkdown:
      '## 복습 문제\n\n1. `list`와 `tuple`의 차이는?\n2. `for`문에서 `range(1, 10, 2)`가 만드는 값은?',
    files: [{ path: 'python/day01.md', commit: 'a1b2c3d' }],
    createdAt: daysAgo(60),
  },
  {
    id: 'note-0915',
    sourceId: 'src1',
    status: 'done',
    scopeType: 'date',
    scopeValue: '2026-09-15',
    scopeKey: '2026-09-15',
    reportMarkdown: [
      '## 오늘의 핵심 한 문장',
      '',
      '동영상을 일정 간격의 프레임으로 잘라 캡션을 붙이고, 그 캡션을 벡터로 검색해 답한다.',
      '',
      '## 핵심 코드와 개념',
      '',
      '- `cv2.VideoCapture` 로 프레임을 읽고 `idx % frame_interval == 0` 인 것만 저장',
      '- OpenCV 는 BGR, PIL 은 RGB — `cv2.COLOR_BGR2RGB` 로 바꿔 넘김',
      "- 파일명 `skiing_frame00300.jpg` 에서 `re.search(r'_frame(\\d+)\\.jpg')` 로 번호를 뽑음",
    ].join('\n'),
    reviewMarkdown: '## 복습 문제\n\n이 수업의 복습 문제는 연습장에서 풀 수 있어요.',
    files: [
      { path: '05_multimodal_rag/02_video_rag_frame_extraction.ipynb', commit: '947b8eb' },
      { path: '05_multimodal_rag/03_video_rag_image_caption.ipynb', commit: '947b8eb' },
    ],
    createdAt: daysAgo(7),
  },
];

export const seedCurriculumSheets: CurriculumSheet[] = [
  {
    id: 'cs1',
    title: '34기 커리큘럼',
    fileName: 'curriculum_34.csv',
    uploadedBy: DemoAccounts.instructorUid,
    uploadedByName: '김강사',
    uploadedAt: daysAgo(90),
    rows: [
      { dayIndex: 1, dateLabel: '1일차', subject: '프로그래밍과 데이터 기초', topic: 'Python', detail: '변수, 자료형, 조건문, 반복문', order: 0 },
      { dayIndex: 2, dateLabel: '2일차', subject: '프로그래밍과 데이터 기초', topic: 'Python', detail: '함수, 모듈, 파일 I/O', order: 1 },
      { dayIndex: 8, dateLabel: '8일차', subject: '프로그래밍과 데이터 기초', topic: 'Database', detail: 'SQL 기초, JOIN', order: 2 },
      { dayIndex: 9, dateLabel: '9일차', subject: '프로그래밍과 데이터 기초', topic: 'Web Crawling', detail: 'requests, BeautifulSoup', order: 3 },
      // 수업일자가 실제 날짜로 들어온 행 — 성취도평가 오답이 그날 노트·복습 문제로 이어진다(reviewLinks.ts)
      { dayIndex: 11, dateLabel: '2026년 9월 11일', subject: '멀티모달', topic: 'CNN · ViT · CLIP', detail: 'CNN, ViT, CLIP 임베딩과 코사인 유사도', order: 4 },
      { dayIndex: 14, dateLabel: '2026년 9월 14일', subject: '멀티모달', topic: 'BLIP · Diffusion', detail: 'BLIP, Stable Diffusion, VQA', order: 5 },
      { dayIndex: 15, dateLabel: '2026년 9월 15일', subject: '멀티모달', topic: '영상 RAG', detail: '프레임 추출, 캡션, 검색', order: 6 },
      { dayIndex: 21, dateLabel: '21일차', subject: '머신러닝', topic: 'Supervised', detail: '회귀·분류, 과적합', order: 7 },
      { dayIndex: 35, dateLabel: '35일차', subject: 'LLM', topic: 'RAG', detail: '임베딩, 벡터DB, 검색 증강 생성', order: 8 },
    ],
  },
];

// ── 설문 · 제출 ────────────────────────────────────────

export const seedFormTasks: FormTask[] = [
  {
    id: 'form1',
    title: '34기 OT 참여 설문',
    description: '온보딩 설문입니다. 노션 가이드를 참고해 작성해 주세요.',
    formUrl: 'https://docs.google.com/forms/d/e/example/viewform',
    notionGuideUrl: 'https://notion.so/example-guide',
    dueAt: daysAhead(7),
    published: true,
    responseCount: 5,
    createdAt: daysAgo(3),
  },
  {
    id: 'form2',
    title: '이력서 클리닉 신청',
    description: '현직자 이력서 클리닉 신청 폼입니다. 선착순 10명.',
    formUrl: 'https://docs.google.com/forms/d/e/example2/viewform',
    dueAt: daysAhead(2),
    published: true,
    responseCount: 8,
    createdAt: daysAgo(5),
  },
  {
    id: 'form3',
    title: '중간 만족도 조사',
    description: '과정 중간 만족도 조사입니다.',
    formUrl: 'https://docs.google.com/forms/d/e/example3/viewform',
    dueAt: daysAgo(4),
    published: true,
    responseCount: 8,
    createdAt: daysAgo(20),
  },
];

export const seedFormResponses: FormResponse[] = [
  {
    id: 'fr1',
    userId: DemoAccounts.studentUid,
    userEmail: 'soomin.demo@gmail.com',
    userDisplayName: '이수민',
    taskId: 'form3',
    source: 'google',
    submittedAt: daysAgo(6),
  },
  {
    id: 'fr2',
    userId: 'demo-student-002',
    userEmail: 'demo-student-002@gmail.com',
    userDisplayName: '김하늘',
    taskId: 'form1',
    source: 'google',
    submittedAt: daysAgo(1),
  },
];

// ── 마일리지 ───────────────────────────────────────────

export const seedMileageProducts: MileageProduct[] = [
  {
    id: 'mp1',
    name: '스타벅스 아메리카노 T',
    description: '기프티콘으로 발송됩니다.',
    category: 'gifticon',
    pricingType: 'fixed',
    fixedPrice: 4500,
    isActive: true,
    sortOrder: 1,
  },
  {
    id: 'mp2',
    name: '혼자 공부하는 머신러닝+딥러닝',
    description: '도서 구매 지원. 링크를 첨부해 주세요.',
    category: 'book',
    pricingType: 'fixed',
    fixedPrice: 26100,
    isActive: true,
    sortOrder: 2,
  },
  {
    id: 'mp3',
    name: '인프런 강의 (직접 입력)',
    description: '수강하고 싶은 강의 링크와 금액을 직접 입력합니다.',
    category: 'onlineCourse',
    pricingType: 'variable',
    isActive: true,
    sortOrder: 3,
  },
  {
    id: 'mp4',
    name: 'CU 모바일 상품권 5천원',
    description: '편의점 기프티콘.',
    category: 'gifticon',
    pricingType: 'fixed',
    fixedPrice: 5000,
    isActive: false,
    sortOrder: 4,
  },
];

export const seedMileageTransactions: MileageTransaction[] = [
  {
    id: 'mt1',
    userId: DemoAccounts.studentUid,
    userDisplayName: '이수민',
    amount: 50000,
    reason: '스터디 미션 달성 (1단위기간)',
    type: 'accrual',
    createdAt: daysAgo(30),
  },
  {
    id: 'mt2',
    userId: DemoAccounts.studentUid,
    userDisplayName: '이수민',
    amount: 30000,
    reason: '개강 전 학습인증 5회',
    type: 'accrual',
    createdAt: daysAgo(38),
  },
  {
    id: 'mt3',
    userId: DemoAccounts.studentUid,
    userDisplayName: '이수민',
    amount: -4500,
    reason: '기프티콘 구매 — 스타벅스 아메리카노 T',
    type: 'redemption',
    createdAt: daysAgo(10),
  },
  {
    id: 'mt4',
    userId: DemoAccounts.studentUid,
    userDisplayName: '이수민',
    amount: 60000,
    reason: '블로그 미션 3단위기간',
    type: 'accrual',
    createdAt: daysAgo(6),
  },
  {
    id: 'mt5',
    userId: 'demo-student-004',
    userDisplayName: '박서연',
    amount: 50000,
    reason: '자격증 취득 — SQLD',
    type: 'accrual',
    createdAt: daysAgo(3),
  },
];

export const seedPurchaseRequests: PurchaseRequest[] = [
  {
    id: 'pr1',
    userId: 'demo-student-003',
    userDisplayName: '이도윤',
    items: [
      {
        productId: 'mp2',
        productName: '혼자 공부하는 머신러닝+딥러닝',
        category: 'book',
        pricingType: 'fixed',
        unitPrice: 26100,
        quantity: 1,
      },
    ],
    totalAmount: 26100,
    status: 'pending',
    createdAt: hoursAgo(8),
  },
  {
    id: 'pr2',
    userId: DemoAccounts.studentUid,
    userDisplayName: '이수민',
    items: [
      {
        productId: 'mp1',
        productName: '스타벅스 아메리카노 T',
        category: 'gifticon',
        pricingType: 'fixed',
        unitPrice: 4500,
        quantity: 1,
      },
    ],
    totalAmount: 4500,
    status: 'approved',
    createdAt: daysAgo(10),
  },
];

export const seedMileageSettings: MileageSettings = {
  categoryLimits: { ...MileageDefaultLimits },
  accrualRules: { certification: 50000, study: 50000, blog: 20000 },
  updatedAt: daysAgo(30),
};

// ── 좌석 ──────────────────────────────────────────────

/**
 * 좌석 배치 — 원본 강의실 모양 그대로다.
 *
 * 맨 위 가운데에 강사석, 맨 아래 가운데에 출입문. 그 사이로 세 자리짜리 책상이
 * 가운데 통로를 두고 좌우로 다섯 줄 선다. 번호는 줄마다 왼쪽 책상부터 이어진다.
 * 틀 편집 화면과 같은 연산으로 쌓아 올려, 손으로 만든 칸과 어긋날 일이 없다.
 */
const SEAT_ROWS = 5;

function buildSeedRoom(): SeatingRoom {
  let grid = emptyGrid(SEAT_ROWS + 2, 10);
  grid = placeFixture(grid, 'instructor', 0, 4);
  grid = placeFixture(grid, 'door', SEAT_ROWS + 1, 4);
  let desk = 1;
  for (let r = 1; r <= SEAT_ROWS; r += 1) {
    for (const col of [1, 5]) {
      grid = placeTable(grid, r, col, 3, `desk-${desk}`);
      desk += 1;
    }
  }
  return {
    ...grid,
    id: 'room-302',
    cohortId: DemoConfig.cohortId,
    roomNumber: '302호',
    createdAt: daysAgo(30),
    updatedAt: daysAgo(7),
  };
}

export const seedSeatingRooms: SeatingRoom[] = [buildSeedRoom()];

// 퇴소한 학생은 앉히지 않는다. 앉혀 두면 배정 인원이 재원 수를 넘어 저장이 막힌다.
const seededSeatOwners = seedUsers.filter(
  (u) => u.role === 'student' && u.isActive && u.seatNumber !== undefined,
);

/** 302호 배치 — 확정한 지 하루라 대시보드에도 미니 배치표가 뜬다(확정 후 3일간). */
export const seedSeatingAssignments: SeatingAssignment[] = [
  {
    roomId: 'room-302',
    cohortId: DemoConfig.cohortId,
    status: 'published',
    assignments: Object.fromEntries(seededSeatOwners.map((u) => [String(u.seatNumber), u.uid])),
    seatNames: Object.fromEntries(seededSeatOwners.map((u) => [String(u.seatNumber), u.displayName])),
    publishedAt: daysAgo(1),
    updatedAt: daysAgo(1),
  },
];

/** 기수별로 학생에게 보이는 강의실 — seatingMeta/default */
export const seedSeatingMeta: Record<string, { publishedRoomId?: string }> = {
  [DemoConfig.cohortId]: { publishedRoomId: 'room-302' },
};

export const seedProjectTeams: ProjectTeam[] = [];

// ── 자격 시험 일정 ─────────────────────────────────────

export const seedQualExams: QualExamSchedule[] = [
  {
    implYy: '2026',
    implSeq: 1,
    qualgbCd: '정기',
    qualgbNm: '정보처리기사',
    description: '국가기술자격 정기 시험',
    docRegStartDt: '20260120',
    docRegEndDt: '20260123',
    docExamStartDt: '20260224',
    docExamEndDt: '20260224',
    docPassDt: '20260312',
    pracRegStartDt: '20260325',
    pracRegEndDt: '20260328',
    pracExamStartDt: '20260420',
    pracExamEndDt: '20260505',
    pracPassDt: '20260612',
  },
  {
    implYy: '2026',
    implSeq: 2,
    qualgbCd: '정기',
    qualgbNm: '빅데이터분석기사',
    description: '필기·실기 정기 시험',
    docRegStartDt: '20260803',
    docRegEndDt: '20260807',
    docExamStartDt: '20260906',
    docExamEndDt: '20260906',
    docPassDt: '20260925',
    pracRegStartDt: '20261005',
    pracRegEndDt: '20261009',
    pracExamStartDt: '20261121',
    pracExamEndDt: '20261121',
    pracPassDt: '20261218',
  },
  {
    implYy: '2026',
    implSeq: 3,
    qualgbCd: '상시',
    qualgbNm: 'SQLD',
    description: '상시 시험 (한국데이터산업진흥원)',
    docRegStartDt: '20261012',
    docRegEndDt: '20261016',
    docExamStartDt: '20261114',
    docExamEndDt: '20261114',
    docPassDt: '20261205',
  },
];

// ── LLMOps ────────────────────────────────────────────

const aiModels = ['claude-sonnet-5', 'claude-haiku-4-5-20251001'];
const aiTypes = ['assessment', 'resume_review', 'student_chatbot', 'job_recommend', 'job_chat'];

/** 기능마다 쓰는 프롬프트가 다르다. LLMOps의 「프롬프트 버전별」이 이 이름으로 묶인다. */
const aiPromptVersions = [
  'assess_q_v2',
  'resume_review_v1',
  'student_chatbot_v2',
  'job_recommend_v1',
  'job_chat_v1',
];

export const seedAiLogs: AiGenerationLog[] = Array.from({ length: 42 }, (_, i) => {
  const failed = i % 17 === 0;
  return {
    id: `ai-${i}`,
    type: aiTypes[i % aiTypes.length],
    promptVersion: aiPromptVersions[i % aiTypes.length],
    model: aiModels[i % aiModels.length],
    generatedCount: i % aiTypes.length === 0 ? 5 : 1,
    // 사람이 그대로 받은 것, 고쳐 쓴 것, 도움이 됐다고 한 것
    adoptedCount: failed ? 0 : i % 3 === 0 ? 1 : 0,
    editedCount: failed ? 0 : i % 5 === 0 ? 1 : 0,
    usefulCount: failed ? 0 : i % 4 === 0 ? 1 : 0,
    latencyMs: 700 + ((i * 137) % 2600),
    status: failed ? 'error' : 'success',
    errorMessage: failed ? 'upstream timeout' : undefined,
    tokenIn: 1200 + ((i * 311) % 5000),
    tokenOut: 300 + ((i * 97) % 1500),
    createdByName: i % 2 === 0 ? '김강사' : 'PLAYDATA 관리자',
    createdAt: hoursAgo(i * 5),
  };
});

export const seedAiEvals: AiEvalResult[] = [
  { id: 'ev1', promptVersion: 'student_chatbot_v2', suite: 'chatbot_lab', model: 'claude-sonnet-5', passRate: 0.9, caseCount: 40, avgLatencyMs: 2310, ranAt: daysAgo(2) },
  { id: 'ev2', promptVersion: 'assess_q_v2', suite: 'question_lab', model: 'claude-sonnet-5', passRate: 0.84, caseCount: 25, avgLatencyMs: 1980, ranAt: daysAgo(12) },
  { id: 'ev3', promptVersion: 'resume_review_v1', suite: 'coach_safety', model: 'claude-haiku-4-5-20251001', passRate: 1, caseCount: 18, avgLatencyMs: 860, ranAt: daysAgo(3) },
  { id: 'ev4', promptVersion: 'job_recommend_v1', suite: 'routing_lab', model: 'claude-sonnet-5', passRate: 0.78, caseCount: 40, avgLatencyMs: 1440, ranAt: daysAgo(1) },
];

/**
 * 데모 학생의 복습 문제 풀이 기록 — 「다시 풀 문제」와 진행률이 처음부터 보이게.
 * 9/11 은 모두 통과, 9/14 는 출력 예상(2)·디버깅(4)을 틀린 채 두었다. 9/15 는 아직 안 풂.
 */
export const seedPracticeAttempts: PracticeAttempt[] = [
  ...[0, 1, 2, 3, 4, 5].map((index) => ({
    id: `pa-seed-11-${index}`,
    uid: DemoAccounts.studentUid,
    setId: 'ps-mm-0911',
    index,
    passed: true,
    tries: index === 3 ? 2 : 1,
    answeredAt: daysAgo(9),
  })),
  ...[
    { index: 0, passed: true, tries: 1 },
    { index: 1, passed: true, tries: 1 },
    { index: 2, passed: false, tries: 2 },
    { index: 3, passed: true, tries: 1 },
    { index: 4, passed: false, tries: 1 },
  ].map((a) => ({
    id: `pa-seed-14-${a.index}`,
    uid: DemoAccounts.studentUid,
    setId: 'ps-mm-0914',
    answeredAt: daysAgo(6),
    ...a,
  })),
];

/** 데모 신고 — 다른 학생 하나가 9/14 문제 5(디버깅)를 신고해 둔 상태. 데모 학생이 한 번 더 신고하면 2명이 되어 숨겨진다. */
export const seedPracticeReports: PracticeReport[] = [
  {
    id: 'pr-seed-1',
    uid: 'demo-student-004',
    setId: 'ps-mm-0914',
    index: 4,
    reason: 'tests',
    note: '문제 문장에는 없는 입력이 테스트에 있어요',
    createdAt: daysAgo(2),
  },
];
