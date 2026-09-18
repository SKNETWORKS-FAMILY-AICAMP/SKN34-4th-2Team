import 'dart:async';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:cloud_functions/cloud_functions.dart';

import '../../core/constants/attendance_status.dart';
import '../../core/constants/firestore_paths.dart';
import '../../core/errors/app_exception.dart';
import '../../core/utils/class_period_utils.dart';
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

/// Firestore CRUD 통합 Repository — cohort 격리 쿼리 중앙화
class LmsRepository {
  LmsRepository(this._firestore);

  final FirebaseFirestore _firestore;

  /// cohorts/{cohortId}/{subcollection} 참조
  CollectionReference<Map<String, dynamic>> cohortSub(
    String cohortId,
    String subcollection,
  ) {
    return _firestore
        .collection('cohorts')
        .doc(cohortId)
        .collection(subcollection);
  }

  // ── TODO (users/{uid}/todos) ──

  Stream<List<TodoModel>> watchTodos(String uid) {
    return _firestore
        .collection(FirestorePaths.users)
        .doc(uid)
        .collection('todos')
        .orderBy('createdAt', descending: true)
        .snapshots()
        .map((s) => s.docs.map(TodoModel.fromFirestore).toList());
  }

  Future<void> addTodo(String uid, String title) async {
    await _firestore
        .collection(FirestorePaths.users)
        .doc(uid)
        .collection('todos')
        .add(TodoModel(id: '', title: title, isCompleted: false).toFirestore());
  }

  Future<void> toggleTodo(String uid, TodoModel todo) async {
    await _firestore
        .collection(FirestorePaths.users)
        .doc(uid)
        .collection('todos')
        .doc(todo.id)
        .update({'isCompleted': !todo.isCompleted});
  }

  Future<void> deleteTodo(String uid, String todoId) async {
    await _firestore
        .collection(FirestorePaths.users)
        .doc(uid)
        .collection('todos')
        .doc(todoId)
        .delete();
  }

  // ── Posts ──

  Stream<List<PostModel>> watchPosts(String cohortId, {int limit = 20}) {
    return cohortSub(cohortId, 'posts')
        .orderBy('createdAt', descending: true)
        .limit(limit)
        .snapshots()
        .map((s) => s.docs.map(PostModel.fromFirestore).toList());
  }

  Future<void> createPost({
    required String cohortId,
    required String authorId,
    required String authorName,
    required String content,
  }) async {
    await cohortSub(cohortId, 'posts').add(
      PostModel(
        id: '',
        authorId: authorId,
        authorName: authorName,
        content: content,
      ).toFirestore(),
    );
  }

  Future<void> deletePost(String cohortId, String postId) async {
    await cohortSub(cohortId, 'posts').doc(postId).delete();
  }

  // ── Notices ──

  Stream<List<NoticeModel>> watchNotices(String cohortId) {
    return cohortSub(cohortId, 'notices')
        .orderBy('isFavorite', descending: true)
        .orderBy('createdAt', descending: true)
        .snapshots()
        .map((s) => s.docs.map(NoticeModel.fromFirestore).toList());
  }

  Future<String> createNotice({
    required String cohortId,
    required NoticeModel notice,
    required String authorId,
    required String authorName,
  }) async {
    final ref = await cohortSub(cohortId, 'notices').add(
      notice.toFirestore(authorId: authorId, authorName: authorName),
    );
    return ref.id;
  }

  Future<void> updateNotice({
    required String cohortId,
    required NoticeModel notice,
    required String authorId,
    required String authorName,
  }) async {
    await cohortSub(cohortId, 'notices').doc(notice.id).update(
          notice.toFirestoreUpdate(
            authorId: authorId,
            authorName: authorName,
          ),
        );
  }

  Future<void> toggleNoticeFavorite({
    required String cohortId,
    required String noticeId,
    required bool isFavorite,
  }) async {
    await cohortSub(cohortId, 'notices').doc(noticeId).update({
      'isFavorite': isFavorite,
      'updatedAt': FieldValue.serverTimestamp(),
    });
  }

  Future<void> deleteNotice(String cohortId, String noticeId) async {
    await cohortSub(cohortId, 'notices').doc(noticeId).delete();
  }

  Stream<List<ScheduledNoticeModel>> watchScheduledNotices(String cohortId) {
    return cohortSub(cohortId, 'scheduledNotices')
        .orderBy('isActive', descending: true)
        .orderBy('nextPublishAt', descending: false)
        .snapshots()
        .map((s) => s.docs.map(ScheduledNoticeModel.fromFirestore).toList());
  }

  Future<String> createScheduledNotice({
    required String cohortId,
    required ScheduledNoticeModel scheduled,
    required String authorId,
    required String authorName,
  }) async {
    final nextAt = computeNextPublishAt(
      repeatType: scheduled.repeatType,
      publishTime: scheduled.publishTime,
      publishAt: scheduled.publishAt,
      weekday: scheduled.weekday,
    );
    final ref = await cohortSub(cohortId, 'scheduledNotices').add(
      scheduled.toFirestore(
        authorId: authorId,
        authorName: authorName,
        nextPublishAt: nextAt,
        isCreate: true,
      ),
    );
    return ref.id;
  }

  Future<void> updateScheduledNotice({
    required String cohortId,
    required ScheduledNoticeModel scheduled,
    required String authorId,
    required String authorName,
  }) async {
    final nextAt = computeNextPublishAt(
      repeatType: scheduled.repeatType,
      publishTime: scheduled.publishTime,
      publishAt: scheduled.publishAt,
      weekday: scheduled.weekday,
    );
    await cohortSub(cohortId, 'scheduledNotices').doc(scheduled.id).update(
          scheduled.toFirestoreUpdate(
            authorId: authorId,
            authorName: authorName,
            nextPublishAt: nextAt,
          ),
        );
  }

  Future<void> toggleScheduledNoticeActive({
    required String cohortId,
    required String scheduledId,
    required bool isActive,
  }) async {
    await cohortSub(cohortId, 'scheduledNotices').doc(scheduledId).update({
      'isActive': isActive,
      'updatedAt': FieldValue.serverTimestamp(),
    });
  }

  Future<void> deleteScheduledNotice(String cohortId, String scheduledId) async {
    await cohortSub(cohortId, 'scheduledNotices').doc(scheduledId).delete();
  }

  // ── Alert Popups (로그인 알림) ──

  List<AlertPopupModel> _alertPopupsFromSnapshot(
    QuerySnapshot<Map<String, dynamic>> snapshot, {
    required bool activeOnly,
  }) {
    final list = <AlertPopupModel>[];
    for (final doc in snapshot.docs) {
      try {
        final popup = AlertPopupModel.fromFirestore(doc);
        if (!activeOnly || popup.isActive) list.add(popup);
      } catch (_) {}
    }
    list.sort((a, b) {
      final byOrder = a.sortOrder.compareTo(b.sortOrder);
      if (byOrder != 0) return byOrder;
      final aAt = a.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0);
      final bAt = b.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0);
      return bAt.compareTo(aAt);
    });
    return list;
  }

  Stream<List<AlertPopupModel>> watchAlertPopups(String cohortId) {
    return cohortSub(cohortId, 'alertPopups').snapshots().map(
          (s) => _alertPopupsFromSnapshot(s, activeOnly: false),
        );
  }

  Stream<List<AlertPopupModel>> watchActiveAlertPopups(String cohortId) {
    return cohortSub(cohortId, 'alertPopups').snapshots().map(
          (s) => _alertPopupsFromSnapshot(s, activeOnly: true),
        );
  }

  Future<String> createAlertPopup({
    required String cohortId,
    required AlertPopupModel popup,
    required String authorId,
    required String authorName,
  }) async {
    final ref = await cohortSub(cohortId, 'alertPopups').add(
      popup.toFirestore(
        authorId: authorId,
        authorName: authorName,
        isCreate: true,
      ),
    );
    return ref.id;
  }

  Future<void> updateAlertPopup({
    required String cohortId,
    required AlertPopupModel popup,
    required String authorId,
    required String authorName,
  }) async {
    await cohortSub(cohortId, 'alertPopups').doc(popup.id).update(
          popup.toFirestore(authorId: authorId, authorName: authorName),
        );
  }

  Future<void> toggleAlertPopupActive({
    required String cohortId,
    required String popupId,
    required bool isActive,
  }) async {
    await cohortSub(cohortId, 'alertPopups').doc(popupId).update({
      'isActive': isActive,
      'updatedAt': FieldValue.serverTimestamp(),
    });
  }

  Future<void> deleteAlertPopup(String cohortId, String popupId) async {
    await cohortSub(cohortId, 'alertPopups').doc(popupId).delete();
  }

  CollectionReference<Map<String, dynamic>> _alertPopupDismissals(String uid) {
    return _firestore
        .collection(FirestorePaths.users)
        .doc(uid)
        .collection('alertPopupDismissals');
  }

  Stream<Map<String, String>> watchAlertPopupDismissals(String uid) {
    return _alertPopupDismissals(uid).snapshots().map((snapshot) {
      final map = <String, String>{};
      for (final doc in snapshot.docs) {
        final dateKey = doc.data()['dateKey'] as String?;
        if (dateKey != null && dateKey.isNotEmpty) {
          map[doc.id] = dateKey;
        }
      }
      return map;
    });
  }

  Future<void> dismissAlertPopupToday({
    required String uid,
    required String popupId,
    required String dateKey,
  }) async {
    await _alertPopupDismissals(uid).doc(popupId).set({
      'dateKey': dateKey,
      'updatedAt': FieldValue.serverTimestamp(),
    });
  }

  // ── Submissions ──

  Stream<List<SubmissionModel>> watchMySubmissions(
    String cohortId,
    String userId,
  ) {
    return cohortSub(cohortId, 'submissions')
        .where('userId', isEqualTo: userId)
        .orderBy('submittedAt', descending: true)
        .snapshots()
        .map((s) => s.docs.map(SubmissionModel.fromFirestore).toList());
  }

  Stream<List<SubmissionModel>> watchAllSubmissions(String cohortId) {
    return cohortSub(cohortId, 'submissions')
        .orderBy('submittedAt', descending: true)
        .limit(50)
        .snapshots()
        .map((s) => s.docs.map(SubmissionModel.fromFirestore).toList());
  }

  Future<String> createSubmission({
    required String cohortId,
    required SubmissionModel submission,
  }) async {
    final ref = submission.id.isNotEmpty
        ? cohortSub(cohortId, 'submissions').doc(submission.id)
        : cohortSub(cohortId, 'submissions').doc();
    await ref.set(submission.toFirestore());
    return ref.id;
  }

  Future<void> reviewSubmission({
    required String cohortId,
    required String submissionId,
    required String status,
    String? reviewComment,
  }) async {
    try {
      final callable = FirebaseFunctions.instanceFor(
        region: 'asia-northeast3',
      ).httpsCallable('reviewSubmission');
      await callable.call<Map<String, dynamic>>({
        'cohortId': cohortId,
        'submissionId': submissionId,
        'status': status,
        if (reviewComment != null && reviewComment.isNotEmpty)
          'comment': reviewComment,
      });
    } on FirebaseFunctionsException catch (e) {
      throw DataException(
        e.message ?? '제출물 검토에 실패했습니다.',
        code: e.code,
      );
    }
  }

  // ── Weekly Tasks & Progress ──

  Stream<WeeklyTaskModel?> watchCurrentWeeklyTask(String cohortId) {
    return cohortSub(cohortId, 'weeklyTasks')
        .orderBy('dueDate', descending: false)
        .limit(1)
        .snapshots()
        .map((s) => s.docs.isEmpty
            ? null
            : WeeklyTaskModel.fromFirestore(s.docs.first));
  }

  Stream<UserProgressModel?> watchUserProgress(String cohortId, String userId) {
    return cohortSub(cohortId, 'userProgress')
        .doc(userId)
        .snapshots()
        .map((doc) =>
            doc.exists ? UserProgressModel.fromFirestore(doc) : null);
  }

  // ── Cohort ──

  Stream<List<CohortModel>> watchCohorts() {
    return watchAllCohorts().map(
      (list) => list.where((c) => c.isSelectable).toList(),
    );
  }

  Stream<List<CohortModel>> watchAllCohorts() {
    return _firestore.collection('cohorts').snapshots().map((snap) {
      final list = snap.docs.map(CohortModel.fromFirestore).toList();
      list.sort((a, b) {
        final ta = a.termNumber ?? 0;
        final tb = b.termNumber ?? 0;
        if (ta != tb) return tb.compareTo(ta);
        return a.name.compareTo(b.name);
      });
      return list;
    });
  }

  Future<String> createCohort(CohortModel cohort) async {
    final id = cohort.cohortId.isNotEmpty
        ? cohort.cohortId
        : (cohort.termNumber != null
            ? 'cohort_${cohort.termNumber}'
            : _firestore.collection('cohorts').doc().id);
    final data = cohort.toFirestore(isCreate: true);
    await _firestore.collection('cohorts').doc(id).set(data);
    return id;
  }

  Future<void> updateCohort(CohortModel cohort) async {
    final students = await _firestore
        .collection(FirestorePaths.users)
        .where('cohortId', isEqualTo: cohort.cohortId)
        .where('role', isEqualTo: 'student')
        .get();

    final activeStudentCount = students.docs
        .where((doc) => doc.data()['isActive'] != false)
        .length;

    await _firestore.collection('cohorts').doc(cohort.cohortId).update({
      ...cohort.toFirestore(),
      'studentCount': activeStudentCount,
    });

    // 기수명은 users에도 표시용으로 중복 저장되어 있으므로 함께 맞춘다.
    // Firestore batch 제한에 여유를 두고 나눠 처리한다.
    final namesToUpdate = students.docs
        .where((doc) => doc.data()['cohortName'] != cohort.name)
        .toList();
    for (var offset = 0; offset < namesToUpdate.length; offset += 450) {
      final end = (offset + 450 < namesToUpdate.length)
          ? offset + 450
          : namesToUpdate.length;
      final batch = _firestore.batch();
      for (final doc in namesToUpdate.sublist(offset, end)) {
        batch.update(doc.reference, {
          'cohortName': cohort.name,
          'updatedAt': FieldValue.serverTimestamp(),
        });
      }
      await batch.commit();
    }
  }

  Stream<List<CohortWithResumes>> watchAllCohortsWithResumes() {
    return _firestore.collection('cohorts').orderBy('name').snapshots().asyncExpand(
      (cohortSnap) {
        final cohorts = cohortSnap.docs
            .map(CohortModel.fromFirestore)
            .where((c) => c.isSelectable)
            .toList();
        if (cohorts.isEmpty) return Stream.value(<CohortWithResumes>[]);
        return _mergeCohortResumeStreams(cohorts);
      },
    );
  }

  Stream<List<CohortWithResumes>> _mergeCohortResumeStreams(
    List<CohortModel> cohorts,
  ) {
    late StreamController<List<CohortWithResumes>> controller;
    final latest = List<List<ResumeModel>?>.filled(cohorts.length, null);
    final subscriptions = <StreamSubscription<dynamic>>[];

    void emitIfReady() {
      if (latest.any((e) => e == null)) return;
      if (controller.isClosed) return;
      controller.add([
        for (var i = 0; i < cohorts.length; i++)
          CohortWithResumes(cohort: cohorts[i], resumes: latest[i]!),
      ]);
    }

    controller = StreamController<List<CohortWithResumes>>(
      onListen: () {
        for (var i = 0; i < cohorts.length; i++) {
          final cohort = cohorts[i];
          subscriptions.add(
            cohortSub(cohort.cohortId, 'resumes').snapshots().listen((snap) {
              latest[i] = snap.docs.map(ResumeModel.fromFirestore).toList();
              emitIfReady();
            }),
          );
        }
      },
      onCancel: () async {
        for (final sub in subscriptions) {
          await sub.cancel();
        }
      },
    );
    return controller.stream;
  }

  // ── Resume ──

  Stream<List<ResumeModel>> watchMyResumes(String cohortId, String userId) {
    return cohortSub(cohortId, 'resumes')
        .where('userId', isEqualTo: userId)
        .snapshots()
        .map((s) => s.docs.map(ResumeModel.fromFirestore).toList());
  }

  Stream<List<ResumeModel>> watchCohortResumes(String cohortId) {
    return cohortSub(cohortId, 'resumes')
        .snapshots()
        .map((s) => s.docs.map(ResumeModel.fromFirestore).toList());
  }

  Future<String> createResume({
    required String cohortId,
    required String userId,
    required String title,
    bool isBaseResume = false,
  }) async {
    final doc = await cohortSub(cohortId, 'resumes').add({
      ...ResumeModel(
        id: '',
        userId: userId,
        title: title,
        status: 'writing',
        sections: const {},
        isBaseResume: isBaseResume,
      ).toFirestore(isCreate: true),
    });
    return doc.id;
  }

  /// 사용자당 기본 이력서는 하나만 유지한다. 공고별 첨삭본은 이 문서의
  /// 하위 tailoredResumes에 저장되므로 여기 목록에 섞이지 않는다.
  Future<void> setBaseResume({
    required String cohortId,
    required String userId,
    required String resumeId,
  }) async {
    final resumes = await cohortSub(cohortId, 'resumes')
        .where('userId', isEqualTo: userId)
        .get();
    if (!resumes.docs.any((document) => document.id == resumeId)) {
      throw StateError('내 이력서만 기본 이력서로 등록할 수 있습니다.');
    }
    final batch = _firestore.batch();
    for (final document in resumes.docs) {
      batch.update(document.reference, {
        'isBaseResume': document.id == resumeId,
        'updatedAt': FieldValue.serverTimestamp(),
      });
    }
    await batch.commit();
  }

  Future<void> updateResumeSections({
    required String cohortId,
    required String resumeId,
    required Map<String, bool> sections,
    required String status,
  }) async {
    await updateResume(
      cohortId: cohortId,
      resumeId: resumeId,
      sections: sections,
      status: status,
    );
  }

  Stream<ResumeModel?> watchResume(String cohortId, String resumeId) {
    return cohortSub(cohortId, 'resumes')
        .doc(resumeId)
        .snapshots()
        .map((doc) => doc.exists ? ResumeModel.fromFirestore(doc) : null);
  }

  Future<void> updateResume({
    required String cohortId,
    required String resumeId,
    String? title,
    ResumeContent? content,
    Map<String, bool>? sections,
    String? status,
    bool incrementRevision = false,
  }) async {
    final updates = <String, dynamic>{
      'updatedAt': FieldValue.serverTimestamp(),
    };
    if (title != null) updates['title'] = title;
    if (content != null) {
      updates['content'] = content.toMap();
      updates['sections'] = content.computeSections();
    }
    if (sections != null) updates['sections'] = sections;
    if (status != null) updates['status'] = status;
    if (incrementRevision) {
      updates['revisionCount'] = FieldValue.increment(1);
    }

    final docRef = cohortSub(cohortId, 'resumes').doc(resumeId);
    await docRef.update(updates);

    if (incrementRevision && content != null) {
      await docRef.collection('revisions').add({
        'title': title,
        'content': content.toMap(),
        'savedAt': FieldValue.serverTimestamp(),
      });
    }
  }

  /// 마이페이지의 생년월일은 사실 정보이므로, 같은 기수의 승인 전 이력서에도
  /// 함께 반영한다. 승인된 이력서는 제출 당시의 기록을 보존한다.
  Future<int> syncBirthDateToMyResumes({
    required String cohortId,
    required String userId,
    required String birthDate,
  }) async {
    final normalized = birthDate.trim();
    if (cohortId.isEmpty || normalized.isEmpty) return 0;

    final resumes = await cohortSub(cohortId, 'resumes')
        .where('userId', isEqualTo: userId)
        .get();
    final targets = resumes.docs.where((doc) {
      final resume = ResumeModel.fromFirestore(doc);
      return !resume.isApproved &&
          resume.content.basicInfo.birthDate != normalized;
    }).toList();

    // Firestore batch는 최대 500개 쓰기다. 사용자 이력서는 보통 훨씬 적지만
    // 안전하게 여유를 둔 단위로 나눈다.
    for (var start = 0; start < targets.length; start += 450) {
      final end = (start + 450).clamp(0, targets.length);
      final batch = _firestore.batch();
      for (final doc in targets.sublist(start, end)) {
        batch.update(doc.reference, {
          'content.basicInfo.birthDate': normalized,
          'updatedAt': FieldValue.serverTimestamp(),
        });
      }
      await batch.commit();
    }
    return targets.length;
  }

  Future<void> approveResume({
    required String cohortId,
    required String resumeId,
  }) async {
    await cohortSub(cohortId, 'resumes').doc(resumeId).update({
      'status': 'approved',
      'updatedAt': FieldValue.serverTimestamp(),
    });
  }

  Future<void> deleteResume(String cohortId, String resumeId) async {
    await cohortSub(cohortId, 'resumes').doc(resumeId).delete();
  }

  Stream<List<ResumeFeedbackModel>> watchResumeFeedback(
    String cohortId,
    String resumeId,
  ) {
    return cohortSub(cohortId, 'resumes')
        .doc(resumeId)
        .collection('feedback')
        .orderBy('createdAt', descending: true)
        .snapshots()
        .map((s) => s.docs.map(ResumeFeedbackModel.fromFirestore).toList());
  }

  Future<void> addResumeFeedback({
    required String cohortId,
    required String resumeId,
    required ResumeFeedbackModel feedback,
    required String authorId,
    required String authorName,
  }) async {
    final batch = _firestore.batch();
    final feedbackRef = cohortSub(cohortId, 'resumes')
        .doc(resumeId)
        .collection('feedback')
        .doc();
    batch.set(
      feedbackRef,
      feedback.toFirestore(authorId: authorId, authorName: authorName),
    );
    batch.update(cohortSub(cohortId, 'resumes').doc(resumeId), {
      'feedbackCount': FieldValue.increment(1),
    });
    await batch.commit();
  }

  /// 내가 쓴 피드백·답글을 지운다.
  ///
  /// 글 하나를 지우고 이력서의 건수를 같이 줄인다. 건수만 남으면 안 읽음 숫자가
  /// 실제 글 수와 어긋나 영영 줄지 않는다.
  ///
  /// 답글이 달린 글을 지워도 답글은 남긴다. 남의 글을 대신 지우는 셈이 되고,
  /// 화면은 부모 없는 답글을 첫 글로 올려 보여 준다.
  Future<void> deleteResumeFeedback({
    required String cohortId,
    required String resumeId,
    required String feedbackId,
  }) async {
    final batch = _firestore.batch();
    batch.delete(
      cohortSub(cohortId, 'resumes')
          .doc(resumeId)
          .collection('feedback')
          .doc(feedbackId),
    );
    batch.update(cohortSub(cohortId, 'resumes').doc(resumeId), {
      'feedbackCount': FieldValue.increment(-1),
    });
    await batch.commit();
  }

  /// 피드백을 화면에서 읽었다. **여기서만** 읽음으로 넘어간다.
  ///
  /// 보는 사람에 따라 다른 자리에 적는다. 학생이 읽은 것과 검토자가 읽은 것이
  /// 섞이면, 한쪽이 읽었다고 다른 쪽 숫자까지 줄어든다. 검토자는 사람마다 따로 센다
  /// ([reviewerReadKey]).
  Future<void> markResumeFeedbackRead({
    required String cohortId,
    required String resumeId,
    required List<String> feedbackIds,
    required bool asReviewer,
    String? viewerId,
  }) async {
    if (feedbackIds.isEmpty) return;
    final field = asReviewer ? 'reviewerReadFeedbackIds' : 'readFeedbackIds';
    await cohortSub(cohortId, 'resumes').doc(resumeId).update({
      field: FieldValue.arrayUnion([
        for (final id in feedbackIds)
          asReviewer ? reviewerReadKey(viewerId, id) : id,
      ]),
    });
  }

  Future<void> markResumeFeedbackSeen({
    required String cohortId,
    required String resumeId,
    required int feedbackCount,
  }) async {
    await cohortSub(cohortId, 'resumes').doc(resumeId).update({
      'lastSeenFeedbackCount': feedbackCount,
    });
  }

  // ── Attendance ──

  Stream<List<AttendanceModel>> watchUserAttendances(
    String cohortId,
    String userId,
  ) {
    return cohortSub(cohortId, 'attendances')
        .where('userId', isEqualTo: userId)
        .orderBy('dateKey', descending: true)
        .limit(400)
        .snapshots()
        .map((s) => s.docs.map(AttendanceModel.fromFirestore).toList());
  }

  Stream<List<AttendanceModel>> watchMyAttendances(
    String cohortId,
    String userId,
  ) =>
      watchUserAttendances(cohortId, userId);

  Stream<List<AttendanceModel>> watchAttendancesByDate(
    String cohortId,
    String dateKey,
  ) {
    return cohortSub(cohortId, 'attendances')
        .where('dateKey', isEqualTo: dateKey)
        .snapshots()
        .map((s) {
      final byUser = <String, AttendanceModel>{};
      for (final doc in s.docs) {
        final model = AttendanceModel.fromFirestore(doc);
        if (model.userId.isEmpty) continue;
        final prev = byUser[model.userId];
        if (prev == null || model.dayStatus != null) {
          byUser[model.userId] = model;
        }
      }
      return byUser.values.toList();
    });
  }

  Future<int> seedDemoAttendances({
    required String cohortId,
    required String dateKey,
    required List<UserModel> students,
    required DemoAttendanceSeed seed,
  }) async {
    if (students.isEmpty) return 0;
    final col = cohortSub(cohortId, 'attendances');
    final existing = await col.where('dateKey', isEqualTo: dateKey).get();
    final existingByUser = <String, Map<String, dynamic>>{};
    for (final doc in existing.docs) {
      final data = doc.data();
      final uid = data['userId'] as String? ?? '';
      if (uid.isNotEmpty) existingByUser[uid] = data;
    }

    final writes = <Map<String, dynamic>>[];
    for (final student in students) {
      final prev = existingByUser[student.uid];
      final source = prev?['statusSource'] as String?;
      if (source == 'form' || source == 'manual') continue;

      final hash = student.uid.hashCode.abs() + dateKey.hashCode.abs();
      final missing = hash % 17 == 0;
      // merge 시 상대 필드를 null로 덮지 않도록, 채우는 쪽만 맵에 넣는다.
      final data = <String, dynamic>{
        'userId': student.uid,
        'userDisplayName': student.displayName,
        'dateKey': dateKey,
        'type': 'status',
        'statusSource': 'demo',
        'timestamp': FieldValue.serverTimestamp(),
        'updatedAt': FieldValue.serverTimestamp(),
      };

      if (seed == DemoAttendanceSeed.checkIn) {
        data['checkInTime'] =
            missing ? null : _formatHm(8 * 60 + 48 + (hash % 18));
        data['checkInSource'] = 'demo';
        data['status'] = missing
            ? AttendanceStatus.absent
            : AttendanceStatus.present;
      } else {
        if (missing) continue;
        data['checkOutTime'] = _formatHm(17 * 60 + 50 + (hash % 20));
        if (prev?['status'] == null) {
          data['status'] = AttendanceStatus.present;
        }
      }

      writes.add(data);
    }

    var written = 0;
    const chunkSize = 400;
    for (var i = 0; i < writes.length; i += chunkSize) {
      final batch = _firestore.batch();
      final slice = writes.sublist(
        i,
        i + chunkSize > writes.length ? writes.length : i + chunkSize,
      );
      for (final data in slice) {
        final uid = data['userId'] as String;
        batch.set(
          col.doc('${uid}_$dateKey'),
          data,
          SetOptions(merge: true),
        );
      }
      await batch.commit();
      written += slice.length;
    }
    return written;
  }

  static String _formatHm(int totalMinutes) {
    final h = totalMinutes ~/ 60;
    final m = totalMinutes % 60;
    return '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}';
  }

  Future<bool> ensureDailyAttendanceFormNotice({
    required String cohortId,
    required String authorId,
    required String authorName,
  }) async {
    final existing = await cohortSub(cohortId, 'scheduledNotices')
        .where('presetKey', isEqualTo: AttendanceForm.dailyNoticePresetKey)
        .limit(1)
        .get();
    if (existing.docs.isNotEmpty) return false;

    final scheduled = ScheduledNoticeModel(
      id: '',
      title: AttendanceForm.dailyNoticeTitle,
      content: AttendanceForm.dailyNoticeContent,
      authorName: authorName,
      isFavorite: true,
      repeatType: ScheduleRepeatType.daily,
      publishTime: '08:30',
    );
    final nextAt = computeNextPublishAt(
      repeatType: scheduled.repeatType,
      publishTime: scheduled.publishTime,
    );
    await cohortSub(cohortId, 'scheduledNotices').add({
      ...scheduled.toFirestore(
        authorId: authorId,
        authorName: authorName,
        nextPublishAt: nextAt,
        isCreate: true,
      ),
      'presetKey': AttendanceForm.dailyNoticePresetKey,
    });
    return true;
  }

  Future<void> upsertAttendanceStatus({
    required String cohortId,
    required String userId,
    required String userDisplayName,
    required String dateKey,
    required String status,
  }) async {
    final docId = '${userId}_$dateKey';
    await cohortSub(cohortId, 'attendances').doc(docId).set(
      {
        'userId': userId,
        'userDisplayName': userDisplayName,
        'dateKey': dateKey,
        'status': status,
        'type': 'status',
        'statusSource': 'manual',
        'timestamp': FieldValue.serverTimestamp(),
        'updatedAt': FieldValue.serverTimestamp(),
      },
      SetOptions(merge: true),
    );
  }

  Future<void> clearAttendanceStatus({
    required String cohortId,
    required String userId,
    required String dateKey,
  }) async {
    final docId = '${userId}_$dateKey';
    await cohortSub(cohortId, 'attendances').doc(docId).delete();
  }

  Stream<Set<String>> watchRollCallConfirmed(
    String cohortId,
    String dateKey,
    String periodId,
  ) {
    final docId = '${dateKey}_p$periodId';
    return cohortSub(cohortId, 'rollCalls').doc(docId).snapshots().map((doc) {
      final raw = doc.data()?['confirmedUserIds'];
      if (raw is! List) return <String>{};
      return raw.map((e) => e.toString()).toSet();
    });
  }

  Stream<Set<String>> watchRollCallHeld(
    String cohortId,
    String dateKey,
    String periodId,
  ) {
    final docId = '${dateKey}_p$periodId';
    return cohortSub(cohortId, 'rollCalls').doc(docId).snapshots().map((doc) {
      final raw = doc.data()?['heldUserIds'];
      if (raw is! List) return <String>{};
      return raw.map((e) => e.toString()).toSet();
    });
  }

  /// 현재 교시 문서가 없으면 직전 교시(확인만)를 복사해 이어받음. 보류는 이어받지 않음.
  Future<void> ensureRollCallCarriedForward({
    required String cohortId,
    required String dateKey,
    required String periodId,
    required String updatedBy,
  }) async {
    final docRef =
        cohortSub(cohortId, 'rollCalls').doc('${dateKey}_p$periodId');
    final snap = await docRef.get();
    if (snap.exists) return;

    var prev = ClassPeriodUtils.previousPeriod(periodId);
    while (prev != null) {
      final prevSnap = await cohortSub(cohortId, 'rollCalls')
          .doc('${dateKey}_p${prev.id}')
          .get();
      if (prevSnap.exists) {
        final raw = prevSnap.data()?['confirmedUserIds'];
        final confirmed = raw is List
            ? raw.map((e) => e.toString()).toList()
            : <String>[];
        await docRef.set({
          'dateKey': dateKey,
          'periodId': periodId,
          'confirmedUserIds': confirmed,
          'heldUserIds': <String>[],
          'carriedFromPeriodId': prev.id,
          'updatedAt': FieldValue.serverTimestamp(),
          'updatedBy': updatedBy,
        });
        return;
      }
      prev = ClassPeriodUtils.previousPeriod(prev.id);
    }
  }

  Future<void> setRollCallConfirmed({
    required String cohortId,
    required String dateKey,
    required String periodId,
    required String userId,
    required bool confirmed,
    required String updatedBy,
  }) async {
    await ensureRollCallCarriedForward(
      cohortId: cohortId,
      dateKey: dateKey,
      periodId: periodId,
      updatedBy: updatedBy,
    );
    final docId = '${dateKey}_p$periodId';
    await cohortSub(cohortId, 'rollCalls').doc(docId).set(
      {
        'dateKey': dateKey,
        'periodId': periodId,
        'confirmedUserIds': confirmed
            ? FieldValue.arrayUnion([userId])
            : FieldValue.arrayRemove([userId]),
        if (confirmed) 'heldUserIds': FieldValue.arrayRemove([userId]),
        'updatedAt': FieldValue.serverTimestamp(),
        'updatedBy': updatedBy,
      },
      SetOptions(merge: true),
    );
  }

  Future<void> setRollCallHeld({
    required String cohortId,
    required String dateKey,
    required String periodId,
    required String userId,
    required bool held,
    required String updatedBy,
  }) async {
    await ensureRollCallCarriedForward(
      cohortId: cohortId,
      dateKey: dateKey,
      periodId: periodId,
      updatedBy: updatedBy,
    );
    final docId = '${dateKey}_p$periodId';
    await cohortSub(cohortId, 'rollCalls').doc(docId).set(
      {
        'dateKey': dateKey,
        'periodId': periodId,
        'heldUserIds': held
            ? FieldValue.arrayUnion([userId])
            : FieldValue.arrayRemove([userId]),
        if (held) 'confirmedUserIds': FieldValue.arrayRemove([userId]),
        'updatedAt': FieldValue.serverTimestamp(),
        'updatedBy': updatedBy,
      },
      SetOptions(merge: true),
    );
  }

  Stream<List<UserModel>> watchCohortStudents(String cohortId) {
    return _firestore
        .collection(FirestorePaths.users)
        .where('cohortId', isEqualTo: cohortId)
        .where('role', isEqualTo: 'student')
        .where('isActive', isEqualTo: true)
        .snapshots()
        .map((s) => s.docs.map(UserModel.fromFirestore).toList());
  }

  Stream<List<UserModel>> watchInstructors() {
    return _firestore
        .collection(FirestorePaths.users)
        .where('role', isEqualTo: 'instructor')
        .snapshots()
        .map((s) {
      final list = s.docs.map(UserModel.fromFirestore).toList();
      list.sort((a, b) => a.displayName.compareTo(b.displayName));
      return list;
    });
  }

  Future<void> recordAttendance({
    required String cohortId,
    required String userId,
    required String userDisplayName,
    required String type,
    required String dateKey,
  }) async {
    await cohortSub(cohortId, 'attendances').add(
      AttendanceModel(
        id: '',
        userId: userId,
        type: type,
        dateKey: dateKey,
      ).toFirestore(userDisplayName: userDisplayName),
    );
  }

  // ── Mileage ──

  Stream<List<MileageTransactionModel>> watchMyMileageTransactions(
    String cohortId,
    String userId,
  ) {
    return cohortSub(cohortId, 'mileageTransactions')
        .where('userId', isEqualTo: userId)
        .orderBy('createdAt', descending: true)
        .limit(30)
        .snapshots()
        .map((s) => s.docs.map(MileageTransactionModel.fromFirestore).toList());
  }

  // ── Schedule ──

  Stream<ScheduleModel?> watchSchedule(String cohortId, String dateKey) {
    return cohortSub(cohortId, 'schedules')
        .doc(dateKey)
        .snapshots()
        .map((doc) => doc.exists ? ScheduleModel.fromFirestore(doc) : null);
  }

  Stream<List<String>> watchScheduleDateKeys(String cohortId) {
    return cohortSub(cohortId, 'schedules')
        .snapshots()
        .map((s) => s.docs.map((d) => d.id).toList());
  }

  // ── Materials ──

  Stream<List<MaterialModel>> watchMaterials(String cohortId) {
    return cohortSub(cohortId, 'materials')
        .orderBy('createdAt', descending: true)
        .snapshots()
        .map((s) => s.docs.map(MaterialModel.fromFirestore).toList());
  }

  // ── Assignments ──

  Stream<List<AssignmentModel>> watchAssignments(String cohortId) {
    return cohortSub(cohortId, 'assignments')
        .orderBy('dueDate', descending: false)
        .snapshots()
        .map((s) => s.docs.map(AssignmentModel.fromFirestore).toList());
  }

  Future<void> submitAssignment({
    required String cohortId,
    required String assignmentId,
    required String userId,
    required String userDisplayName,
    required String fileUrl,
    required String fileName,
    required int fileSizeBytes,
  }) async {
    await cohortSub(cohortId, 'assignments')
        .doc(assignmentId)
        .collection('submissions')
        .doc(userId)
        .set({
          'userId': userId,
          'userDisplayName': userDisplayName,
          'fileUrl': fileUrl,
          'fileName': fileName,
          'fileSizeBytes': fileSizeBytes,
          'submittedAt': FieldValue.serverTimestamp(),
          'status': 'submitted',
        });
  }

  // ── Inflearn Packages (학습실) ──

  Stream<List<InflearnPackageModel>> watchInflearnPackages(String cohortId) {
    return cohortSub(cohortId, 'inflearnPackages')
        .orderBy('sortOrder')
        .snapshots()
        .map((s) => s.docs.map(InflearnPackageModel.fromFirestore).toList());
  }

  Stream<List<InflearnPackageModel>> watchPublishedInflearnPackages(
    String cohortId,
  ) {
    return watchInflearnPackages(cohortId).map(
      (list) => list.where((p) => p.isPublished).toList(),
    );
  }

  Future<String> createInflearnPackage({
    required String cohortId,
    required InflearnPackageModel package,
  }) async {
    final ref = cohortSub(cohortId, 'inflearnPackages').doc();
    await ref.set(package.toFirestore(isCreate: true));
    return ref.id;
  }

  Future<void> updateInflearnPackage({
    required String cohortId,
    required String packageId,
    required Map<String, dynamic> updates,
  }) async {
    final normalized = Map<String, dynamic>.from(updates);
    if (normalized['publishedAt'] is DateTime) {
      normalized['publishedAt'] =
          Timestamp.fromDate(normalized['publishedAt'] as DateTime);
    }
    await cohortSub(cohortId, 'inflearnPackages').doc(packageId).update({
      ...normalized,
      'updatedAt': FieldValue.serverTimestamp(),
    });
  }

  Future<void> deleteInflearnPackage({
    required String cohortId,
    required String packageId,
  }) async {
    await cohortSub(cohortId, 'inflearnPackages').doc(packageId).delete();
  }

  // ── Study sources (공부방) ──

  Stream<List<StudySourceModel>> watchStudySources(String cohortId) {
    return cohortSub(cohortId, 'studySources')
        .orderBy('sortOrder')
        .snapshots()
        .map((s) => s.docs.map(StudySourceModel.fromFirestore).toList());
  }

  Stream<List<StudySourceModel>> watchActiveStudySources(String cohortId) {
    return cohortSub(cohortId, 'studySources')
        .where('isActive', isEqualTo: true)
        .snapshots()
        .map((s) {
          final list = s.docs.map(StudySourceModel.fromFirestore).toList()
            ..sort((a, b) => a.sortOrder.compareTo(b.sortOrder));
          return list;
        });
  }

  Stream<List<StudyNoteModel>> watchReadyStudyNotes(String uid) {
    return _firestore
        .collection(FirestorePaths.users)
        .doc(uid)
        .collection('studyNotes')
        .where('status', isEqualTo: 'ready')
        .snapshots()
        .map((s) => s.docs.map(StudyNoteModel.fromFirestore).toList());
  }

  Future<String> createStudySource({
    required String cohortId,
    required StudySourceModel source,
  }) async {
    final ref = cohortSub(cohortId, 'studySources').doc();
    await ref.set(source.toFirestore(isCreate: true));
    return ref.id;
  }

  Future<void> updateStudySource({
    required String cohortId,
    required String sourceId,
    required Map<String, dynamic> updates,
  }) async {
    await cohortSub(cohortId, 'studySources').doc(sourceId).update({
      ...updates,
      'updatedAt': FieldValue.serverTimestamp(),
    });
  }

  // ── YouTube Recommendations (학습실 관심사 추천) ──

  Stream<List<YoutubeRecommendationModel>> watchYoutubeRecommendations(
    String cohortId,
  ) {
    return cohortSub(cohortId, 'youtubeRecommendations')
        .orderBy('sortOrder')
        .snapshots()
        .map(
          (s) => s.docs.map(YoutubeRecommendationModel.fromFirestore).toList(),
        );
  }

  Stream<List<YoutubeRecommendationModel>> watchPublishedYoutubeRecommendations(
    String cohortId,
  ) {
    return watchYoutubeRecommendations(cohortId).map(
      (list) => list.where((v) => v.isPublished).toList(),
    );
  }

  Future<String> createYoutubeRecommendation({
    required String cohortId,
    required YoutubeRecommendationModel video,
  }) async {
    final ref = cohortSub(cohortId, 'youtubeRecommendations').doc();
    await ref.set(video.toFirestore(isCreate: true));
    return ref.id;
  }

  Future<void> updateYoutubeRecommendation({
    required String cohortId,
    required String videoId,
    required Map<String, dynamic> updates,
  }) async {
    await cohortSub(cohortId, 'youtubeRecommendations').doc(videoId).update({
      ...updates,
      'updatedAt': FieldValue.serverTimestamp(),
    });
  }

  Future<void> deleteYoutubeRecommendation({
    required String cohortId,
    required String videoId,
  }) async {
    await cohortSub(cohortId, 'youtubeRecommendations').doc(videoId).delete();
  }

  /// 추천 클릭/오픈 이벤트 (향후 ML용 로그)
  Future<void> logRecommendationEvent({
    required String cohortId,
    required String userId,
    required String videoDocId,
    required String youtubeVideoId,
    required List<String> userSkills,
    required List<String> matchedTags,
    String action = 'open',
  }) async {
    await cohortSub(cohortId, 'recommendationEvents').add({
      'userId': userId,
      'videoDocId': videoDocId,
      'youtubeVideoId': youtubeVideoId,
      'userSkills': userSkills,
      'matchedTags': matchedTags,
      'action': action,
      'createdAt': FieldValue.serverTimestamp(),
    });
  }

  // ── Assessments (성취도 평가 — 인앱 퀴즈) ──

  Stream<List<AssessmentModel>> watchAssessments(String cohortId) {
    return cohortSub(cohortId, 'assessments')
        .orderBy('startAt', descending: true)
        .snapshots()
        .map((s) => s.docs.map(AssessmentModel.fromFirestore).toList());
  }

  Stream<List<AssessmentModel>> watchPublishedAssessments(String cohortId) {
    // published 단일 필터만 사용 (복합 인덱스 불필요). 정렬은 클라이언트.
    return cohortSub(cohortId, 'assessments')
        .where('published', isEqualTo: true)
        .snapshots()
        .map((s) {
      final list = s.docs.map(AssessmentModel.fromFirestore).toList()
        ..sort((a, b) => b.startAt.compareTo(a.startAt));
      return list;
    });
  }

  Stream<AssessmentModel?> watchAssessment(
    String cohortId,
    String assessmentId,
  ) {
    return cohortSub(cohortId, 'assessments')
        .doc(assessmentId)
        .snapshots()
        .map((s) => s.exists ? AssessmentModel.fromFirestore(s) : null);
  }

  Future<String> createAssessment({
    required String cohortId,
    required AssessmentModel assessment,
  }) async {
    final ref = cohortSub(cohortId, 'assessments').doc();
    await ref.set(assessment.toFirestore());
    return ref.id;
  }

  Future<void> updateAssessment({
    required String cohortId,
    required String assessmentId,
    required Map<String, dynamic> updates,
  }) async {
    final normalized = Map<String, dynamic>.from(updates);
    if (normalized['startAt'] is DateTime) {
      normalized['startAt'] =
          Timestamp.fromDate(normalized['startAt'] as DateTime);
    }
    if (normalized['endAt'] is DateTime) {
      normalized['endAt'] = Timestamp.fromDate(normalized['endAt'] as DateTime);
    }
    if (normalized['curriculumSource'] is AssessmentCurriculumSource) {
      normalized['curriculumSource'] =
          (normalized['curriculumSource'] as AssessmentCurriculumSource)
              .toMap();
    }
    if (normalized['notionSource'] is AssessmentCurriculumSource) {
      normalized['curriculumSource'] =
          (normalized['notionSource'] as AssessmentCurriculumSource).toMap();
      normalized.remove('notionSource');
    }
    await cohortSub(cohortId, 'assessments').doc(assessmentId).update({
      ...normalized,
      'updatedAt': FieldValue.serverTimestamp(),
    });
  }

  Future<void> publishAssessment({
    required String cohortId,
    required String assessmentId,
    bool published = true,
  }) async {
    await cohortSub(cohortId, 'assessments').doc(assessmentId).update({
      'published': published,
      'updatedAt': FieldValue.serverTimestamp(),
    });
  }

  Future<void> deleteAssessment({
    required String cohortId,
    required String assessmentId,
  }) async {
    final assessmentRef =
        cohortSub(cohortId, 'assessments').doc(assessmentId);
    final questions = await assessmentRef.collection('questions').get();
    final batch = _firestore.batch();
    for (final doc in questions.docs) {
      batch.delete(doc.reference);
    }
    batch.delete(assessmentRef);
    await batch.commit();
  }

  Stream<List<AssessmentQuestionModel>> watchAssessmentQuestions(
    String cohortId,
    String assessmentId,
  ) {
    return cohortSub(cohortId, 'assessments')
        .doc(assessmentId)
        .collection('questions')
        .orderBy('order')
        .snapshots()
        .map((s) => s.docs.map(AssessmentQuestionModel.fromFirestore).toList());
  }

  Future<void> replaceAssessmentQuestions({
    required String cohortId,
    required String assessmentId,
    required List<AssessmentQuestionModel> questions,
  }) async {
    final col = cohortSub(cohortId, 'assessments')
        .doc(assessmentId)
        .collection('questions');
    final existing = await col.get();
    final batch = _firestore.batch();
    for (final doc in existing.docs) {
      batch.delete(doc.reference);
    }
    var maxScore = 0;
    for (var i = 0; i < questions.length; i++) {
      final q = questions[i].copyWith(order: i);
      final ref = q.id.isEmpty || q.id.startsWith('draft_')
          ? col.doc()
          : col.doc(q.id);
      batch.set(ref, q.copyWith(id: ref.id, order: i).toFirestore());
      maxScore += q.points;
    }
    batch.update(cohortSub(cohortId, 'assessments').doc(assessmentId), {
      'questionCount': questions.length,
      'maxScore': maxScore,
      'updatedAt': FieldValue.serverTimestamp(),
    });
    await batch.commit();
  }

  Stream<List<AssessmentSubmissionModel>> watchMyAssessmentSubmissions(
    String cohortId,
    String userId,
  ) {
    return cohortSub(cohortId, 'assessmentSubmissions')
        .where('userId', isEqualTo: userId)
        .snapshots()
        .map((s) => s.docs.map(AssessmentSubmissionModel.fromFirestore).toList());
  }

  Stream<List<AssessmentSubmissionModel>> watchAssessmentSubmissions(
    String cohortId,
    String assessmentId,
  ) {
    return cohortSub(cohortId, 'assessmentSubmissions')
        .where('assessmentId', isEqualTo: assessmentId)
        .snapshots()
        .map((s) => s.docs.map(AssessmentSubmissionModel.fromFirestore).toList());
  }

  Stream<AssessmentSubmissionModel?> watchAssessmentSubmission(
    String cohortId,
    String submissionId,
  ) {
    return cohortSub(cohortId, 'assessmentSubmissions')
        .doc(submissionId)
        .snapshots()
        .map(
          (s) => s.exists ? AssessmentSubmissionModel.fromFirestore(s) : null,
        );
  }

  // ── Curriculum Sheets (CSV) ──

  Stream<List<CurriculumSheetModel>> watchCurriculumSheets(String cohortId) {
    return cohortSub(cohortId, 'curriculumSheets')
        .orderBy('uploadedAt', descending: true)
        .snapshots()
        .map((s) => s.docs.map(CurriculumSheetModel.fromFirestore).toList());
  }

  Stream<CurriculumSheetModel?> watchLatestCurriculumSheet(String cohortId) {
    return cohortSub(cohortId, 'curriculumSheets')
        .orderBy('uploadedAt', descending: true)
        .limit(1)
        .snapshots()
        .map(
          (s) => s.docs.isEmpty
              ? null
              : CurriculumSheetModel.fromFirestore(s.docs.first),
        );
  }

  Stream<CurriculumSheetModel?> watchCurriculumSheet(
    String cohortId,
    String sheetId,
  ) {
    return cohortSub(cohortId, 'curriculumSheets')
        .doc(sheetId)
        .snapshots()
        .map((s) => s.exists ? CurriculumSheetModel.fromFirestore(s) : null);
  }

  Future<String> saveCurriculumSheet({
    required String cohortId,
    required CurriculumSheetModel sheet,
    String? replaceSheetId,
  }) async {
    final ref = replaceSheetId != null
        ? cohortSub(cohortId, 'curriculumSheets').doc(replaceSheetId)
        : cohortSub(cohortId, 'curriculumSheets').doc();
    await ref.set(sheet.toFirestore());
    return ref.id;
  }

  Future<void> deleteCurriculumSheet({
    required String cohortId,
    required String sheetId,
  }) async {
    await cohortSub(cohortId, 'curriculumSheets').doc(sheetId).delete();
  }

  // ── Form Tasks (Google Form) ──

  Stream<List<FormTaskModel>> watchFormTasks(String cohortId) {
    return cohortSub(cohortId, 'formTasks')
        .where('published', isEqualTo: true)
        .orderBy('dueAt', descending: false)
        .snapshots()
        .map((s) => s.docs.map(FormTaskModel.fromFirestore).toList());
  }

  Stream<List<FormTaskModel>> watchAllFormTasks(String cohortId) {
    return cohortSub(cohortId, 'formTasks')
        .orderBy('dueAt', descending: false)
        .snapshots()
        .map((s) => s.docs.map(FormTaskModel.fromFirestore).toList());
  }

  Stream<FormTaskModel?> watchFormTask(String cohortId, String taskId) {
    return cohortSub(cohortId, 'formTasks')
        .doc(taskId)
        .snapshots()
        .map((doc) => doc.exists ? FormTaskModel.fromFirestore(doc) : null);
  }

  Stream<List<FormResponseModel>> watchFormTaskResponses(
    String cohortId,
    String taskId,
  ) {
    return cohortSub(cohortId, 'formTasks')
        .doc(taskId)
        .collection('responses')
        .orderBy('submittedAt', descending: true)
        .snapshots()
        .map((s) => s.docs.map(FormResponseModel.fromFirestore).toList());
  }

  Stream<List<FormResponseModel>> watchMyFormResponses(
    String cohortId,
    String userId,
  ) {
    return _firestore
        .collectionGroup('responses')
        .where('cohortId', isEqualTo: cohortId)
        .where('userId', isEqualTo: userId)
        .snapshots()
        .map((s) => s.docs.map(FormResponseModel.fromFirestore).toList());
  }

  Stream<List<FormTaskWithStatus>> watchFormTasksWithStatus(
    String cohortId,
    String userId,
  ) {
    return watchFormTasks(cohortId).asyncMap((tasks) async {
      if (tasks.isEmpty) return <FormTaskWithStatus>[];
      final results = await Future.wait(
        tasks.map((task) async {
          final doc = await cohortSub(cohortId, 'formTasks')
              .doc(task.id)
              .collection('responses')
              .doc(userId)
              .get();
          return FormTaskWithStatus(
            task: task,
            myResponse: doc.exists
                ? FormResponseModel.fromFirestore(doc)
                : null,
          );
        }),
      );
      return results;
    });
  }

  Future<String> createFormTask({
    required String cohortId,
    required FormTaskModel task,
    required String authorId,
  }) async {
    final doc = await cohortSub(cohortId, 'formTasks').add(
      task.copyWith(responseCount: 0).toFirestore(
            authorId: authorId,
            isCreate: true,
          ),
    );
    return doc.id;
  }

  Future<void> updateFormTask({
    required String cohortId,
    required String taskId,
    required FormTaskModel task,
    required String authorId,
  }) async {
    await cohortSub(cohortId, 'formTasks').doc(taskId).update(
          task.toFirestore(authorId: authorId),
        );
  }

  Future<void> deleteFormTask(String cohortId, String taskId) async {
    final taskRef = cohortSub(cohortId, 'formTasks').doc(taskId);
    final responses = await taskRef.collection('responses').get();
    final refs = [...responses.docs.map((doc) => doc.reference), taskRef];
    for (var i = 0; i < refs.length; i += 400) {
      final batch = _firestore.batch();
      for (final ref in refs.skip(i).take(400)) {
        batch.delete(ref);
      }
      await batch.commit();
    }
  }

  // ── User Profile ──

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
  }) async {
    final updates = <String, dynamic>{
      'updatedAt': FieldValue.serverTimestamp(),
    };
    if (jobPreferences != null) updates['jobPreferences'] = jobPreferences.toMap();
    if (motto != null) updates['motto'] = motto;
    if (skills != null) updates['skills'] = skills;
    if (socialLinks != null) updates['socialLinks'] = socialLinks;
    if (birthDate != null) updates['birthDate'] = birthDate;
    if (photoUrl != null) updates['photoUrl'] = photoUrl;
    if (photoStoragePath != null) updates['photoStoragePath'] = photoStoragePath;
    if (personalEmail != null) {
      updates['personalEmail'] = personalEmail.trim().toLowerCase();
    }
    await _firestore.collection(FirestorePaths.users).doc(uid).update(updates);
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

    try {
      final callable = FirebaseFunctions.instanceFor(
        region: 'asia-northeast3',
      ).httpsCallable('updatePersonalEmail');
      await callable.call<Map<String, dynamic>>({
        'personalEmail': normalized,
      });
    } on FirebaseFunctionsException catch (e) {
      throw DataException(
        e.message ?? '개인 이메일 저장에 실패했습니다.',
        code: e.code,
      );
    }
  }
}
