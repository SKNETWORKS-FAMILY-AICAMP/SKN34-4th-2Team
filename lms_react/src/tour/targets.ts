/** 역할별 온보딩 타깃 id */
export const StudentTargets = {
  navDashboard: 'student.nav.dashboard',
  navResume: 'student.nav.resume',
  navStudyRoom: 'student.nav.studyRoom',
  navBoard: 'student.nav.board',
  navSeating: 'student.nav.seating',
  navForms: 'student.nav.forms',
  navQualExams: 'student.nav.qualExams',
  navRecords: 'student.nav.records',
  navMileage: 'student.nav.mileage',
  navAssessments: 'student.nav.assessments',
  navMyPage: 'student.nav.myPage',

  attendanceForm: 'student.appBar.attendanceForm',
  dashboardCalendar: 'student.dashboard.calendar',
  boardNotices: 'student.board.notices',
} as const;

export const InstructorTargets = {
  navAttendance: 'instructor.nav.attendance',
  navResumes: 'instructor.nav.resumes',
  navBoard: 'instructor.nav.board',
  navAssessments: 'instructor.nav.assessments',
  navCurriculum: 'instructor.nav.curriculum',
  navMyPage: 'instructor.nav.myPage',

  attendanceSummary: 'instructor.attendance.summary',
  attendanceConfirm: 'instructor.attendance.confirm',
  resumesStats: 'instructor.resumes.stats',
  boardCreate: 'instructor.board.create',
  assessmentsCreate: 'instructor.assessments.create',
  curriculumUpload: 'instructor.curriculum.upload',
} as const;

export const AdminTargets = {
  navDashboard: 'admin.nav.dashboard',
  navCohorts: 'admin.nav.cohorts',
  navStudents: 'admin.nav.students',
  navInstructors: 'admin.nav.instructors',
  navAttendance: 'admin.nav.attendance',
  navSeatPresence: 'admin.nav.seatPresence',
  navSeating: 'admin.nav.seating',
  navAssessments: 'admin.nav.assessments',
  navRecords: 'admin.nav.records',
  navResumes: 'admin.nav.resumes',
  navFormTasks: 'admin.nav.formTasks',
  navStudyRoom: 'admin.nav.studyRoom',
  navBoard: 'admin.nav.board',
  navMileage: 'admin.nav.mileage',
  navAiQuality: 'admin.nav.aiQuality',

  attendanceDailyNotice: 'admin.attendance.dailyNotice',
  boardCreate: 'admin.board.create',
} as const;
