import type { UserRole } from '../domain/types';

/** 경로 상수 — Flutter `core/routing/route_paths.dart` 그대로 */
export const RoutePaths = {
  login: '/login',
  changePassword: '/change-password',

  // 학생 셸
  dashboard: '/',
  resume: '/resume',
  studyRoom: '/study-room',
  studyRoomNotes: '/study-room/notes',
  board: '/board',
  records: '/records',
  recordsCreate: '/records/create',
  recordsCreateCert: '/records/create/certification',
  recordsCreateStudy: '/records/create/study',
  recordsCreateBlog: '/records/create/blog',
  recordsCreateStudyCert: '/records/create/study-cert',
  recordsCreatePrecourseQuiz: '/records/create/precourse-quiz',
  mileage: '/mileage',
  mileageShop: '/mileage/shop',
  mileageCart: '/mileage/shop/cart',
  assessments: '/assessments',
  myPage: '/my-page',
  settings: '/settings',
  forms: '/forms',
  qualExams: '/qual-exams',
  seating: '/seating',

  // 관리자 셸
  admin: '/admin',
  adminCohorts: '/admin/cohorts',
  adminCohortsCreate: '/admin/cohorts/create',
  adminStudents: '/admin/students',
  adminStudentsCreate: '/admin/students/create',
  adminInstructors: '/admin/instructors',
  adminInstructorsCreate: '/admin/instructors/create',
  adminAttendance: '/admin/attendance',
  adminSeatPresence: '/admin/seat-presence',
  adminSeating: '/admin/seating',
  adminAssessments: '/admin/assessments',
  adminRecords: '/admin/records',
  adminResumes: '/admin/resumes',
  adminFormTasks: '/admin/form-tasks',
  adminFormTasksCreate: '/admin/form-tasks/create',
  adminStudyRoom: '/admin/study-room',
  adminStudyRoomCreate: '/admin/study-room/create',
  adminBoard: '/admin/board',
  adminBoardNoticeCreate: '/admin/board/create',
  adminBoardScheduledCreate: '/admin/board/scheduled/create',
  adminBoardAlertPopupCreate: '/admin/board/alert-popups/create',
  adminMileage: '/admin/mileage',
  adminMileageProducts: '/admin/mileage/products',
  adminMileageProductsCreate: '/admin/mileage/products/create',
  adminMileageRequests: '/admin/mileage/requests',
  adminMileageAdjust: '/admin/mileage/adjust',
  adminMileageSettings: '/admin/mileage/settings',
  adminAiQuality: '/admin/ai-quality',
  adminMyPage: '/admin/my-page',
  adminSettings: '/admin/settings',

  // 강사 셸
  instructor: '/instructor',
  instructorResumes: '/instructor/resumes',
  instructorBoard: '/instructor/board',
  instructorBoardCreate: '/instructor/board/create',
  instructorAssessments: '/instructor/assessments',
  instructorAssessmentsCreate: '/instructor/assessments/create',
  instructorCurriculum: '/instructor/curriculum',
  instructorMyPage: '/instructor/my-page',
  instructorSettings: '/instructor/settings',
} as const;

// 파라미터가 붙는 경로들 — Flutter의 같은 이름 함수들
export const resumeEditPath = (
  resumeId: string,
  opts: { section?: string; feedback?: boolean } = {},
): string => {
  const params = new URLSearchParams();
  if (opts.section !== undefined && opts.section !== '') params.set('section', opts.section);
  if (opts.feedback === true) params.set('feedback', '1');
  const query = params.toString();
  return `/resume/${resumeId}/edit${query === '' ? '' : `?${query}`}`;
};

export const assessmentTakePath = (id: string) => `/assessments/${id}/take`;
export const assessmentResultPath = (id: string) => `/assessments/${id}/result`;

export const studyRoomNoteSourcePath = (sourceId: string) => `/study-room/notes/${sourceId}`;

export const instructorBoardNoticeEditPath = (id: string) => `/instructor/board/${id}/edit`;
export const instructorAssessmentDetailPath = (id: string) => `/instructor/assessments/${id}`;
export const instructorAssessmentEditPath = (id: string) => `/instructor/assessments/${id}/edit`;
export const instructorAssessmentSubmissionPath = (id: string, submissionId: string) =>
  `/instructor/assessments/${id}/submissions/${submissionId}`;

export const adminAssessmentDetailPath = (id: string) => `/admin/assessments/${id}`;
export const adminStudentDetailPath = (uid: string) => `/admin/students/${uid}`;
export const adminStudentEditPath = (uid: string) => `/admin/students/${uid}/edit`;
export const adminCohortEditPath = (id: string) => `/admin/cohorts/${id}/edit`;
export const adminFormTaskEditPath = (id: string) => `/admin/form-tasks/${id}/edit`;
export const adminBoardNoticeEditPath = (id: string) => `/admin/board/${id}/edit`;
export const adminBoardScheduledEditPath = (id: string) => `/admin/board/scheduled/${id}/edit`;
export const adminBoardAlertPopupEditPath = (id: string) => `/admin/board/alert-popups/${id}/edit`;
export const adminStudyRoomPackagePath = (id: string) => `/admin/study-room/${id}`;
export const adminMileageProductEditPath = (id: string) => `/admin/mileage/products/${id}/edit`;

export function homeFor(role: UserRole): string {
  switch (role) {
    case 'admin':
      return RoutePaths.admin;
    case 'instructor':
      return RoutePaths.instructor;
    default:
      return RoutePaths.dashboard;
  }
}
