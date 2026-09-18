/// Firestore Collection / Document 경로 상수
/// 모든 Repository는 이 클래스의 경로만 사용하여 쿼리합니다.
abstract final class FirestorePaths {
  // ── 전역 ──
  static const users = 'users';
  static const studentIntakes = 'studentIntakes';

  // ── 기수 루트 ──
  static String cohort(String cohortId) => 'cohorts/$cohortId';

  // ── 기수 하위 Subcollection ──
  static String schedules(String cohortId) =>
      '${cohort(cohortId)}/schedules';
  static String seating(String cohortId) => '${cohort(cohortId)}/seating';
  static String attendances(String cohortId) =>
      '${cohort(cohortId)}/attendances';
  static String rollCalls(String cohortId) =>
      '${cohort(cohortId)}/rollCalls';

  static String rollCallDoc(String cohortId, String dateKey, String periodId) =>
      '${rollCalls(cohortId)}/${dateKey}_p$periodId';
  static String notices(String cohortId) => '${cohort(cohortId)}/notices';
  static String scheduledNotices(String cohortId) =>
      '${cohort(cohortId)}/scheduledNotices';
  static String alertPopups(String cohortId) =>
      '${cohort(cohortId)}/alertPopups';
  static String posts(String cohortId) => '${cohort(cohortId)}/posts';
  static String qna(String cohortId) => '${cohort(cohortId)}/qna';
  static String materials(String cohortId) => '${cohort(cohortId)}/materials';
  static String assignments(String cohortId) =>
      '${cohort(cohortId)}/assignments';
  static String resumes(String cohortId) => '${cohort(cohortId)}/resumes';
  static String mileageTransactions(String cohortId) =>
      '${cohort(cohortId)}/mileageTransactions';
  static String mileageSettings(String cohortId) =>
      '${cohort(cohortId)}/mileageSettings';
  static String mileageSettingsConfig(String cohortId) =>
      '${mileageSettings(cohortId)}/config';
  static String mileageProducts(String cohortId) =>
      '${cohort(cohortId)}/mileageProducts';
  static String purchaseRequests(String cohortId) =>
      '${cohort(cohortId)}/purchaseRequests';
  static String mileageCart(String cohortId) =>
      '${cohort(cohortId)}/mileageCart';
  static String missionProgress(String cohortId) =>
      '${cohort(cohortId)}/missionProgress';
  static String missionProgressDoc(String cohortId, String userId) =>
      '${missionProgress(cohortId)}/$userId';
  static String weeklyTasks(String cohortId) =>
      '${cohort(cohortId)}/weeklyTasks';
  static String userProgress(String cohortId) =>
      '${cohort(cohortId)}/userProgress';
  static String submissions(String cohortId) =>
      '${cohort(cohortId)}/submissions';
  static String assessments(String cohortId) =>
      '${cohort(cohortId)}/assessments';
  static String assessment(String cohortId, String assessmentId) =>
      '${assessments(cohortId)}/$assessmentId';
  static String assessmentQuestions(String cohortId, String assessmentId) =>
      '${assessment(cohortId, assessmentId)}/questions';
  static String assessmentQuestion(
    String cohortId,
    String assessmentId,
    String questionId,
  ) =>
      '${assessmentQuestions(cohortId, assessmentId)}/$questionId';
  static String assessmentSubmissions(String cohortId) =>
      '${cohort(cohortId)}/assessmentSubmissions';
  static String assessmentSubmission(
    String cohortId,
    String assessmentId,
    String userId,
  ) =>
      '${assessmentSubmissions(cohortId)}/${assessmentId}_$userId';
  static String inflearnPackages(String cohortId) =>
      '${cohort(cohortId)}/inflearnPackages';
  static String studySources(String cohortId) =>
      '${cohort(cohortId)}/studySources';
  static String studySource(String cohortId, String sourceId) =>
      '${studySources(cohortId)}/$sourceId';
  static String userStudyNotes(String uid) => 'users/$uid/studyNotes';
  static String userStudyNote(String uid, String noteId) =>
      '${userStudyNotes(uid)}/$noteId';
  static String youtubeRecommendations(String cohortId) =>
      '${cohort(cohortId)}/youtubeRecommendations';
  static String projectTeams(String cohortId) =>
      '${cohort(cohortId)}/projectTeams';
  static String recommendationEvents(String cohortId) =>
      '${cohort(cohortId)}/recommendationEvents';
  static String curriculumMeta(String cohortId) =>
      '${cohort(cohortId)}/curriculum/meta';
  static String curriculumSheets(String cohortId) =>
      '${cohort(cohortId)}/curriculumSheets';
  static String curriculumSheet(String cohortId, String sheetId) =>
      '${curriculumSheets(cohortId)}/$sheetId';

  // ── 유저 하위 Subcollection ──
  static String userTodos(String uid) => 'users/$uid/todos';

  // ── 시스템 캐시 (국가자격 시험일정 등) ──
  static const systemCache = 'systemCache';
  static String qualExamSchedules(int year) =>
      '$systemCache/qualExamSchedules_$year';
}
