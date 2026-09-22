import { AdminTargets, InstructorTargets, StudentTargets } from '../tour/targets';
import { RoutePaths } from './routePaths';
import type { UserRole } from '../domain/types';

export interface NavItem {
  /** Material Symbols 이름 — Flutter의 Icons.* 와 같은 것을 고른다. */
  icon: string;
  label: string;
  path: string;
  /** 온보딩 투어 타깃 id (투어가 비추는 메뉴만) */
  targetId?: string;
}

export interface NavSection {
  id: string;
  title?: string;
  items: NavItem[];
  /** 관리자 사이드바는 그룹을 접었다 편다. */
  collapsible?: boolean;
}

/** 학생 레일 — features/shell/main_shell_screen.dart */
export const studentNav: NavSection[] = [
  {
    id: 'main',
    items: [
      { icon: 'dashboard', label: '대시보드', path: RoutePaths.dashboard, targetId: StudentTargets.navDashboard },
      { icon: 'description', label: '이력서 관리', path: RoutePaths.resume, targetId: StudentTargets.navResume },
      { icon: 'menu_book', label: '학습실', path: RoutePaths.studyRoom, targetId: StudentTargets.navStudyRoom },
      { icon: 'forum', label: '게시판', path: RoutePaths.board, targetId: StudentTargets.navBoard },
      { icon: 'event_seat', label: '자리 배치', path: RoutePaths.seating, targetId: StudentTargets.navSeating },
      { icon: 'ballot', label: '설문 · 제출', path: RoutePaths.forms, targetId: StudentTargets.navForms },
      { icon: 'workspace_premium', label: '자격 시험 일정', path: RoutePaths.qualExams, targetId: StudentTargets.navQualExams },
      { icon: 'history', label: '기록실', path: RoutePaths.records, targetId: StudentTargets.navRecords },
      { icon: 'card_giftcard', label: '마일리지', path: RoutePaths.mileage, targetId: StudentTargets.navMileage },
      { icon: 'quiz', label: '성취도평가', path: RoutePaths.assessments, targetId: StudentTargets.navAssessments },
      { icon: 'settings', label: '설정', path: RoutePaths.settings },
    ],
  },
];

/** 강사 레일 — features/instructor/shell/instructor_shell_screen.dart */
export const instructorNav: NavSection[] = [
  {
    id: 'main',
    items: [
      { icon: 'fact_check', label: '자리 확인', path: RoutePaths.instructor, targetId: InstructorTargets.navAttendance },
      { icon: 'description', label: '이력서관리', path: RoutePaths.instructorResumes, targetId: InstructorTargets.navResumes },
      { icon: 'forum', label: '게시물관리', path: RoutePaths.instructorBoard, targetId: InstructorTargets.navBoard },
      { icon: 'quiz', label: '성취도평가', path: RoutePaths.instructorAssessments, targetId: InstructorTargets.navAssessments },
      { icon: 'table_chart', label: '커리큘럼', path: RoutePaths.instructorCurriculum, targetId: InstructorTargets.navCurriculum },
      { icon: 'flag', label: '복습 문제', path: RoutePaths.instructorPractice },
      { icon: 'person', label: '마이페이지', path: RoutePaths.instructorMyPage, targetId: InstructorTargets.navMyPage },
      { icon: 'settings', label: '설정', path: RoutePaths.instructorSettings },
    ],
  },
];

/** 관리자 사이드바 — 그룹까지 admin_shell_screen.dart 그대로 */
export const adminNav: NavSection[] = [
  {
    id: 'home',
    items: [{ icon: 'dashboard', label: '대시보드', path: RoutePaths.admin, targetId: AdminTargets.navDashboard }],
  },
  {
    id: 'people',
    title: '운영 · 인원',
    collapsible: true,
    items: [
      { icon: 'calendar_month', label: '기수 관리', path: RoutePaths.adminCohorts, targetId: AdminTargets.navCohorts },
      { icon: 'groups', label: '학생 관리', path: RoutePaths.adminStudents, targetId: AdminTargets.navStudents },
      { icon: 'badge', label: '강사 관리', path: RoutePaths.adminInstructors, targetId: AdminTargets.navInstructors },
    ],
  },
  {
    id: 'attendance',
    title: '출결 · 공간',
    collapsible: true,
    items: [
      { icon: 'fact_check', label: '출석 관리', path: RoutePaths.adminAttendance, targetId: AdminTargets.navAttendance },
      { icon: 'event_available', label: '자리 확인', path: RoutePaths.adminSeatPresence, targetId: AdminTargets.navSeatPresence },
      { icon: 'event_seat', label: '좌석 배치', path: RoutePaths.adminSeating, targetId: AdminTargets.navSeating },
    ],
  },
  {
    id: 'learning',
    title: '학습 · 평가',
    collapsible: true,
    items: [
      { icon: 'quiz', label: '성취도 평가', path: RoutePaths.adminAssessments, targetId: AdminTargets.navAssessments },
      { icon: 'history', label: '기록실', path: RoutePaths.adminRecords, targetId: AdminTargets.navRecords },
      { icon: 'description', label: '이력서', path: RoutePaths.adminResumes, targetId: AdminTargets.navResumes },
      { icon: 'ballot', label: '설문 · 제출', path: RoutePaths.adminFormTasks, targetId: AdminTargets.navFormTasks },
      { icon: 'menu_book', label: '학습실', path: RoutePaths.adminStudyRoom, targetId: AdminTargets.navStudyRoom },
    ],
  },
  {
    id: 'engage',
    title: '소통 · 리워드',
    collapsible: true,
    items: [
      { icon: 'forum', label: '게시판', path: RoutePaths.adminBoard, targetId: AdminTargets.navBoard },
      { icon: 'card_giftcard', label: '마일리지', path: RoutePaths.adminMileage, targetId: AdminTargets.navMileage },
    ],
  },
  {
    id: 'system',
    title: '시스템',
    collapsible: true,
    items: [
      { icon: 'analytics', label: 'LLMOps', path: RoutePaths.adminAiQuality, targetId: AdminTargets.navAiQuality },
      { icon: 'settings', label: '설정', path: RoutePaths.adminSettings },
    ],
  },
];

export function navFor(role: UserRole): NavSection[] {
  switch (role) {
    case 'admin':
      return adminNav;
    case 'instructor':
      return instructorNav;
    default:
      return studentNav;
  }
}

/**
 * 메뉴 선택 표시 — 루트 경로는 exact match, 나머지는 하위 경로까지 포함.
 *
 * `/admin`이 `/admin/students`를 품으면 사이드바에서 대시보드와 학생 관리가
 * 동시에 켜진다.
 */
export function isNavSelected(location: string, path: string): boolean {
  const roots: string[] = [RoutePaths.dashboard, RoutePaths.admin, RoutePaths.instructor];
  if (roots.includes(path)) return location === path;
  return location === path || location.startsWith(`${path}/`);
}
