import { MaterialIcons } from '@expo/vector-icons';
import { navFor } from '@web/app/navigation';
import { RoutePaths } from '@web/app/routePaths';
import type { UserRole } from '@web/domain/types';

import type { IconName } from '../ui/kit';

/** 메뉴 이름 · 순서 · 아이콘은 웹 `navigation.ts` 하나만 고친다 — 앱은 경로만 갈아 끼운다. */
export interface AppNavItem {
  label: string;
  icon: IconName;
  href: string;
  webPath: string;
}

export interface AppNavSection {
  id: string;
  title?: string;
  items: AppNavItem[];
}

const R = RoutePaths;

const appPaths: Record<string, string> = {
  // 학생
  [R.dashboard]: '/(student)/(tabs)',
  [R.resume]: '/(student)/resume',
  [R.jobApply]: '/(student)/apply',
  [R.studyRoom]: '/(student)/(tabs)/study',
  [R.board]: '/(student)/(tabs)/board',
  [R.seating]: '/(student)/seating',
  [R.attendanceRequest]: '/(student)/attendance',
  [R.forms]: '/(student)/forms',
  [R.qualExams]: '/(student)/qual',
  [R.records]: '/(student)/records',
  [R.mileage]: '/(student)/(tabs)/mileage',
  [R.assessments]: '/(student)/exams',
  [R.settings]: '/(student)/settings',
  [R.myPage]: '/(student)/mypage',
  // 강사
  [R.instructor]: '/(instructor)',
  [R.instructorResumes]: '/(instructor)/resumes',
  [R.instructorBoard]: '/(instructor)/board',
  [R.instructorAssessments]: '/(instructor)/exams',
  [R.instructorCurriculum]: '/(instructor)/curriculum',
  [R.instructorPractice]: '/(instructor)/desktop/practice',
  [R.instructorStudySources]: '/(instructor)/sources',
  [R.instructorMyPage]: '/(instructor)/mypage',
  [R.instructorSettings]: '/(instructor)/settings',
  // 관리자
  [R.admin]: '/(admin)',
  [R.adminCohorts]: '/(admin)/cohorts',
  [R.adminStudents]: '/(admin)/students',
  [R.adminCounsel]: '/(admin)/counsel',
  [R.adminInstructors]: '/(admin)/instructors',
  [R.adminAttendance]: '/(admin)/attendance',
  [R.adminSeatPresence]: '/(admin)/presence',
  [R.adminSeating]: '/(admin)/rooms',
  [R.adminAssessments]: '/(admin)/exams',
  [R.adminRecords]: '/(admin)/records',
  [R.adminResumes]: '/(admin)/resumes',
  [R.adminFormTasks]: '/(admin)/forms',
  [R.adminStudyRoom]: '/(admin)/study',
  [R.adminBoard]: '/(admin)/board',
  [R.adminAlertPopups]: '/(admin)/alerts',
  [R.adminMileage]: '/(admin)/mileage',
  [R.adminQuests]: '/(admin)/quests',
  [R.adminAiQuality]: '/(admin)/ai',
  [R.adminSettings]: '/(admin)/settings',
};

/** 웹 서랍에는 없지만(웹은 떠 있는 버튼 · 게시판 안 탭) 앱에서는 메뉴로 연다 */
const appOnly: Partial<Record<UserRole, AppNavSection>> = {
  admin: {
    id: 'app',
    title: '앱 전용',
    items: [
      { label: '예약 공지', icon: 'schedule-send', href: '/(admin)/scheduled', webPath: '' },
      { label: 'AI 어시스턴트', icon: 'smart-toy', href: '/(admin)/assistant', webPath: '' },
    ],
  },
};

const fallbackIcons: Record<string, IconName> = { folder_code: 'folder' };

function toIcon(name: string): IconName {
  const icon = name.replace(/_/g, '-');
  if (icon in MaterialIcons.glyphMap) return icon as IconName;
  return fallbackIcons[name] ?? 'circle';
}

function desktopPath(role: UserRole): string {
  return role === 'admin' ? '/(admin)/desktop' : role === 'instructor' ? '/(instructor)/desktop' : '/(student)/desktop';
}

export function appNav(role: UserRole): AppNavSection[] {
  const sections: AppNavSection[] = navFor(role).map((section) => ({
    id: section.id,
    title: section.title,
    items: section.items.map((item) => ({
      label: item.label,
      icon: toIcon(item.icon),
      // 앱에 아직 없는 새 메뉴는 「PC 에서 이용해 주세요」로 보낸다
      href: appPaths[item.path] ?? desktopPath(role),
      webPath: item.path,
    })),
  }));
  const extra = appOnly[role];
  return extra ? [...sections, extra] : sections;
}

/** 웹 메뉴의 이름을 경로로 찾는다 — 탭 · 바로가기 이름을 웹과 같게 둔다 */
export function navLabel(webPath: string, fallback: string): string {
  for (const role of ['student', 'instructor', 'admin'] as const) {
    for (const section of navFor(role)) {
      const hit = section.items.find((item) => item.path === webPath);
      if (hit) return hit.label;
    }
  }
  return fallback;
}

export function navIcon(webPath: string, fallback: IconName): IconName {
  for (const role of ['student', 'instructor', 'admin'] as const) {
    for (const section of navFor(role)) {
      const hit = section.items.find((item) => item.path === webPath);
      if (hit) return toIcon(hit.icon);
    }
  }
  return fallback;
}
