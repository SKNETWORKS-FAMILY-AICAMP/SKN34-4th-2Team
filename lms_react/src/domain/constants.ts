/** 라벨·코드 상수 — Flutter `lib/core/constants/*.dart` */
import type { MileagePricingType, RecordType, ResumeContent, UserRole } from './types';

export const RoleLabels: Record<UserRole, string> = {
  admin: '관리자',
  instructor: '강사',
  student: '학생',
};

// ── 출결 ──────────────────────────────────────────────

export const AttendanceStatuses = [
  'present',
  'late',
  'absent',
  'officialLeave',
  'earlyLeave',
  'outing',
] as const;

export const AttendanceLabels: Record<string, string> = {
  present: '출석',
  late: '지각',
  absent: '결석',
  officialLeave: '공가',
  earlyLeave: '조퇴',
  outing: '외출',
};

/** 상태색 — CSS 변수 이름으로 돌려준다. 어두운 화면은 같은 이름이 다른 값이다. */
export const AttendanceColorVars: Record<string, string> = {
  present: 'var(--success)',
  late: 'var(--warning)',
  absent: 'var(--error)',
  officialLeave: 'var(--info)',
  earlyLeave: 'var(--primary)',
  outing: '#0f766e',
};

export function attendanceLabel(status?: string | null): string {
  if (status === undefined || status === null || status === '') return '-';
  return AttendanceLabels[status] ?? status;
}

export const OfficialLeaveLabels: Record<string, string> = {
  vacation: '휴가',
  sick: '병가',
  interview: '면접',
  reserve: '예비군/민방위',
  cert: '자격증 응시',
  other: '기타',
};

export const AttendanceForm = {
  url: 'https://forms.gle/HFraX15h7PB7iMic7',
  dailyNoticeTitle: '[출결] 오늘 예외 출결 제출',
  dailyNoticeContent:
    '정상 출석 외에 지각 / 조퇴 / 외출 / 결석(공가 포함) 예정이 있으면 ' +
    '반드시 오늘 날짜로 구글폼을 제출해 주세요.',
} as const;

// ── 교시 ──────────────────────────────────────────────

export interface ClassPeriod {
  id: string;
  startHour: number;
  label: string;
}

/** 09:00 ~ 17:50, 정각 시작 :50 종료, 12:50~14:00 점심 */
export const ClassPeriods: ClassPeriod[] = [
  { id: '09', startHour: 9, label: '09:00' },
  { id: '10', startHour: 10, label: '10:00' },
  { id: '11', startHour: 11, label: '11:00' },
  { id: '12', startHour: 12, label: '12:00' },
  { id: '14', startHour: 14, label: '14:00' },
  { id: '15', startHour: 15, label: '15:00' },
  { id: '16', startHour: 16, label: '16:00' },
  { id: '17', startHour: 17, label: '17:00' },
];

/** 지금 교시. 쉬는시간(:50 이후)·점심에는 null. */
export function currentPeriod(now: Date = new Date()): ClassPeriod | null {
  if (now.getMinutes() >= 50) return null;
  return ClassPeriods.find((p) => p.startHour === now.getHours()) ?? null;
}

/** 가장 최근에 시작한 교시. 자리 확인 화면의 기본 선택. */
export function nearestPeriod(now: Date = new Date()): ClassPeriod {
  const started = ClassPeriods.filter((p) => p.startHour <= now.getHours());
  return started.length > 0 ? started[started.length - 1] : ClassPeriods[0];
}

// ── 기록실 ────────────────────────────────────────────

export const RecordTypeLabels: Record<RecordType, string> = {
  certification: '자격증',
  study: '스터디',
  blog: '블로그',
  studyCert: '학습인증',
  precourseQuiz: '프리코스 퀴즈',
};

export const RecordTypeDescriptions: Record<RecordType, string> = {
  certification:
    'PCCE / PCCP / PCSQL 합격·레벨 취득 증빙을 제출하세요. 승인 시 코딩테스트 미션 규칙(최대 50,000M)으로 적립됩니다.',
  study:
    '팀 스터디만 인정됩니다(개인 스터디 제외). 오프라인 스터디 사진(날짜·시간 확인 가능)을 주 1회 이상 제출하세요. 1~2단위기간 주 1회 이상 승인 시 50,000M이 적립됩니다.',
  blog:
    '안내된 블로그 양식에 맞춰 주차별 링크를 제출하세요. 단위기간 내 모든 주차를 연속 작성·승인받으면 단위기간당 20,000M(최대 5단위·100,000M)이 적립됩니다.',
  studyCert:
    '개강 전 학습인증(예수학제)입니다. 학습일자·학습 내용·인증 사진을 올려 주세요. 승인 횟수에 따라 3회 10,000 / 5회 30,000 / 10회 50,000M이 적립됩니다.',
  precourseQuiz:
    '프리코스 퀴즈 응시 결과(점수·증빙)를 제출하세요. 60점 이상 승인 횟수에 따라 1회 10,000 / 3회 30,000 / 5회 50,000M이 적립됩니다.',
};

export const CertKinds = ['PCCE', 'PCCP', 'PCSQL'] as const;

export const SubmissionStatusLabels: Record<string, string> = {
  pending: '대기',
  approved: '승인',
  rejected: '반려',
};

// ── 마일리지 ───────────────────────────────────────────

export const MileageCategoryLabels: Record<string, string> = {
  gifticon: '기프티콘',
  book: '도서',
  onlineCourse: '인터넷 강의',
};

export const MileageCategories = ['gifticon', 'book', 'onlineCourse'] as const;

export const MileagePricingLabels: Record<MileagePricingType, string> = {
  fixed: '정가',
  custom: '직접 입력',
};

export const PurchaseRequestStatusLabels: Record<string, string> = {
  pending: '대기',
  approved: '승인',
  rejected: '반려',
  modify_requested: '수정 요청',
  cancelled: '취소',
};

export const MileageDefaultLimits: Record<string, number> = {
  gifticon: 200000,
  book: 100000,
  onlineCourse: 200000,
};

// ── 기수 ──────────────────────────────────────────────

export const CohortStatusLabels: Record<string, string> = {
  planned: '예정',
  active: '진행중',
  closed: '종료',
};

/** resume_model.dart의 statusLabel 그대로 */
export const ResumeStatusLabels: Record<string, string> = {
  draft: '작성 중',
  submitted: '피드백 요청',
  feedbackRequested: '피드백 요청',
  approved: '승인 완료',
};

/** 이력서 섹션 — core/constants/app_constants.dart 그대로 (순서까지) */
export const ResumeSectionKeys = [
  'basicInfo',
  'coreCompetencies',
  'experience',
  'education',
  'techStack',
  'certifications',
  'awards',
  'trainingExperience',
  'otherActivities',
  'projects',
  'selfIntroduction',
] as const;

export const ResumeSectionLabels: Record<string, string> = {
  basicInfo: '기본정보',
  coreCompetencies: '핵심역량/강점',
  experience: '경력사항',
  education: '학력사항',
  techStack: '기술스택',
  certifications: '자격사항',
  awards: '수상내역',
  trainingExperience: '교육경험',
  otherActivities: '기타활동',
  projects: '프로젝트 경험',
  selfIntroduction: '자기소개서',
};

/** 자기소개서 문항 — resume_content.dart의 ResumeSelfIntroLabels */
export const SelfIntroKeys = [
  'intro',
  'motivation',
  'challenge',
  'growth',
  'strengthsWeaknesses',
  'aspiration',
] as const;

export const SelfIntroLabels: Record<string, string> = {
  intro: '자기소개',
  motivation: '지원동기',
  challenge: '직무와 관련된 경험 중 어려움을 극복한 사례',
  growth: '성장과정',
  strengthsWeaknesses: '직무와 관련된 성격의 장단점',
  aspiration: '지원한 회사에 대한 포부',
};

/** 기술 숙련도 */
/**
 * 채운 섹션 판정 — resume_content.dart의 computeSections()
 *
 * 저장된 `sections` 맵을 믿지 않고 내용에서 다시 센다. 원본이 그렇게 한다:
 * 글자를 지우면 체크도 같이 풀려야 하기 때문이다.
 */
export function computeSections(c: ResumeContent): Record<string, boolean> {
  const any = <T>(list: T[], filled: (item: T) => boolean) => list.some(filled);
  const has = (v: string) => v.trim() !== '';
  const intro = c.selfIntroduction;
  return {
    basicInfo: has(c.basicInfo.name) && has(c.basicInfo.email),
    coreCompetencies: has(c.coreCompetencies.text),
    experience: any(c.experience, (e) => has(e.company)),
    education: any(c.education, (e) => has(e.school)),
    techStack: any(c.techStack, (e) => has(e.name)),
    certifications: any(c.certifications, (e) => has(e.name)),
    awards: any(c.awards, (e) => has(e.name)),
    trainingExperience: any(c.trainingExperience, (e) => has(e.course)),
    otherActivities: any(c.otherActivities, (e) => has(e.name)),
    projects: any(c.projects, (e) => has(e.name)),
    selfIntroduction: SelfIntroKeys.some((k) => has(intro[k].body)),
  };
}
