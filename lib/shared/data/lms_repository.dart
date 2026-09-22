import 'dart:async';

import '../../core/constants/attendance_status.dart';
import '../../core/errors/app_exception.dart';
import '../../core/utils/date_utils.dart';
import '../models/assessment_model.dart';
import '../models/alert_popup_model.dart';
import '../models/curriculum_sheet_model.dart';
import '../models/inflearn_package_model.dart';
import '../models/study_source_model.dart';
import '../models/youtube_recommendation_model.dart';
import '../models/cohort_model.dart';
import '../models/domain_models.dart';
import '../models/notice_model.dart';
import '../models/scheduled_notice_model.dart';
import '../models/form_task_model.dart';
import '../models/post_model.dart';
import '../models/resume_content.dart';
import '../models/resume_model.dart';
import '../models/submission_model.dart';
import '../models/todo_model.dart';
import '../models/user_model.dart';
import '../models/job_preferences.dart';
import '../models/mission_models.dart';
import '../models/ai_ops_models.dart';
import 'lms_api_client.dart';

/// Postgres LMS API Repository — Firestore CRUD 없음
class LmsRepository {
  LmsRepository(this._api);

  final LmsApiClient _api;

  Stream<T> _watch<T>(T Function() select) async* {
    if (_api.snapshot.isEmpty) {
      try {
        await _api.bootstrap();
      } catch (_) {}
    }
    yield select();
    await for (final _ in _api.changes) {
      yield select();
    }
  }

  List<Map<String, dynamic>> _list(String key) => _api.list(key);

  List<Map<String, dynamic>> _forCohort(String key, String cohortId) {
    return _list(key).where((row) => '${row['cohortId']}' == cohortId).toList();
  }

  Future<String> _id(String op, Map<String, dynamic> payload) async {
    final result = await _api.command(op, payload);
    return '${result['id'] ?? ''}';
  }

  Future<void> _run(String op, [Map<String, dynamic>? payload]) =>
      _api.command(op, payload);

  NoticeModel _notice(Map<String, dynamic> row) => NoticeModel(
        id: '${row['id']}',
        title: row['title'] as String? ?? '',
        content: row['content'] as String? ?? '',
        authorName: row['authorName'] as String? ?? '',
        authorId: row['authorId']?.toString(),
        isFavorite: row['isFavorite'] == true,
        priority: (row['priority'] as num?)?.toInt() ?? 0,
        source: row['source'] as String?,
        channelLabel: row['channelLabel'] as String?,
        scheduledNoticeId: row['scheduledNoticeId']?.toString(),
        imageUrl: row['imageUrl'] as String?,
        createdAt: AppDateUtils.timestampToDateTime(row['createdAt']),
      );

  ResumeModel _resume(Map<String, dynamic> row) {
    final rawSections = Map<String, dynamic>.from(row['sections'] as Map? ?? {});
    final content = ResumeContent.fromMap(
      row['content'] is Map ? Map<String, dynamic>.from(row['content'] as Map) : null,
    );
    final sections = rawSections.isNotEmpty
        ? rawSections.map((k, v) => MapEntry(k, v == true))
        : content.computeSections();
    return ResumeModel(
      id: '${row['id']}',
      userId: '${row['userId'] ?? ''}',
      title: row['title'] as String? ?? '새 이력서',
      status: row['status'] as String? ?? 'writing',
      sections: sections,
      content: content,
      isBaseResume: row['isBaseResume'] == true,
      baseResumeId: '${row['baseResumeId'] ?? ''}',
      sourceTailoredResumeId: '${row['sourceTailoredResumeId'] ?? ''}',
      linkedJobId: '${row['linkedJobId'] ?? row['jobId'] ?? ''}',
      updatedAt: AppDateUtils.timestampToDateTime(row['updatedAt']),
    );
  }

  UserModel _user(Map<String, dynamic> row) =>
      UserModel.fromMap('${row['uid'] ?? row['id']}', row);

  CohortModel _cohort(Map<String, dynamic> row) {
    final isActive = row['isActive'] as bool? ?? true;
    return CohortModel(
      cohortId: '${row['cohortId'] ?? row['code'] ?? row['id']}',
      name: row['name'] as String? ?? '',
      description: row['description'] as String?,
      startDate: AppDateUtils.timestampToDateTime(row['startDate']),
      endDate: AppDateUtils.timestampToDateTime(row['endDate']),
      isActive: isActive,
      termNumber: (row['termNumber'] as num?)?.toInt(),
      classroomName: row['classroomName'] as String?,
      studentCount: (row['studentCount'] as num?)?.toInt() ?? 0,
      createdAt: AppDateUtils.timestampToDateTime(row['createdAt']),
    );
  }

  Stream<List<TodoModel>> watchTodos(String uid) => _watch(() {
        return _list('todos')
            .map(
              (row) => TodoModel(
                id: '${row['id']}',
                title: row['title'] as String? ?? '',
                isCompleted: row['isCompleted'] == true,
                createdAt: AppDateUtils.timestampToDateTime(row['createdAt']),
              ),
            )
            .toList();
      });

  Future<void> addTodo(String uid, String title) =>
      _run('addTodo', {'uid': uid, 'title': title});

  Future<void> toggleTodo(String uid, TodoModel todo) =>
      _run('toggleTodo', {'todoId': todo.id});

  Future<void> deleteTodo(String uid, String todoId) =>
      _run('deleteTodo', {'todoId': todoId});

  Stream<List<PostModel>> watchPosts(String cohortId, {int limit = 20}) =>
      _watch(() => <PostModel>[]);

  Future<void> createPost({
    required String cohortId,
    required String authorId,
    required String authorName,
    required String content,
  }) async {}

  Future<void> deletePost(String cohortId, String postId) async {}

  Stream<List<NoticeModel>> watchNotices(String cohortId) => _watch(() {
        final list = _forCohort('notices', cohortId).map(_notice).toList();
        list.sort((a, b) {
          final fav = (b.isFavorite ? 1 : 0).compareTo(a.isFavorite ? 1 : 0);
          if (fav != 0) return fav;
          return (b.createdAt ?? DateTime(0)).compareTo(a.createdAt ?? DateTime(0));
        });
        return list;
      });

  Future<String> createNotice({
    required String cohortId,
    required NoticeModel notice,
    required String authorId,
    required String authorName,
  }) =>
      _id('createNotice', {
        'cohortId': cohortId,
        'title': notice.title,
        'content': notice.content,
        'authorName': authorName,
        'isFavorite': notice.isFavorite,
        'priority': notice.priority,
      });

  Future<void> updateNotice({
    required String cohortId,
    required NoticeModel notice,
    required String authorId,
    required String authorName,
  }) =>
      _run('updateNotice', {
        'noticeId': notice.id,
        'title': notice.title,
        'content': notice.content,
      });

  Future<void> toggleNoticeFavorite({
    required String cohortId,
    required String noticeId,
    required bool isFavorite,
  }) =>
      _run('updateNotice', {'noticeId': noticeId, 'isFavorite': isFavorite});

  Future<void> deleteNotice(String cohortId, String noticeId) =>
      _run('deleteNotice', {'noticeId': noticeId});

  Stream<List<ScheduledNoticeModel>> watchScheduledNotices(String cohortId) =>
      _watch(() => _forCohort('scheduledNotices', cohortId)
          .map((row) => ScheduledNoticeModel(
                id: '${row['id']}',
                title: row['title'] as String? ?? '',
                content: row['content'] as String? ?? '',
                authorName: row['authorName'] as String? ?? '',
                authorId: row['authorId']?.toString(),
                isActive: row['isActive'] == true,
                repeatType: ScheduleRepeatType.fromString(row['repeatType'] as String?),
                publishTime: row['publishTime'] as String? ?? '09:00',
                weekday: (row['weekday'] as num?)?.toInt() ?? DateTime.monday,
                nextPublishAt: AppDateUtils.timestampToDateTime(row['nextPublishAt']),
                publishAt: AppDateUtils.timestampToDateTime(row['publishAt']),
              ))
          .toList());

  Future<String> createScheduledNotice({
    required String cohortId,
    required ScheduledNoticeModel scheduled,
    required String authorId,
    required String authorName,
  }) async {
    computeNextPublishAt(
      repeatType: scheduled.repeatType,
      publishTime: scheduled.publishTime,
      publishAt: scheduled.publishAt,
      weekday: scheduled.weekday,
    );
    return _id('upsert', {'table': 'scheduled_notices', 'action': 'insert', 'cohortId': cohortId});
  }

  Future<void> updateScheduledNotice({
    required String cohortId,
    required ScheduledNoticeModel scheduled,
    required String authorId,
    required String authorName,
  }) =>
      _run('upsert', {'table': 'scheduled_notices', 'id': scheduled.id, 'action': 'update'});

  Future<void> toggleScheduledNoticeActive({
    required String cohortId,
    required String scheduledId,
    required bool isActive,
  }) =>
      _run('upsert', {'table': 'scheduled_notices', 'id': scheduledId, 'action': 'update'});

  Future<void> deleteScheduledNotice(String cohortId, String scheduledId) =>
      _run('upsert', {'table': 'scheduled_notices', 'id': scheduledId, 'action': 'delete'});

  Stream<List<AlertPopupModel>> watchAlertPopups(String cohortId) => _watch(
        () => _forCohort('alertPopups', cohortId)
            .map((row) => AlertPopupModel(
                  id: '${row['id']}',
                  title: row['title'] as String? ?? '',
                  content: row['content'] as String? ?? '',
                  authorName: row['authorName'] as String? ?? '',
                  isActive: row['isActive'] == true,
                ))
            .toList(),
      );

  Stream<List<AlertPopupModel>> watchActiveAlertPopups(String cohortId) =>
      _watch(() => _forCohort('alertPopups', cohortId)
          .where((row) => row['isActive'] == true)
          .map((row) => AlertPopupModel(
                id: '${row['id']}',
                title: row['title'] as String? ?? '',
                content: row['content'] as String? ?? '',
                authorName: row['authorName'] as String? ?? '',
                isActive: true,
              ))
          .toList());

  Future<String> createAlertPopup({
    required String cohortId,
    required AlertPopupModel popup,
    required String authorId,
  }) =>
      _id('upsert', {'table': 'alert_popups', 'action': 'insert', 'cohortId': cohortId});

  Future<void> updateAlertPopup({
    required String cohortId,
    required AlertPopupModel popup,
  }) =>
      _run('upsert', {'table': 'alert_popups', 'id': popup.id, 'action': 'update'});

  Future<void> toggleAlertPopupActive({
    required String cohortId,
    required String popupId,
    required bool isActive,
  }) =>
      _run('upsert', {'table': 'alert_popups', 'id': popupId, 'action': 'update'});

  Future<void> deleteAlertPopup(String cohortId, String popupId) =>
      _run('upsert', {'table': 'alert_popups', 'id': popupId, 'action': 'delete'});

  Stream<Map<String, String>> watchAlertPopupDismissals(String uid) =>
      _watch(() => <String, String>{});

  Future<void> dismissAlertPopupToday({
    required String uid,
    required String popupId,
  }) =>
      _run('upsert', {'table': 'alert_popup_dismissals', 'action': 'insert'});

  Stream<List<SubmissionModel>> watchMySubmissions(String cohortId, String userId) =>
      _watch(() => _forCohort('submissions', cohortId)
          .where((row) => '${row['userId']}' == userId)
          .map((row) => SubmissionModel(
                id: '${row['id']}',
                userId: '${row['userId']}',
                userDisplayName: row['userDisplayName'] as String? ?? '',
                title: row['title'] as String? ?? '',
                type: row['type'] as String? ?? '',
                status: row['status'] as String? ?? '',
              ))
          .toList());

  Stream<List<SubmissionModel>> watchAllSubmissions(String cohortId) => _watch(
        () => _forCohort('submissions', cohortId)
            .map((row) => SubmissionModel(
                  id: '${row['id']}',
                  userId: '${row['userId']}',
                  userDisplayName: row['userDisplayName'] as String? ?? '',
                  title: row['title'] as String? ?? '',
                  type: row['type'] as String? ?? '',
                  status: row['status'] as String? ?? '',
                ))
            .toList(),
      );

  Future<String> createSubmission({
    required String cohortId,
    required SubmissionModel submission,
  }) =>
      _id('upsert', {'table': 'record_submissions', 'action': 'insert'});

  Future<void> reviewSubmission({
    required String cohortId,
    required String submissionId,
    required String status,
    String? comment,
    required String reviewerId,
  }) =>
      _run('upsert', {'table': 'record_submissions', 'id': submissionId, 'action': 'update'});

  Stream<WeeklyTaskModel?> watchCurrentWeeklyTask(String cohortId) => _watch(() {
        final rows = _forCohort('weeklyTasks', cohortId);
        if (rows.isEmpty) return null;
        final row = rows.first;
        return WeeklyTaskModel(
          id: '${row['id']}',
          title: row['title'] as String? ?? '',
          dueDate: AppDateUtils.timestampToDateTime(row['dueDate']) ?? DateTime.now(),
          totalCount: (row['totalCount'] as num?)?.toInt() ?? 0,
        );
      });

  Stream<UserProgressModel?> watchUserProgress(String cohortId, String userId) =>
      _watch(() {
        final row = _forCohort('weeklyProgress', cohortId)
            .where((item) => '${item['userId']}' == userId)
            .firstOrNull;
        if (row == null) return null;
        return UserProgressModel(
          userId: userId,
          completedCount: (row['completedCount'] as num?)?.toInt() ?? 0,
          totalCount: (row['totalCount'] as num?)?.toInt() ?? 0,
        );
      });

  Stream<List<CohortModel>> watchCohorts() =>
      _watch(() => _list('cohorts').map(_cohort).toList());

  Stream<List<CohortModel>> watchAllCohorts() => watchCohorts();

  Future<String> createCohort(CohortModel cohort) =>
      _id('upsert', {'table': 'cohorts', 'action': 'insert'});

  Future<void> updateCohort(CohortModel cohort) =>
      _run('upsert', {'table': 'cohorts', 'id': cohort.cohortId, 'action': 'update'});

  Stream<List<CohortWithResumes>> watchAllCohortsWithResumes() => _watch(() {
        final resumes = _list('resumes').map(_resume).toList();
        return _list('cohorts').map((row) {
          final cohort = _cohort(row);
          return CohortWithResumes(
            cohort: cohort,
            resumes: resumes.where((item) => item.id.isNotEmpty).where((item) {
              return _list('resumes')
                  .any((raw) => '${raw['id']}' == item.id && '${raw['cohortId']}' == cohort.cohortId);
            }).toList(),
          );
        }).toList();
      });

  Stream<List<ResumeModel>> watchMyResumes(String cohortId, String userId) =>
      _watch(() => _forCohort('resumes', cohortId)
          .where((row) => '${row['userId']}' == userId)
          .map(_resume)
          .toList());

  Stream<List<ResumeModel>> watchCohortResumes(String cohortId) =>
      _watch(() => _forCohort('resumes', cohortId).map(_resume).toList());

  Future<String> createResume({
    required String cohortId,
    required ResumeModel resume,
  }) =>
      _id('upsert', {'table': 'resumes', 'action': 'insert'});

  Future<void> setBaseResume({
    required String cohortId,
    required String userId,
    required String resumeId,
  }) =>
      _run('upsert', {'table': 'resumes', 'id': resumeId, 'action': 'update'});

  Future<void> updateResumeSections({
    required String cohortId,
    required String resumeId,
    required Map<String, bool> sections,
  }) =>
      _run('upsert', {'table': 'resumes', 'id': resumeId, 'action': 'update'});

  Stream<ResumeModel?> watchResume(String cohortId, String resumeId) =>
      _watch(() => _forCohort('resumes', cohortId)
          .where((row) => '${row['id']}' == resumeId)
          .map(_resume)
          .firstOrNull);

  Future<void> updateResume({
    required String cohortId,
    required ResumeModel resume,
  }) =>
      _run('upsert', {'table': 'resumes', 'id': resume.id, 'action': 'update'});

  Future<int> syncBirthDateToMyResumes({
    required String cohortId,
    required String userId,
    required String birthDate,
  }) async =>
      0;

  Future<void> approveResume({
    required String cohortId,
    required String resumeId,
  }) =>
      _run('upsert', {'table': 'resumes', 'id': resumeId, 'action': 'update'});

  Future<void> deleteResume(String cohortId, String resumeId) =>
      _run('upsert', {'table': 'resumes', 'id': resumeId, 'action': 'delete'});

  Stream<List<ResumeFeedbackModel>> watchResumeFeedback(
    String cohortId,
    String resumeId,
  ) =>
      _watch(() => _list('resumeFeedbacks')
          .where((row) => '${row['resumeId']}' == resumeId)
          .map((row) => ResumeFeedbackModel(
                id: '${row['id']}',
                sectionKey: row['sectionKey'] as String? ?? '',
                content: row['content'] as String? ?? '',
                authorName: row['authorName'] as String? ?? '',
                authorId: '${row['authorId'] ?? ''}',
              ))
          .toList());

  Future<void> addResumeFeedback({
    required String cohortId,
    required String resumeId,
    required ResumeFeedbackModel feedback,
  }) =>
      _run('upsert', {'table': 'resume_feedback', 'action': 'insert'});

  Future<void> deleteResumeFeedback({
    required String cohortId,
    required String resumeId,
    required String feedbackId,
  }) =>
      _run('upsert', {'table': 'resume_feedback', 'id': feedbackId, 'action': 'delete'});

  Future<void> markResumeFeedbackRead({
    required String cohortId,
    required String resumeId,
    required String uid,
    required List<String> ids,
  }) async {}

  Future<void> markResumeFeedbackSeen({
    required String cohortId,
    required String resumeId,
    required int count,
  }) async {}

  Stream<List<AttendanceModel>> watchUserAttendances(
    String cohortId,
    String userId,
  ) =>
      _watch(() => _forCohort('attendances', cohortId)
          .where((row) => '${row['userId']}' == userId)
          .map(_attendance)
          .toList());

  Stream<List<AttendanceModel>> watchMyAttendances(
    String cohortId,
    String userId,
  ) =>
      watchUserAttendances(cohortId, userId);

  Stream<List<AttendanceModel>> watchAttendancesByDate(
    String cohortId,
    String dateKey,
  ) =>
      _watch(() => _forCohort('attendances', cohortId)
          .where((row) => '${row['dateKey']}' == dateKey)
          .map(_attendance)
          .toList());

  AttendanceModel _attendance(Map<String, dynamic> row) => AttendanceModel(
        id: '${row['id']}',
        userId: '${row['userId'] ?? ''}',
        type: row['type'] as String? ?? 'checkIn',
        dateKey: row['dateKey'] as String? ?? '',
        status: row['status'] as String?,
        userDisplayName: row['userDisplayName'] as String?,
        timestamp: AppDateUtils.timestampToDateTime(row['timestamp'] ?? row['createdAt']),
        checkInTime: row['checkInTime'] as String?,
        checkOutTime: row['checkOutTime'] as String?,
        statusSource: row['statusSource'] as String?,
      );

  Future<int> seedDemoAttendances({
    required String cohortId,
    required List<UserModel> students,
  }) async =>
      0;

  Future<bool> ensureDailyAttendanceFormNotice({
    required String cohortId,
  }) async =>
      false;

  Future<void> upsertAttendanceStatus({
    required String cohortId,
    required String userId,
    required String dateKey,
    required String status,
  }) =>
      _run('upsert', {'table': 'attendances', 'action': 'insert'});

  Future<void> clearAttendanceStatus({
    required String cohortId,
    required String attendanceId,
  }) =>
      _run('upsert', {'table': 'attendances', 'id': attendanceId, 'action': 'delete'});

  Stream<Set<String>> watchRollCallConfirmed(
    String cohortId,
    String dateKey,
    String periodId,
  ) =>
      _watch(() => <String>{});

  Stream<Set<String>> watchRollCallHeld(
    String cohortId,
    String dateKey,
    String periodId,
  ) =>
      _watch(() => <String>{});

  Future<void> ensureRollCallCarriedForward({
    required String cohortId,
    required String dateKey,
    required String periodId,
  }) async {}

  Future<void> setRollCallConfirmed({
    required String cohortId,
    required String dateKey,
    required String periodId,
    required Set<String> uids,
  }) async {}

  Future<void> setRollCallHeld({
    required String cohortId,
    required String dateKey,
    required String periodId,
    required Set<String> uids,
  }) async {}

  Stream<List<UserModel>> watchCohortStudents(String cohortId) => _watch(() {
        return _list('users')
            .where((row) =>
                '${row['cohortId']}' == cohortId && row['role'] == 'student')
            .map(_user)
            .toList();
      });

  Stream<List<UserModel>> watchInstructors() => _watch(() {
        return _list('users').where((row) => row['role'] == 'instructor').map(_user).toList();
      });

  Future<void> recordAttendance({
    required String cohortId,
    required AttendanceModel attendance,
  }) =>
      upsertAttendanceStatus(
        cohortId: cohortId,
        userId: attendance.userId,
        dateKey: attendance.dateKey,
        status: attendance.status ?? AttendanceStatus.present,
      );

  Stream<List<MileageTransactionModel>> watchMyMileageTransactions(
    String cohortId,
    String userId,
  ) =>
      _watch(() => _forCohort('mileageTransactions', cohortId)
          .where((row) => '${row['userId']}' == userId)
          .map((row) => MileageTransactionModel(
                id: '${row['id']}',
                userId: '${row['userId']}',
                amount: (row['amount'] as num?)?.toInt() ?? 0,
                type: row['type'] as String? ?? '',
                reason: row['reason'] as String? ?? '',
                createdAt: AppDateUtils.timestampToDateTime(row['createdAt']),
              ))
          .toList());

  Stream<ScheduleModel?> watchSchedule(String cohortId, String dateKey) =>
      _watch(() {
        final row = _forCohort('schedules', cohortId)
            .where((item) => '${item['dateKey']}' == dateKey)
            .firstOrNull;
        if (row == null) return null;
        return ScheduleModel(
          dateKey: dateKey,
          sessions: const [],
        );
      });

  Stream<List<String>> watchScheduleDateKeys(String cohortId) => _watch(
        () => _forCohort('schedules', cohortId)
            .map((row) => '${row['dateKey']}')
            .where((key) => key.isNotEmpty)
            .toList(),
      );

  Stream<List<MaterialModel>> watchMaterials(String cohortId) => _watch(
        () => _forCohort('materials', cohortId)
            .map((row) => MaterialModel(
                  id: '${row['id']}',
                  title: row['title'] as String? ?? '',
                  fileUrl: row['fileUrl'] as String? ?? '',
                  fileName: row['fileName'] as String? ?? '',
                ))
            .toList(),
      );

  Stream<List<AssignmentModel>> watchAssignments(String cohortId) => _watch(
        () => _forCohort('assignments', cohortId)
            .map((row) => AssignmentModel(
                  id: '${row['id']}',
                  title: row['title'] as String? ?? '',
                  description: row['description'] as String? ?? '',
                  dueDate: AppDateUtils.timestampToDateTime(row['dueDate']) ?? DateTime.now(),
                ))
            .toList(),
      );

  Future<void> submitAssignment({
    required String cohortId,
    required String assignmentId,
    required String userId,
    required String fileUrl,
  }) =>
      _run('upsert', {'table': 'assignments', 'id': assignmentId, 'action': 'update'});

  Stream<List<InflearnPackageModel>> watchInflearnPackages(String cohortId) =>
      _watch(() => _forCohort('inflearnPackages', cohortId)
          .map((row) => InflearnPackageModel(
                id: '${row['id']}',
                title: row['title'] as String? ?? '',
                subject: row['subject'] as String? ?? '',
                isPublished: row['isPublished'] == true,
              ))
          .toList());

  Stream<List<InflearnPackageModel>> watchPublishedInflearnPackages(
    String cohortId,
  ) =>
      _watch(() => _forCohort('inflearnPackages', cohortId)
          .where((row) => row['isPublished'] == true)
          .map((row) => InflearnPackageModel(
                id: '${row['id']}',
                title: row['title'] as String? ?? '',
                subject: row['subject'] as String? ?? '',
                isPublished: true,
              ))
          .toList());

  Future<String> createInflearnPackage({
    required String cohortId,
    required InflearnPackageModel package,
  }) =>
      _id('upsert', {'table': 'inflearn_packages', 'action': 'insert'});

  Future<void> updateInflearnPackage({
    required String cohortId,
    required InflearnPackageModel package,
  }) =>
      _run('upsert', {'table': 'inflearn_packages', 'id': package.id, 'action': 'update'});

  Future<void> deleteInflearnPackage({
    required String cohortId,
    required String packageId,
  }) =>
      _run('upsert', {'table': 'inflearn_packages', 'id': packageId, 'action': 'delete'});

  Stream<List<StudySourceModel>> watchStudySources(String cohortId) => _watch(
        () => _forCohort('studySources', cohortId)
            .map((row) => StudySourceModel(
                  id: '${row['id']}',
                  title: row['title'] as String? ?? '',
                  repoUrl: row['repoUrl'] as String? ?? '',
                  isActive: row['isActive'] != false,
                ))
            .toList(),
      );

  Stream<List<StudySourceModel>> watchActiveStudySources(String cohortId) =>
      _watch(() => _forCohort('studySources', cohortId)
          .where((row) => row['isActive'] != false)
          .map((row) => StudySourceModel(
                id: '${row['id']}',
                title: row['title'] as String? ?? '',
                repoUrl: row['repoUrl'] as String? ?? '',
                isActive: true,
              ))
          .toList());

  Stream<List<StudyNoteModel>> watchReadyStudyNotes(String uid) => _watch(
        () => _list('studyNotes')
            .map((row) => StudyNoteModel(
                  id: '${row['id']}',
                  status: row['status'] as String? ?? 'ready',
                ))
            .toList(),
      );

  Future<String> createStudySource({
    required String cohortId,
    required StudySourceModel source,
  }) =>
      _id('upsert', {'table': 'study_sources', 'action': 'insert'});

  Future<void> updateStudySource({
    required String cohortId,
    required StudySourceModel source,
  }) =>
      _run('upsert', {'table': 'study_sources', 'id': source.id, 'action': 'update'});

  Stream<List<YoutubeRecommendationModel>> watchYoutubeRecommendations(
    String cohortId,
  ) =>
      _watch(() => _forCohort('youtubeRecommendations', cohortId)
          .map((row) => YoutubeRecommendationModel(
                id: '${row['id']}',
                title: row['title'] as String? ?? '',
                youtubeUrl: row['youtubeUrl'] as String? ?? '',
                isPublished: row['isPublished'] == true,
              ))
          .toList());

  Stream<List<YoutubeRecommendationModel>> watchPublishedYoutubeRecommendations(
    String cohortId,
  ) =>
      _watch(() => _forCohort('youtubeRecommendations', cohortId)
          .where((row) => row['isPublished'] == true)
          .map((row) => YoutubeRecommendationModel(
                id: '${row['id']}',
                title: row['title'] as String? ?? '',
                youtubeUrl: row['youtubeUrl'] as String? ?? '',
                isPublished: true,
              ))
          .toList());

  Future<String> createYoutubeRecommendation({
    required String cohortId,
    required YoutubeRecommendationModel item,
  }) =>
      _id('upsert', {'table': 'youtube_recommendations', 'action': 'insert'});

  Future<void> updateYoutubeRecommendation({
    required String cohortId,
    required YoutubeRecommendationModel item,
  }) =>
      _run('upsert', {'table': 'youtube_recommendations', 'id': item.id, 'action': 'update'});

  Future<void> deleteYoutubeRecommendation({
    required String cohortId,
    required String id,
  }) =>
      _run('upsert', {'table': 'youtube_recommendations', 'id': id, 'action': 'delete'});

  Future<void> logRecommendationEvent({
    required String cohortId,
    required String recommendationId,
    required String userId,
    required String event,
  }) async {}

  Stream<List<AssessmentModel>> watchAssessments(String cohortId) => _watch(
        () => _forCohort('assessments', cohortId)
            .map((row) => AssessmentModel(
                  id: '${row['id']}',
                  title: row['title'] as String? ?? '',
                  tags: List<String>.from(row['tags'] as List? ?? const []),
                  questionCount: (row['questionCount'] as num?)?.toInt() ?? 0,
                  maxScore: (row['maxScore'] as num?)?.toInt() ?? 0,
                  startAt: AppDateUtils.timestampToDateTime(row['startAt']) ?? DateTime.now(),
                  endAt: AppDateUtils.timestampToDateTime(row['endAt']) ?? DateTime.now(),
                  published: row['published'] == true,
                ))
            .toList(),
      );

  Stream<List<AssessmentModel>> watchPublishedAssessments(String cohortId) =>
      _watch(() => _forCohort('assessments', cohortId)
          .where((row) => row['published'] == true)
          .map((row) => AssessmentModel(
                id: '${row['id']}',
                title: row['title'] as String? ?? '',
                tags: List<String>.from(row['tags'] as List? ?? const []),
                questionCount: (row['questionCount'] as num?)?.toInt() ?? 0,
                maxScore: (row['maxScore'] as num?)?.toInt() ?? 0,
                startAt: AppDateUtils.timestampToDateTime(row['startAt']) ?? DateTime.now(),
                endAt: AppDateUtils.timestampToDateTime(row['endAt']) ?? DateTime.now(),
                published: true,
              ))
          .toList());

  Stream<AssessmentModel?> watchAssessment(String cohortId, String id) =>
      _watch(() => _forCohort('assessments', cohortId)
          .where((row) => '${row['id']}' == id)
          .map((row) => AssessmentModel(
                id: '${row['id']}',
                title: row['title'] as String? ?? '',
                tags: List<String>.from(row['tags'] as List? ?? const []),
                questionCount: (row['questionCount'] as num?)?.toInt() ?? 0,
                maxScore: (row['maxScore'] as num?)?.toInt() ?? 0,
                startAt: AppDateUtils.timestampToDateTime(row['startAt']) ?? DateTime.now(),
                endAt: AppDateUtils.timestampToDateTime(row['endAt']) ?? DateTime.now(),
                published: row['published'] == true,
              ))
          .firstOrNull);

  Future<String> createAssessment({
    required String cohortId,
    required AssessmentModel assessment,
  }) =>
      _id('upsert', {'table': 'assessments', 'action': 'insert'});

  Future<void> updateAssessment({
    required String cohortId,
    required AssessmentModel assessment,
  }) =>
      _run('upsert', {'table': 'assessments', 'id': assessment.id, 'action': 'update'});

  Future<void> publishAssessment({
    required String cohortId,
    required String assessmentId,
  }) =>
      _run('upsert', {'table': 'assessments', 'id': assessmentId, 'action': 'update'});

  Future<void> deleteAssessment({
    required String cohortId,
    required String assessmentId,
  }) =>
      _run('upsert', {'table': 'assessments', 'id': assessmentId, 'action': 'delete'});

  Stream<List<AssessmentQuestionModel>> watchAssessmentQuestions(
    String cohortId,
    String assessmentId,
  ) =>
      _watch(() => _list('assessmentQuestions')
          .where((row) => '${row['assessmentId']}' == assessmentId)
          .map((row) => AssessmentQuestionModel(
                id: '${row['id']}',
                order: (row['order'] as num?)?.toInt() ?? 0,
                type: AssessmentQuestionType.fromString(row['type'] as String?),
                prompt: row['prompt'] as String? ?? row['stem'] as String? ?? '',
                points: (row['points'] as num?)?.toInt() ?? 0,
              ))
          .toList());

  Future<void> replaceAssessmentQuestions({
    required String cohortId,
    required String assessmentId,
    required List<AssessmentQuestionModel> questions,
  }) async {}

  Stream<List<AssessmentSubmissionModel>> watchMyAssessmentSubmissions(
    String cohortId,
    String userId,
  ) =>
      _watch(() => _list('assessmentSubmissions')
          .where((row) => '${row['userId']}' == userId)
          .map((row) => AssessmentSubmissionModel(
                id: '${row['id']}',
                assessmentId: '${row['assessmentId']}',
                userId: '${row['userId']}',
                userDisplayName: row['userDisplayName'] as String? ?? '',
                answers: const {},
                autoTotalScore: (row['autoTotalScore'] as num?)?.toInt() ?? 0,
                totalScore: (row['totalScore'] as num?)?.toInt() ?? 0,
              ))
          .toList());

  Stream<List<AssessmentSubmissionModel>> watchAssessmentSubmissions(
    String cohortId,
    String assessmentId,
  ) =>
      _watch(() => _list('assessmentSubmissions')
          .where((row) => '${row['assessmentId']}' == assessmentId)
          .map((row) => AssessmentSubmissionModel(
                id: '${row['id']}',
                assessmentId: assessmentId,
                userId: '${row['userId']}',
                userDisplayName: row['userDisplayName'] as String? ?? '',
                answers: const {},
                autoTotalScore: (row['autoTotalScore'] as num?)?.toInt() ?? 0,
                totalScore: (row['totalScore'] as num?)?.toInt() ?? 0,
              ))
          .toList());

  Stream<AssessmentSubmissionModel?> watchAssessmentSubmission(
    String cohortId,
    String submissionId,
  ) =>
      _watch(() => _list('assessmentSubmissions')
          .where((row) => '${row['id']}' == submissionId)
          .map((row) => AssessmentSubmissionModel(
                id: submissionId,
                assessmentId: '${row['assessmentId']}',
                userId: '${row['userId']}',
                userDisplayName: row['userDisplayName'] as String? ?? '',
                answers: const {},
                autoTotalScore: (row['autoTotalScore'] as num?)?.toInt() ?? 0,
                totalScore: (row['totalScore'] as num?)?.toInt() ?? 0,
              ))
          .firstOrNull);

  Stream<List<CurriculumSheetModel>> watchCurriculumSheets(String cohortId) =>
      _watch(() => _forCohort('curriculumSheets', cohortId)
          .map((row) => CurriculumSheetModel(
                id: '${row['id']}',
                title: row['title'] as String? ?? '',
                fileName: row['fileName'] as String? ?? '',
                rows: const [],
              ))
          .toList());

  Stream<CurriculumSheetModel?> watchLatestCurriculumSheet(String cohortId) =>
      _watch(() {
        final rows = _forCohort('curriculumSheets', cohortId);
        if (rows.isEmpty) return null;
        final row = rows.first;
        return CurriculumSheetModel(
          id: '${row['id']}',
          title: row['title'] as String? ?? '',
          fileName: row['fileName'] as String? ?? '',
          rows: const [],
        );
      });

  Stream<CurriculumSheetModel?> watchCurriculumSheet(
    String cohortId,
    String sheetId,
  ) =>
      _watch(() {
        final row = _forCohort('curriculumSheets', cohortId)
            .where((item) => '${item['id']}' == sheetId)
            .firstOrNull;
        if (row == null) return null;
        return CurriculumSheetModel(
          id: sheetId,
          title: row['title'] as String? ?? '',
          fileName: row['fileName'] as String? ?? '',
        );
      });

  Future<String> saveCurriculumSheet({
    required String cohortId,
    required CurriculumSheetModel sheet,
    String? replaceSheetId,
  }) =>
      _id('upsert', {'table': 'curriculum_sheets', 'action': 'insert'});

  Future<void> deleteCurriculumSheet({
    required String cohortId,
    required String sheetId,
  }) =>
      _run('upsert', {'table': 'curriculum_sheets', 'id': sheetId, 'action': 'delete'});

  Stream<List<FormTaskModel>> watchFormTasks(String cohortId) => _watch(
        () => _forCohort('formTasks', cohortId)
            .where((row) => row['published'] == true)
            .map((row) => FormTaskModel(
                  id: '${row['id']}',
                  title: row['title'] as String? ?? '',
                  formUrl: row['formUrl'] as String? ?? '',
                  dueAt: AppDateUtils.timestampToDateTime(row['dueAt']) ?? DateTime.now(),
                  published: true,
                ))
            .toList(),
      );

  Stream<List<FormTaskModel>> watchAllFormTasks(String cohortId) => _watch(
        () => _forCohort('formTasks', cohortId)
            .map((row) => FormTaskModel(
                  id: '${row['id']}',
                  title: row['title'] as String? ?? '',
                  formUrl: row['formUrl'] as String? ?? '',
                  dueAt: AppDateUtils.timestampToDateTime(row['dueAt']) ?? DateTime.now(),
                  published: row['published'] == true,
                ))
            .toList(),
      );

  Stream<FormTaskModel?> watchFormTask(String cohortId, String taskId) =>
      _watch(() {
        final row = _forCohort('formTasks', cohortId)
            .where((item) => '${item['id']}' == taskId)
            .firstOrNull;
        if (row == null) return null;
        return FormTaskModel(
          id: taskId,
          title: row['title'] as String? ?? '',
          formUrl: row['formUrl'] as String? ?? '',
          dueAt: AppDateUtils.timestampToDateTime(row['dueAt']) ?? DateTime.now(),
          published: row['published'] == true,
        );
      });

  Stream<List<FormResponseModel>> watchFormTaskResponses(
    String cohortId,
    String taskId,
  ) =>
      _watch(() => _list('formResponses')
          .where((row) => '${row['taskId']}' == taskId)
          .map((row) => FormResponseModel(
                id: '${row['id'] ?? row['userId']}',
                userId: '${row['userId']}',
                userEmail: row['userEmail'] as String? ?? '',
                taskId: '${row['taskId']}',
                cohortId: '${row['cohortId'] ?? cohortId}',
                submittedAt: AppDateUtils.timestampToDateTime(row['submittedAt']),
              ))
          .toList());

  Stream<List<FormResponseModel>> watchMyFormResponses(
    String cohortId,
    String userId,
  ) =>
      _watch(() => _list('formResponses')
          .where((row) => '${row['userId']}' == userId)
          .map((row) => FormResponseModel(
                id: '${row['id'] ?? userId}',
                userId: userId,
                userEmail: row['userEmail'] as String? ?? '',
                taskId: '${row['taskId']}',
                cohortId: cohortId,
                submittedAt: AppDateUtils.timestampToDateTime(row['submittedAt']),
              ))
          .toList());

  Stream<List<FormTaskWithStatus>> watchFormTasksWithStatus(
    String cohortId,
    String userId,
  ) =>
      watchFormTasks(cohortId).map((tasks) {
        return tasks
            .map((task) => FormTaskWithStatus(task: task, myResponse: null))
            .toList();
      });

  Future<String> createFormTask({
    required String cohortId,
    required FormTaskModel task,
    required String authorId,
  }) =>
      _id('upsert', {'table': 'form_tasks', 'action': 'insert'});

  Future<void> updateFormTask({
    required String cohortId,
    required String taskId,
    required FormTaskModel task,
    required String authorId,
  }) =>
      _run('upsert', {'table': 'form_tasks', 'id': taskId, 'action': 'update'});

  Future<void> deleteFormTask(String cohortId, String taskId) =>
      _run('upsert', {'table': 'form_tasks', 'id': taskId, 'action': 'delete'});

  Future<void> updateProfile({
    required String uid,
    String? motto,
    List<String>? skills,
    Map<String, String>? socialLinks,
    String? birthDate,
    String? personalEmail,
    JobPreferences? jobPreferences,
    String? photoUrl,
    String? photoStoragePath,
  }) {
    return _run('updateProfile', {
      'uid': uid,
      if (motto != null) 'motto': motto,
      if (skills != null) 'skills': skills,
      if (socialLinks != null) 'socialLinks': socialLinks,
      if (birthDate != null) 'birthDate': birthDate,
      if (personalEmail != null) 'personalEmail': personalEmail,
      if (jobPreferences != null) 'jobPreferences': jobPreferences.toMap(),
      if (photoUrl != null) 'photoUrl': photoUrl,
      if (photoStoragePath != null) 'photoStoragePath': photoStoragePath,
    });
  }

  Future<void> updatePersonalEmail({
    required String uid,
    required String personalEmail,
  }) async {
    final normalized = personalEmail.trim().toLowerCase();
    if (normalized.isEmpty) {
      throw const DataException('개인 이메일을 입력해 주세요.');
    }
    final emailRegex = RegExp(r'^[\w-\.]+@([\w-]+\.)+[\w-]{2,}$');
    if (!emailRegex.hasMatch(normalized)) {
      throw const DataException('올바른 이메일 형식이 아닙니다.');
    }
    await updateProfile(uid: uid, personalEmail: normalized);
  }

  Future<String?> getTailoredLinkedJobId({
    required String cohortId,
    required String baseResumeId,
    required String tailoredResumeId,
  }) async {
    await _api.bootstrap();
    final row = _forCohort('resumes', cohortId).where((item) {
      final id = '${item['id']}';
      return id == tailoredResumeId ||
          id.endsWith('/tailored/$tailoredResumeId') ||
          '${item['baseResumeId']}' == baseResumeId &&
              id.contains(tailoredResumeId);
    }).firstOrNull;
    final job = row?['linkedJobId'] ?? row?['jobId'];
    return job == null ? null : '$job';
  }

  Stream<List<AiGenerationLogModel>> watchAiGenerationLogs(String cohortId) =>
      _watch(() => _forCohort('aiGenerationLogs', cohortId)
          .map((row) => AiGenerationLogModel(
                id: '${row['id']}',
                type: row['type'] as String? ?? '',
                promptVersion: row['promptVersion'] as String? ?? '',
                model: row['model'] as String? ?? '',
                cohortId: '${row['cohortId'] ?? cohortId}',
              ))
          .toList());

  Stream<MissionProgressModel> watchMissionProgress(
    String cohortId,
    String uid,
  ) =>
      _watch(() {
        final row = _list('missionProgress')
            .where((item) =>
                '${item['cohortId']}' == cohortId && '${item['userId']}' == uid)
            .firstOrNull;
        if (row == null) return const MissionProgressModel();
        return MissionProgressModel(
          studyCertCount: (row['studyCertCount'] as num?)?.toInt() ?? 0,
          studyCertGranted: (row['studyCertGranted'] as num?)?.toInt() ?? 0,
          quizPassCount: (row['quizPassCount'] as num?)?.toInt() ?? 0,
          quizGranted: (row['quizGranted'] as num?)?.toInt() ?? 0,
          codingPcce: row['codingPcce'] == true,
          codingPccp: row['codingPccp'] == true,
          codingPcsql: row['codingPcsql'] == true,
          codingGranted: (row['codingGranted'] as num?)?.toInt() ?? 0,
          blogWeeks: List<int>.from((row['blogWeeks'] as List? ?? []).map((e) => (e as num).toInt())),
          blogUnitsGranted: List<int>.from(
            (row['blogUnitsGranted'] as List? ?? []).map((e) => (e as num).toInt()),
          ),
          studyWeekKeys: List<String>.from(row['studyWeekKeys'] as List? ?? []),
          studyGranted: row['studyGranted'] == true,
        );
      });
}
