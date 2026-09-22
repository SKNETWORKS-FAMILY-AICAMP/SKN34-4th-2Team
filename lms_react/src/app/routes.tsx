import type { ReactElement } from 'react';

import { RoutePaths } from './routePaths';
import { DashboardScreen } from '../features/dashboard/DashboardScreen';
import { BoardScreen } from '../features/board/BoardScreen';
import { RecordsScreen, RecordFormRoute, RecordTypeSelectScreen } from '../features/records/RecordsScreen';
import { FormTasksScreen } from '../features/forms/FormTasksScreen';
import { QualExamScreen } from '../features/qual/QualExamScreen';
import { SeatingScreen } from '../features/seating/SeatingScreen';
import {
  StudyNoteSourceScreen,
  StudyNotesScreen,
  StudyRoomScreen,
} from '../features/study/StudyRoomScreen';
import { PythonPlaygroundScreen } from '../features/practice/PythonPlaygroundScreen';
import {
  MileageCartScreen,
  MileageScreen,
  MileageShopScreen,
} from '../features/mileage/MileageScreens';
import {
  AssessmentResultScreen,
  AssessmentTakeScreen,
  AssessmentsScreen,
} from '../features/assessments/AssessmentScreens';
import { ResumeScreen } from '../features/resume/ResumeScreens';
import { ResumeEditScreen } from '../features/resume/ResumeEditScreen';
import { MyPageScreen } from '../features/mypage/MyPageScreen';
import { SettingsScreen } from '../features/settings/SettingsScreen';
import { InstructorAttendanceScreen } from '../features/instructor/InstructorAttendanceScreen';
import { InstructorBoardScreen } from '../features/instructor/InstructorBoardScreen';
import {
  InstructorAssessmentDetailScreen,
  InstructorAssessmentFormScreen,
  InstructorAssessmentSubmissionScreen,
  InstructorAssessmentsScreen,
} from '../features/instructor/InstructorAssessmentScreens';
import { InstructorCurriculumScreen } from '../features/instructor/InstructorCurriculumScreen';
import { InstructorPracticeScreen } from '../features/instructor/InstructorPracticeScreen';
import { ReviewerResumesScreen } from '../features/resume/ReviewerResumesScreen';
import { NoticeFormScreen } from '../features/notices/NoticeFormScreen';
import { AdminDashboardScreen } from '../features/admin/AdminDashboardScreen';
import {
  AdminCohortFormScreen,
  AdminCohortsScreen,
  AdminInstructorCreateScreen,
  AdminInstructorsScreen,
  AdminStudentDetailScreen,
  AdminStudentFormScreen,
  AdminStudentsScreen,
} from '../features/admin/AdminPeopleScreens';
import {
  AdminAttendanceScreen,
  AdminSeatPresenceScreen,
  AdminSeatingScreen,
} from '../features/admin/AdminAttendanceScreens';
import { AdminRecordsScreen } from '../features/admin/AdminRecordsScreen';
import {
  AdminAlertPopupFormScreen,
  AdminBoardScreen,
  AdminScheduledNoticeFormScreen,
} from '../features/admin/AdminBoardScreens';
import {
  AdminFormTaskFormScreen,
  AdminFormTasksScreen,
  AdminInflearnPackageFormScreen,
  AdminStudyRoomScreen,
} from '../features/admin/AdminLearningScreens';
import {
  AdminMileageAdjustScreen,
  AdminMileageHubScreen,
  AdminMileageProductFormScreen,
  AdminMileageProductsScreen,
  AdminMileageSettingsScreen,
  AdminPurchaseRequestsScreen,
} from '../features/admin/AdminMileageScreens';
import { AdminAiQualityScreen } from '../features/admin/AdminAiQualityScreen';

export interface AppRoute {
  path: string;
  element: ReactElement;
  /** 비우면 모든 역할이 들어갈 수 있다. */
  roles?: string[];
}

const student = ['student'];

/** 학생 셸 라우트 — Flutter ShellRoute의 학생 가지 */
export const studentRoutes: AppRoute[] = [
  { path: RoutePaths.dashboard, element: <DashboardScreen />, roles: student },
  { path: RoutePaths.board, element: <BoardScreen />, roles: student },
  { path: RoutePaths.records, element: <RecordsScreen />, roles: student },
  { path: RoutePaths.recordsCreate, element: <RecordTypeSelectScreen />, roles: student },
  { path: '/records/create/:type', element: <RecordFormRoute />, roles: student },
  { path: RoutePaths.forms, element: <FormTasksScreen />, roles: student },
  { path: RoutePaths.qualExams, element: <QualExamScreen />, roles: student },
  { path: RoutePaths.seating, element: <SeatingScreen />, roles: student },
  { path: RoutePaths.studyRoom, element: <StudyRoomScreen />, roles: student },
  { path: RoutePaths.studyRoomNotes, element: <StudyNotesScreen />, roles: student },
  { path: RoutePaths.studyRoomPlayground, element: <PythonPlaygroundScreen />, roles: student },
  { path: '/study-room/notes/:sourceId', element: <StudyNoteSourceScreen />, roles: student },
  { path: RoutePaths.mileage, element: <MileageScreen />, roles: student },
  { path: RoutePaths.mileageShop, element: <MileageShopScreen />, roles: student },
  { path: RoutePaths.mileageCart, element: <MileageCartScreen />, roles: student },
  { path: RoutePaths.assessments, element: <AssessmentsScreen />, roles: student },
  { path: RoutePaths.resume, element: <ResumeScreen />, roles: student },
  { path: RoutePaths.myPage, element: <MyPageScreen />, roles: student },
  { path: RoutePaths.settings, element: <SettingsScreen />, roles: student },
];

const instructor = ['instructor'];

/** 강사 셸 라우트 */
export const instructorRoutes: AppRoute[] = [
  { path: RoutePaths.instructor, element: <InstructorAttendanceScreen />, roles: instructor },
  { path: RoutePaths.instructorResumes, element: <ReviewerResumesScreen />, roles: instructor },
  { path: RoutePaths.instructorBoard, element: <InstructorBoardScreen />, roles: instructor },
  {
    path: RoutePaths.instructorBoardCreate,
    element: <NoticeFormScreen backTo={RoutePaths.instructorBoard} />,
    roles: instructor,
  },
  {
    path: '/instructor/board/:noticeId/edit',
    element: <NoticeFormScreen backTo={RoutePaths.instructorBoard} />,
    roles: instructor,
  },
  { path: RoutePaths.instructorAssessments, element: <InstructorAssessmentsScreen />, roles: instructor },
  { path: RoutePaths.instructorPractice, element: <InstructorPracticeScreen />, roles: instructor },
  {
    path: RoutePaths.instructorAssessmentsCreate,
    element: <InstructorAssessmentFormScreen />,
    roles: instructor,
  },
  {
    path: '/instructor/assessments/:assessmentId',
    element: <InstructorAssessmentDetailScreen />,
    roles: instructor,
  },
  {
    path: '/instructor/assessments/:assessmentId/edit',
    element: <InstructorAssessmentFormScreen />,
    roles: instructor,
  },
  {
    path: '/instructor/assessments/:assessmentId/submissions/:submissionId',
    element: <InstructorAssessmentSubmissionScreen />,
    roles: instructor,
  },
  { path: RoutePaths.instructorCurriculum, element: <InstructorCurriculumScreen />, roles: instructor },
  { path: RoutePaths.instructorMyPage, element: <MyPageScreen />, roles: instructor },
  { path: RoutePaths.instructorSettings, element: <SettingsScreen />, roles: instructor },
];

const admin = ['admin'];

/** 관리자 셸 라우트 — 사이드바 15개 메뉴 + 하위 화면 */
export const adminRoutes: AppRoute[] = [
  { path: RoutePaths.admin, element: <AdminDashboardScreen />, roles: admin },

  { path: RoutePaths.adminCohorts, element: <AdminCohortsScreen />, roles: admin },
  { path: RoutePaths.adminCohortsCreate, element: <AdminCohortFormScreen />, roles: admin },
  { path: '/admin/cohorts/:cohortId/edit', element: <AdminCohortFormScreen />, roles: admin },

  { path: RoutePaths.adminStudents, element: <AdminStudentsScreen />, roles: admin },
  { path: RoutePaths.adminStudentsCreate, element: <AdminStudentFormScreen />, roles: admin },
  { path: '/admin/students/:studentUid', element: <AdminStudentDetailScreen />, roles: admin },
  { path: '/admin/students/:studentUid/edit', element: <AdminStudentFormScreen />, roles: admin },

  { path: RoutePaths.adminInstructors, element: <AdminInstructorsScreen />, roles: admin },
  { path: RoutePaths.adminInstructorsCreate, element: <AdminInstructorCreateScreen />, roles: admin },

  { path: RoutePaths.adminAttendance, element: <AdminAttendanceScreen />, roles: admin },
  { path: RoutePaths.adminSeatPresence, element: <AdminSeatPresenceScreen />, roles: admin },
  { path: RoutePaths.adminSeating, element: <AdminSeatingScreen />, roles: admin },

  { path: RoutePaths.adminAssessments, element: <InstructorAssessmentsScreen readOnly />, roles: admin },
  {
    path: '/admin/assessments/:assessmentId',
    element: <InstructorAssessmentDetailScreen readOnly />,
    roles: admin,
  },
  {
    path: '/admin/assessments/:assessmentId/submissions/:submissionId',
    element: <InstructorAssessmentSubmissionScreen canEditScores={false} />,
    roles: admin,
  },

  { path: RoutePaths.adminRecords, element: <AdminRecordsScreen />, roles: admin },
  { path: RoutePaths.adminResumes, element: <ReviewerResumesScreen canApprove />, roles: admin },

  { path: RoutePaths.adminFormTasks, element: <AdminFormTasksScreen />, roles: admin },
  { path: RoutePaths.adminFormTasksCreate, element: <AdminFormTaskFormScreen />, roles: admin },
  { path: '/admin/form-tasks/:taskId/edit', element: <AdminFormTaskFormScreen />, roles: admin },

  { path: RoutePaths.adminStudyRoom, element: <AdminStudyRoomScreen />, roles: admin },
  { path: RoutePaths.adminStudyRoomCreate, element: <AdminInflearnPackageFormScreen />, roles: admin },
  { path: '/admin/study-room/:packageId', element: <AdminInflearnPackageFormScreen />, roles: admin },

  { path: RoutePaths.adminBoard, element: <AdminBoardScreen />, roles: admin },
  {
    path: RoutePaths.adminBoardNoticeCreate,
    element: <NoticeFormScreen backTo={RoutePaths.adminBoard} />,
    roles: admin,
  },
  {
    path: '/admin/board/:noticeId/edit',
    element: <NoticeFormScreen backTo={RoutePaths.adminBoard} />,
    roles: admin,
  },
  {
    path: RoutePaths.adminBoardScheduledCreate,
    element: <AdminScheduledNoticeFormScreen />,
    roles: admin,
  },
  {
    path: '/admin/board/scheduled/:scheduledId/edit',
    element: <AdminScheduledNoticeFormScreen />,
    roles: admin,
  },
  {
    path: RoutePaths.adminBoardAlertPopupCreate,
    element: <AdminAlertPopupFormScreen />,
    roles: admin,
  },
  {
    path: '/admin/board/alert-popups/:popupId/edit',
    element: <AdminAlertPopupFormScreen />,
    roles: admin,
  },

  { path: RoutePaths.adminMileage, element: <AdminMileageHubScreen />, roles: admin },
  { path: RoutePaths.adminMileageProducts, element: <AdminMileageProductsScreen />, roles: admin },
  { path: RoutePaths.adminMileageProductsCreate, element: <AdminMileageProductFormScreen />, roles: admin },
  { path: '/admin/mileage/products/:productId/edit', element: <AdminMileageProductFormScreen />, roles: admin },
  { path: RoutePaths.adminMileageRequests, element: <AdminPurchaseRequestsScreen />, roles: admin },
  { path: RoutePaths.adminMileageAdjust, element: <AdminMileageAdjustScreen />, roles: admin },
  { path: RoutePaths.adminMileageSettings, element: <AdminMileageSettingsScreen />, roles: admin },

  { path: RoutePaths.adminAiQuality, element: <AdminAiQualityScreen />, roles: admin },
  { path: RoutePaths.adminMyPage, element: <MyPageScreen />, roles: admin },
  { path: RoutePaths.adminSettings, element: <SettingsScreen />, roles: admin },
];

export const appRoutes: AppRoute[] = [...studentRoutes, ...instructorRoutes, ...adminRoutes];

/**
 * 셸 밖 라우트 — app_router.dart에서 ShellRoute 위에 놓인 세 개.
 *
 * 왼쪽 레일도 상단 바도 없이 화면 전체를 쓴다. 이력서 편집은 학생·강사·관리자가
 * 같은 주소로 들어오므로 역할을 걸지 않는다.
 */
export const fullScreenRoutes: AppRoute[] = [
  { path: '/resume/:resumeId/edit', element: <ResumeEditScreen /> },
  { path: '/assessments/:assessmentId/take', element: <AssessmentTakeScreen />, roles: student },
  { path: '/assessments/:assessmentId/result', element: <AssessmentResultScreen />, roles: student },
];
