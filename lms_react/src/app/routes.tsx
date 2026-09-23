import type { ReactElement } from 'react';

import { lazyNamed, tracked } from './lazyNamed';

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

/*
 * 강사 · 관리자 화면과 파이썬 연습장은 필요할 때 받는다(화면 파일마다 청크 하나).
 * 학생은 강사·관리자 코드를 받지 않고, CodeMirror(원본 1MB 남짓)는 연습장을 열 때만 온다.
 * 받는 동안은 App 의 Suspense 가 자리 표시를 띄운다.
 */
const loadPythonPlaygroundScreen = tracked(() => import('../features/practice/PythonPlaygroundScreen'));
const PythonPlaygroundScreen = lazyNamed(loadPythonPlaygroundScreen, 'PythonPlaygroundScreen');
const loadInstructorAttendanceScreen = tracked(() => import('../features/instructor/InstructorAttendanceScreen'));
const InstructorAttendanceScreen = lazyNamed(loadInstructorAttendanceScreen, 'InstructorAttendanceScreen');
const loadInstructorBoardScreen = tracked(() => import('../features/instructor/InstructorBoardScreen'));
const InstructorBoardScreen = lazyNamed(loadInstructorBoardScreen, 'InstructorBoardScreen');
const loadInstructorAssessmentScreens = tracked(() => import('../features/instructor/InstructorAssessmentScreens'));
const InstructorAssessmentDetailScreen = lazyNamed(loadInstructorAssessmentScreens, 'InstructorAssessmentDetailScreen');
const InstructorAssessmentFormScreen = lazyNamed(loadInstructorAssessmentScreens, 'InstructorAssessmentFormScreen');
const InstructorAssessmentSubmissionScreen = lazyNamed(loadInstructorAssessmentScreens, 'InstructorAssessmentSubmissionScreen');
const InstructorAssessmentsScreen = lazyNamed(loadInstructorAssessmentScreens, 'InstructorAssessmentsScreen');
const loadInstructorCurriculumScreen = tracked(() => import('../features/instructor/InstructorCurriculumScreen'));
const InstructorCurriculumScreen = lazyNamed(loadInstructorCurriculumScreen, 'InstructorCurriculumScreen');
const loadInstructorPracticeScreen = tracked(() => import('../features/instructor/InstructorPracticeScreen'));
const InstructorPracticeScreen = lazyNamed(loadInstructorPracticeScreen, 'InstructorPracticeScreen');
const loadInstructorStudySourcesScreen = tracked(() => import('../features/instructor/InstructorStudySourcesScreen'));
const InstructorStudySourcesScreen = lazyNamed(loadInstructorStudySourcesScreen, 'InstructorStudySourcesScreen');
const loadReviewerResumesScreen = tracked(() => import('../features/resume/ReviewerResumesScreen'));
const ReviewerResumesScreen = lazyNamed(loadReviewerResumesScreen, 'ReviewerResumesScreen');
const loadNoticeFormScreen = tracked(() => import('../features/notices/NoticeFormScreen'));
const NoticeFormScreen = lazyNamed(loadNoticeFormScreen, 'NoticeFormScreen');
const loadAdminDashboardScreen = tracked(() => import('../features/admin/AdminDashboardScreen'));
const AdminDashboardScreen = lazyNamed(loadAdminDashboardScreen, 'AdminDashboardScreen');
const loadAdminPeopleScreens = tracked(() => import('../features/admin/AdminPeopleScreens'));
const AdminCohortFormScreen = lazyNamed(loadAdminPeopleScreens, 'AdminCohortFormScreen');
const AdminCohortsScreen = lazyNamed(loadAdminPeopleScreens, 'AdminCohortsScreen');
const AdminInstructorCreateScreen = lazyNamed(loadAdminPeopleScreens, 'AdminInstructorCreateScreen');
const AdminInstructorsScreen = lazyNamed(loadAdminPeopleScreens, 'AdminInstructorsScreen');
const AdminStudentDetailScreen = lazyNamed(loadAdminPeopleScreens, 'AdminStudentDetailScreen');
const AdminStudentFormScreen = lazyNamed(loadAdminPeopleScreens, 'AdminStudentFormScreen');
const AdminStudentsScreen = lazyNamed(loadAdminPeopleScreens, 'AdminStudentsScreen');
const loadAdminAttendanceScreens = tracked(() => import('../features/admin/AdminAttendanceScreens'));
const AdminAttendanceScreen = lazyNamed(loadAdminAttendanceScreens, 'AdminAttendanceScreen');
const AdminSeatPresenceScreen = lazyNamed(loadAdminAttendanceScreens, 'AdminSeatPresenceScreen');
const AdminSeatingScreen = lazyNamed(loadAdminAttendanceScreens, 'AdminSeatingScreen');
const loadAdminRecordsScreen = tracked(() => import('../features/admin/AdminRecordsScreen'));
const AdminRecordsScreen = lazyNamed(loadAdminRecordsScreen, 'AdminRecordsScreen');
const loadAdminBoardScreens = tracked(() => import('../features/admin/AdminBoardScreens'));
const AdminAlertPopupFormScreen = lazyNamed(loadAdminBoardScreens, 'AdminAlertPopupFormScreen');
const AdminBoardScreen = lazyNamed(loadAdminBoardScreens, 'AdminBoardScreen');
const AdminScheduledNoticeFormScreen = lazyNamed(loadAdminBoardScreens, 'AdminScheduledNoticeFormScreen');
const loadAdminLearningScreens = tracked(() => import('../features/admin/AdminLearningScreens'));
const AdminFormTaskFormScreen = lazyNamed(loadAdminLearningScreens, 'AdminFormTaskFormScreen');
const AdminFormTasksScreen = lazyNamed(loadAdminLearningScreens, 'AdminFormTasksScreen');
const AdminInflearnPackageFormScreen = lazyNamed(loadAdminLearningScreens, 'AdminInflearnPackageFormScreen');
const AdminStudyRoomScreen = lazyNamed(loadAdminLearningScreens, 'AdminStudyRoomScreen');
const loadAdminMileageScreens = tracked(() => import('../features/admin/AdminMileageScreens'));
const AdminMileageAdjustScreen = lazyNamed(loadAdminMileageScreens, 'AdminMileageAdjustScreen');
const AdminMileageHubScreen = lazyNamed(loadAdminMileageScreens, 'AdminMileageHubScreen');
const AdminMileageProductFormScreen = lazyNamed(loadAdminMileageScreens, 'AdminMileageProductFormScreen');
const AdminMileageProductsScreen = lazyNamed(loadAdminMileageScreens, 'AdminMileageProductsScreen');
const AdminMileageSettingsScreen = lazyNamed(loadAdminMileageScreens, 'AdminMileageSettingsScreen');
const AdminPurchaseRequestsScreen = lazyNamed(loadAdminMileageScreens, 'AdminPurchaseRequestsScreen');
const loadAdminAiQualityScreen = tracked(() => import('../features/admin/AdminAiQualityScreen'));
const AdminAiQualityScreen = lazyNamed(loadAdminAiQualityScreen, 'AdminAiQualityScreen');

/** 로그인한 역할이 곧 쓸 화면 청크 — 셸이 한가할 때 미리 받는다. 연습장(CodeMirror)은 크니 열 때 받는다 */
export const prefetchByRole: Record<string, (() => Promise<unknown>)[]> = {
  student: [],
  instructor: [
    loadInstructorAttendanceScreen,
    loadInstructorBoardScreen,
    loadInstructorAssessmentScreens,
    loadInstructorCurriculumScreen,
    loadInstructorPracticeScreen,
    loadInstructorStudySourcesScreen,
    loadReviewerResumesScreen,
    loadNoticeFormScreen,
  ],
  admin: [
    loadInstructorAttendanceScreen,
    loadInstructorAssessmentScreens,
    loadReviewerResumesScreen,
    loadNoticeFormScreen,
    loadAdminDashboardScreen,
    loadAdminPeopleScreens,
    loadAdminAttendanceScreens,
    loadAdminRecordsScreen,
    loadAdminBoardScreens,
    loadAdminLearningScreens,
    loadAdminMileageScreens,
    loadAdminAiQualityScreen,
  ],
};

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
  { path: RoutePaths.instructorStudySources, element: <InstructorStudySourcesScreen />, roles: instructor },
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
