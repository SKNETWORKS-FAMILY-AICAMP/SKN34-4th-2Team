import '../constants/role.dart';

/// go_router 경로 상수
abstract final class RoutePaths {
  static const login = '/login';
  static const changePassword = '/change-password';

  // Shell 하위 경로
  static const dashboard = '/';
  static const resume = '/resume';
  static const studyRoom = '/study-room';
  static const studyRoomNotes = '/study-room/notes';
  static String studyRoomNoteSource(String sourceId, {String? noteId}) {
    final path = '/study-room/notes/$sourceId';
    if (noteId == null || noteId.isEmpty) return path;
    return Uri(path: path, queryParameters: {'noteId': noteId}).toString();
  }

  static const board = '/board';
  static const records = '/records';
  static const recordsCreate = '/records/create';
  static const recordsCreateCert = '/records/create/certification';
  static const recordsCreateStudy = '/records/create/study';
  static const recordsCreateBlog = '/records/create/blog';
  static const recordsCreateStudyCert = '/records/create/study-cert';
  static const recordsCreatePrecourseQuiz = '/records/create/precourse-quiz';
  static const mileage = '/mileage';
  static const mileageShop = '/mileage/shop';
  static const mileageCart = '/mileage/shop/cart';
  static const assessments = '/assessments';
  static const myPage = '/my-page';
  static const settings = '/settings';
  static const forms = '/forms';
  static const qualExams = '/qual-exams';
  static const resumeEdit = '/resume/:resumeId/edit';

  // Admin Shell
  static const admin = '/admin';
  static const adminRecords = '/admin/records';
  static const adminResumes = '/admin/resumes';
  static const adminBoard = '/admin/board';
  static const adminBoardNoticeCreate = '/admin/board/create';
  static const adminBoardScheduledCreate = '/admin/board/scheduled/create';
  static const adminBoardAlertPopupCreate = '/admin/board/alert-popups/create';
  static const adminStudyRoom = '/admin/study-room';
  static const adminMyPage = '/admin/my-page';
  static const adminSettings = '/admin/settings';
  static const adminStudyRoomCreate = '/admin/study-room/create';
  static const adminStudents = '/admin/students';
  static const adminStudentsCreate = '/admin/students/create';
  static const adminCohorts = '/admin/cohorts';
  static const adminCohortsCreate = '/admin/cohorts/create';
  static const adminFormTasks = '/admin/form-tasks';
  static const adminFormTasksCreate = '/admin/form-tasks/create';
  static const adminSeating = '/admin/seating';
  static const adminMileage = '/admin/mileage';
  static const adminMileageProducts = '/admin/mileage/products';
  static const adminMileageProductsCreate = '/admin/mileage/products/create';
  static const adminMileageRequests = '/admin/mileage/requests';
  static const adminMileageAdjust = '/admin/mileage/adjust';
  static const adminMileageSettings = '/admin/mileage/settings';
  static const adminInstructors = '/admin/instructors';
  static const adminInstructorsCreate = '/admin/instructors/create';
  static const adminAttendance = '/admin/attendance';
  static const adminSeatPresence = '/admin/seat-presence';
  static const adminAssessments = '/admin/assessments';
  static const adminAiQuality = '/admin/ai-quality';

  // Instructor Shell
  static const instructor = '/instructor';
  static const instructorResumes = '/instructor/resumes';
  static const instructorBoard = '/instructor/board';
  static const instructorBoardCreate = '/instructor/board/create';
  static const instructorAssessments = '/instructor/assessments';
  static const instructorAssessmentsCreate = '/instructor/assessments/create';
  static const instructorCurriculum = '/instructor/curriculum';
  static const instructorMyPage = '/instructor/my-page';
  static const instructorSettings = '/instructor/settings';

  static String assessmentTakePath(String assessmentId) =>
      '/assessments/$assessmentId/take';
  static String assessmentResultPath(String assessmentId) =>
      '/assessments/$assessmentId/result';

  static String instructorBoardNoticeEditPath(String noticeId) =>
      '/instructor/board/$noticeId/edit';
  static String instructorAssessmentDetailPath(String assessmentId) =>
      '/instructor/assessments/$assessmentId';
  static String instructorAssessmentEditPath(String assessmentId) =>
      '/instructor/assessments/$assessmentId/edit';
  static String instructorAssessmentSubmissionPath(
    String assessmentId,
    String submissionId,
  ) => '/instructor/assessments/$assessmentId/submissions/$submissionId';

  static String adminAssessmentDetailPath(String assessmentId) =>
      '/admin/assessments/$assessmentId';
  static String adminAssessmentSubmissionPath(
    String assessmentId,
    String submissionId,
  ) => '/admin/assessments/$assessmentId/submissions/$submissionId';

  static String homeFor(UserRole role) => switch (role) {
    UserRole.admin => admin,
    UserRole.instructor => instructor,
    UserRole.student => dashboard,
  };

  static String adminMileageProductEditPath(String productId) =>
      '/admin/mileage/products/$productId/edit';

  static String adminStudentDetailPath(String uid) => '/admin/students/$uid';
  static String adminStudentEditPath(String uid) => '/admin/students/$uid/edit';
  static String adminFormTaskDetailPath(String taskId) =>
      '/admin/form-tasks/$taskId';
  static String adminFormTaskEditPath(String taskId) =>
      '/admin/form-tasks/$taskId/edit';
  static String adminCohortEditPath(String cohortId) =>
      '/admin/cohorts/$cohortId/edit';

  static String resumeEditPath(
    String resumeId, {
    String? section,
    String? cohortId,
    bool openFeedback = false,
  }) {
    final path = '/resume/$resumeId/edit';
    final params = <String, String>{};
    if (section != null && section.isNotEmpty) params['section'] = section;
    if (cohortId != null && cohortId.isNotEmpty) params['cohortId'] = cohortId;
    // 목록의 「읽으러 가기」로 들어오면 종이 펼쳐진 채로 연다. 가는 곳은 같고
    // 도착 상태가 다르다.
    if (openFeedback) params['feedback'] = '1';
    if (params.isEmpty) return path;
    final query = params.entries.map((e) => '${e.key}=${e.value}').join('&');
    return '$path?$query';
  }

  static String adminBoardNoticeEditPath(String noticeId) =>
      '/admin/board/$noticeId/edit';
  static String adminBoardScheduledEditPath(String scheduledId) =>
      '/admin/board/scheduled/$scheduledId/edit';
  static String adminBoardAlertPopupEditPath(String popupId) =>
      '/admin/board/alert-popups/$popupId/edit';

  static String adminStudyRoomPackagePath(String packageId) =>
      '/admin/study-room/$packageId';
  static const attendance = '/attendance';
  static const seating = '/seating';
}
