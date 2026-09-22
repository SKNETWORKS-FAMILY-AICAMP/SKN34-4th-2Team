import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/utils/date_utils.dart';
import '../models/assessment_model.dart';
import '../models/alert_popup_model.dart';
import '../models/curriculum_sheet_model.dart';
import '../models/inflearn_package_model.dart';
import '../models/study_source_model.dart';
import '../models/youtube_recommendation_model.dart';
import '../models/cohort_model.dart';
import '../models/domain_models.dart';
import '../models/form_task_model.dart';
import '../models/notice_model.dart';
import '../models/scheduled_notice_model.dart';
import '../models/post_model.dart';
import '../models/resume_model.dart';
import '../models/submission_model.dart';
import '../models/todo_model.dart';
import '../models/user_model.dart';
import '../demo/demo_accounts.dart';
import '../demo/demo_lms_repository.dart';
import '../providers/cohort_providers.dart';
import '../../features/auth/providers/auth_providers.dart';
import '../data/lms_api_client.dart';
import '../data/lms_repository.dart';
import '../../features/admin/data/scheduled_notice_admin_service.dart';
import 'package:cloud_functions/cloud_functions.dart';

final scheduledNoticeAdminServiceProvider =
    Provider<ScheduledNoticeAdminService>((ref) {
  return ScheduledNoticeAdminService(
    FirebaseFunctions.instanceFor(region: 'asia-northeast3'),
  );
});

final lmsRepositoryProvider = Provider<dynamic>((ref) {
  final uid = ref.watch(sessionUidProvider).value;
  if (DemoConfig.enabled && uid != null && DemoAccounts.isDemoUid(uid)) {
    return demoLmsRepository;
  }
  return LmsRepository(lmsApiClient);
});

final todosStreamProvider = StreamProvider.autoDispose<List<TodoModel>>((ref) {
  final user = ref.watch(currentUserSyncProvider);
  if (user == null) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchTodos(user.uid);
});

final postsStreamProvider = StreamProvider.autoDispose<List<PostModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchPosts(cohortId);
});

final noticesStreamProvider =
    StreamProvider.autoDispose<List<NoticeModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchNotices(cohortId);
});

final scheduledNoticesProvider =
    StreamProvider.autoDispose<List<ScheduledNoticeModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  final isAdmin = ref.watch(isAdminProvider);
  if (cohortId == null || !isAdmin) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchScheduledNotices(cohortId)
      as Stream<List<ScheduledNoticeModel>>;
});

final alertPopupsAdminProvider =
    StreamProvider.autoDispose<List<AlertPopupModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  final isAdmin = ref.watch(isAdminProvider);
  if (cohortId == null || !isAdmin) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchAlertPopups(cohortId)
      as Stream<List<AlertPopupModel>>;
});

final activeAlertPopupsProvider =
    StreamProvider<List<AlertPopupModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null || cohortId.isEmpty) {
    return Stream.value(const <AlertPopupModel>[]);
  }
  return ref.watch(lmsRepositoryProvider).watchActiveAlertPopups(cohortId)
      as Stream<List<AlertPopupModel>>;
});

final mySubmissionsProvider =
    StreamProvider.autoDispose<List<SubmissionModel>>((ref) {
  final user = ref.watch(currentUserSyncProvider);
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (user == null || cohortId == null) return Stream.value([]);
  return ref
      .watch(lmsRepositoryProvider)
      .watchMySubmissions(cohortId, user.uid);
});

final allSubmissionsProvider =
    StreamProvider.autoDispose<List<SubmissionModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  final isAdmin = ref.watch(isAdminProvider);
  if (cohortId == null || !isAdmin) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchAllSubmissions(cohortId);
});

final myResumesProvider = StreamProvider.autoDispose<List<ResumeModel>>((ref) {
  final user = ref.watch(currentUserSyncProvider);
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (user == null || cohortId == null) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchMyResumes(cohortId, user.uid);
});

final cohortResumesProvider =
    StreamProvider.autoDispose<List<ResumeModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  final canReview = ref.watch(canReviewResumesProvider);
  if (cohortId == null || !canReview) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchCohortResumes(cohortId);
});

final weeklyTaskProvider = StreamProvider.autoDispose<WeeklyTaskModel?>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value(null);
  return ref.watch(lmsRepositoryProvider).watchCurrentWeeklyTask(cohortId);
});

final userProgressProvider =
    StreamProvider.autoDispose<UserProgressModel?>((ref) {
  final user = ref.watch(currentUserSyncProvider);
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (user == null || cohortId == null) return Stream.value(null);
  return ref
      .watch(lmsRepositoryProvider)
      .watchUserProgress(cohortId, user.uid);
});

final myAttendancesProvider =
    StreamProvider.autoDispose<List<AttendanceModel>>((ref) {
  final user = ref.watch(currentUserSyncProvider);
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (user == null || cohortId == null) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchUserAttendances(
        cohortId,
        user.uid,
      ) as Stream<List<AttendanceModel>>;
});

/// 관리자 출석 관리 대상 학생 uid
final adminAttendanceTargetUserIdProvider =
    NotifierProvider<_AdminAttendanceTarget, String?>(
  _AdminAttendanceTarget.new,
);

class _AdminAttendanceTarget extends Notifier<String?> {
  @override
  String? build() => null;

  void select(String? uid) => state = uid;
}

final cohortStudentsProvider =
    StreamProvider.autoDispose<List<UserModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  final isAdmin = ref.watch(isAdminProvider);
  final isInstructor = ref.watch(isInstructorProvider);
  if (cohortId == null || (!isAdmin && !isInstructor)) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchCohortStudents(cohortId);
});

/// 관리자 기수 목록에서 각 기수의 실제 재원생 수를 표시할 때 사용한다.
/// `cohorts.studentCount`는 과거 데이터에서 누락될 수 있으므로 users를 기준으로 한다.
final cohortStudentsByIdProvider = StreamProvider.autoDispose
    .family<List<UserModel>, String>((ref, cohortId) {
  final isAdmin = ref.watch(isAdminProvider);
  if (!isAdmin) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchCohortStudents(cohortId);
});

final instructorsStreamProvider =
    StreamProvider.autoDispose<List<UserModel>>((ref) {
  final isAdmin = ref.watch(isAdminProvider);
  if (!isAdmin) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchInstructors();
});

final attendancesByDateProvider = StreamProvider.autoDispose
    .family<List<AttendanceModel>, String>((ref, dateKey) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  final isAdmin = ref.watch(isAdminProvider);
  final isInstructor = ref.watch(isInstructorProvider);
  if (cohortId == null || (!isAdmin && !isInstructor)) {
    return Stream.value([]);
  }
  return ref.watch(lmsRepositoryProvider).watchAttendancesByDate(
        cohortId,
        dateKey,
      ) as Stream<List<AttendanceModel>>;
});

final rollCallConfirmedProvider =
    StreamProvider.autoDispose.family<Set<String>, String>((ref, scopeKey) {
  final parts = scopeKey.split('|');
  if (parts.length != 2) return Stream.value(const <String>{});
  final dateKey = parts[0];
  final periodId = parts[1];
  final cohortId = ref.watch(effectiveCohortIdProvider);
  final isAdmin = ref.watch(isAdminProvider);
  final isInstructor = ref.watch(isInstructorProvider);
  if (cohortId == null || (!isAdmin && !isInstructor)) {
    return Stream.value(const <String>{});
  }
  return ref.watch(lmsRepositoryProvider).watchRollCallConfirmed(
        cohortId,
        dateKey,
        periodId,
      ) as Stream<Set<String>>;
});

final rollCallHeldProvider =
    StreamProvider.autoDispose.family<Set<String>, String>((ref, scopeKey) {
  final parts = scopeKey.split('|');
  if (parts.length != 2) return Stream.value(const <String>{});
  final dateKey = parts[0];
  final periodId = parts[1];
  final cohortId = ref.watch(effectiveCohortIdProvider);
  final isAdmin = ref.watch(isAdminProvider);
  final isInstructor = ref.watch(isInstructorProvider);
  if (cohortId == null || (!isAdmin && !isInstructor)) {
    return Stream.value(const <String>{});
  }
  return ref.watch(lmsRepositoryProvider).watchRollCallHeld(
        cohortId,
        dateKey,
        periodId,
      ) as Stream<Set<String>>;
});

final attendanceStatusMapProvider = StreamProvider.autoDispose
    .family<Map<String, String>, String>((ref, userId) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value({});
  final stream = ref.watch(lmsRepositoryProvider).watchUserAttendances(
        cohortId,
        userId,
      ) as Stream<List<AttendanceModel>>;
  return stream.map((list) {
    final map = <String, String>{};
    for (final a in list) {
      final s = a.dayStatus;
      if (s != null) map[a.dateKey] = s;
    }
    return map;
  });
});

final todayScheduleProvider = StreamProvider.autoDispose<ScheduleModel?>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value(null);
  final dateKey = AppDateUtils.toDateKey(DateTime.now());
  return ref.watch(lmsRepositoryProvider).watchSchedule(cohortId, dateKey);
});

final scheduleDateKeysProvider =
    StreamProvider.autoDispose<List<String>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchScheduleDateKeys(cohortId);
});

final materialsProvider =
    StreamProvider.autoDispose<List<MaterialModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchMaterials(cohortId);
});

final assignmentsProvider =
    StreamProvider.autoDispose<List<AssignmentModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchAssignments(cohortId);
});

final inflearnPackagesProvider =
    StreamProvider.autoDispose<List<InflearnPackageModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchInflearnPackages(cohortId);
});

final publishedInflearnPackagesProvider =
    StreamProvider.autoDispose<List<InflearnPackageModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref
      .watch(lmsRepositoryProvider)
      .watchPublishedInflearnPackages(cohortId);
});

final studySourcesProvider =
    StreamProvider.autoDispose<List<StudySourceModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchStudySources(cohortId);
});

final activeStudySourcesProvider =
    StreamProvider.autoDispose<List<StudySourceModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchActiveStudySources(cohortId);
});

final readyStudyNotesProvider =
    StreamProvider.autoDispose<List<StudyNoteModel>>((ref) {
  final uid = ref.watch(sessionUidProvider).value;
  if (uid == null || uid.isEmpty) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchReadyStudyNotes(uid);
});

final youtubeRecommendationsProvider =
    StreamProvider.autoDispose<List<YoutubeRecommendationModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchYoutubeRecommendations(cohortId);
});

final publishedYoutubeRecommendationsProvider =
    StreamProvider.autoDispose<List<YoutubeRecommendationModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref
      .watch(lmsRepositoryProvider)
      .watchPublishedYoutubeRecommendations(cohortId);
});

/// 현재 유저 skills 기준 랭킹된 YouTube 추천
final rankedYoutubeRecommendationsProvider =
    Provider.autoDispose<AsyncValue<List<RankedYoutubeRecommendation>>>((ref) {
  final user = ref.watch(currentUserSyncProvider);
  final videosAsync = ref.watch(publishedYoutubeRecommendationsProvider);

  return videosAsync.when(
    loading: () => const AsyncValue.loading(),
    error: (e, st) => AsyncValue.error(e, st),
    data: (videos) {
      final skills = user?.skills ?? const <String>[];
      if (skills.isEmpty) {
        // 스킬 없으면 매칭 없이 공개 영상 상위만 (score 0)
        final ranked = rankYoutubeRecommendations(
          videos: videos,
          skills: const [],
        );
        return AsyncValue.data(ranked.take(6).toList());
      }
      final ranked = rankYoutubeRecommendations(
        videos: videos,
        skills: skills,
      );
      final matched = ranked.where((r) => r.score > 0).toList();
      // 매칭 없으면 전체 공개 목록(점수 0)으로 폴백
      final result = matched.isNotEmpty ? matched : ranked;
      return AsyncValue.data(result.take(12).toList());
    },
  );
});

final assessmentsProvider =
    StreamProvider.autoDispose<List<AssessmentModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchAssessments(cohortId);
});

final publishedAssessmentsProvider =
    StreamProvider.autoDispose<List<AssessmentModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchPublishedAssessments(cohortId);
});

final assessmentProvider =
    StreamProvider.autoDispose.family<AssessmentModel?, String>((ref, id) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value(null);
  return ref.watch(lmsRepositoryProvider).watchAssessment(cohortId, id);
});

final assessmentQuestionsProvider = StreamProvider.autoDispose
    .family<List<AssessmentQuestionModel>, String>((ref, assessmentId) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref
      .watch(lmsRepositoryProvider)
      .watchAssessmentQuestions(cohortId, assessmentId);
});

final myAssessmentSubmissionsProvider = StreamProvider.autoDispose<
    List<AssessmentSubmissionModel>>((ref) {
  final user = ref.watch(currentUserSyncProvider);
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (user == null || cohortId == null) return Stream.value([]);
  return ref
      .watch(lmsRepositoryProvider)
      .watchMyAssessmentSubmissions(cohortId, user.uid);
});

final assessmentSubmissionsProvider = StreamProvider.autoDispose
    .family<List<AssessmentSubmissionModel>, String>((ref, assessmentId) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref
      .watch(lmsRepositoryProvider)
      .watchAssessmentSubmissions(cohortId, assessmentId);
});

final assessmentSubmissionProvider = StreamProvider.autoDispose
    .family<AssessmentSubmissionModel?, String>((ref, submissionId) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value(null);
  return ref
      .watch(lmsRepositoryProvider)
      .watchAssessmentSubmission(cohortId, submissionId);
});

final latestCurriculumSheetProvider =
    StreamProvider.autoDispose<CurriculumSheetModel?>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value(null);
  return ref
      .watch(lmsRepositoryProvider)
      .watchLatestCurriculumSheet(cohortId);
});

final curriculumSheetsProvider =
    StreamProvider.autoDispose<List<CurriculumSheetModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchCurriculumSheets(cohortId);
});

/// 선택된 캘린더 날짜의 시간표
final selectedScheduleProvider = StreamProvider.autoDispose
    .family<ScheduleModel?, DateTime>((ref, date) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value(null);
  final dateKey = AppDateUtils.toDateKey(date);
  return ref.watch(lmsRepositoryProvider).watchSchedule(cohortId, dateKey);
});

final resumeFeedbackProvider = StreamProvider.autoDispose
    .family<List<ResumeFeedbackModel>, String>((ref, resumeId) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref
      .watch(lmsRepositoryProvider)
      .watchResumeFeedback(cohortId, resumeId);
});

final resumeDetailProvider = StreamProvider.autoDispose
    .family<ResumeModel?, String>((ref, resumeId) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value(null);
  return ref.watch(lmsRepositoryProvider).watchResume(cohortId, resumeId);
});

final cohortsStreamProvider =
    StreamProvider.autoDispose<List<CohortModel>>((ref) {
  final isAdmin = ref.watch(isAdminProvider);
  if (!isAdmin) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchCohorts();
});

final allCohortsAdminProvider =
    StreamProvider.autoDispose<List<CohortModel>>((ref) {
  final isAdmin = ref.watch(isAdminProvider);
  if (!isAdmin) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchAllCohorts();
});

final effectiveCohortNameProvider = Provider<String?>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return null;

  final cohortsAsync = ref.watch(cohortsStreamProvider);
  final matched = switch (cohortsAsync) {
    AsyncData(:final value) =>
      value.where((c) => c.cohortId == cohortId).firstOrNull,
    _ => null,
  };
  if (matched != null) return matched.name;

  final user = ref.watch(currentUserSyncProvider);
  if (user?.cohortId == cohortId) return user?.cohortName;
  return cohortId;
});

final adminCohortsWithResumesProvider =
    StreamProvider.autoDispose<List<CohortWithResumes>>((ref) {
  final isAdmin = ref.watch(isAdminProvider);
  if (!isAdmin) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchAllCohortsWithResumes();
});

final formTasksWithStatusProvider =
    StreamProvider.autoDispose<List<FormTaskWithStatus>>((ref) {
  final user = ref.watch(currentUserSyncProvider);
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (user == null || cohortId == null) return Stream.value([]);
  return ref
      .watch(lmsRepositoryProvider)
      .watchFormTasksWithStatus(cohortId, user.uid);
});

final allFormTasksAdminProvider =
    StreamProvider.autoDispose<List<FormTaskModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  final isAdmin = ref.watch(isAdminProvider);
  if (cohortId == null || !isAdmin) return Stream.value([]);
  return ref.watch(lmsRepositoryProvider).watchAllFormTasks(cohortId);
});

final formTaskDetailProvider = StreamProvider.autoDispose
    .family<FormTaskModel?, String>((ref, taskId) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value(null);
  return ref.watch(lmsRepositoryProvider).watchFormTask(cohortId, taskId);
});

final formTaskResponsesProvider = StreamProvider.autoDispose
    .family<List<FormResponseModel>, String>((ref, taskId) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref
      .watch(lmsRepositoryProvider)
      .watchFormTaskResponses(cohortId, taskId);
});
