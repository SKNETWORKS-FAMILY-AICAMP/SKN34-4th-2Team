import 'package:cloud_firestore/cloud_firestore.dart';

import '../../core/utils/date_utils.dart';

/// 구글폼 설문·제출 과제 (cohorts/{cohortId}/formTasks)
class FormTaskModel {
  const FormTaskModel({
    required this.id,
    required this.title,
    required this.formUrl,
    this.description = '',
    this.notionGuideUrl,
    required this.dueAt,
    this.published = true,
    this.responseCount = 0,
    this.createdAt,
    this.updatedAt,
  });

  final String id;
  final String title;
  final String description;
  final String formUrl;
  final String? notionGuideUrl;
  final DateTime dueAt;
  final bool published;
  final int responseCount;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  bool get isOverdue => DateTime.now().isAfter(dueAt);

  int get daysRemaining {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final due = DateTime(dueAt.year, dueAt.month, dueAt.day);
    return due.difference(today).inDays;
  }

  factory FormTaskModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data()!;
    return FormTaskModel(
      id: doc.id,
      title: data['title'] as String? ?? '',
      description: data['description'] as String? ?? '',
      formUrl: data['formUrl'] as String? ?? '',
      notionGuideUrl: data['notionGuideUrl'] as String?,
      dueAt: AppDateUtils.timestampToDateTime(data['dueAt']) ?? DateTime.now(),
      published: data['published'] as bool? ?? true,
      responseCount: data['responseCount'] as int? ?? 0,
      createdAt: AppDateUtils.timestampToDateTime(data['createdAt']),
      updatedAt: AppDateUtils.timestampToDateTime(data['updatedAt']),
    );
  }

  Map<String, dynamic> toFirestore({
    required String authorId,
    bool isCreate = false,
  }) =>
      {
        'title': title,
        'description': description,
        'formUrl': formUrl,
        if (notionGuideUrl != null && notionGuideUrl!.isNotEmpty)
          'notionGuideUrl': notionGuideUrl,
        'dueAt': Timestamp.fromDate(dueAt),
        'published': published,
        'responseCount': responseCount,
        'authorId': authorId,
        'updatedAt': FieldValue.serverTimestamp(),
        if (isCreate) 'createdAt': FieldValue.serverTimestamp(),
      };

  FormTaskModel copyWith({
    String? title,
    String? description,
    String? formUrl,
    String? notionGuideUrl,
    DateTime? dueAt,
    bool? published,
    int? responseCount,
  }) {
    return FormTaskModel(
      id: id,
      title: title ?? this.title,
      description: description ?? this.description,
      formUrl: formUrl ?? this.formUrl,
      notionGuideUrl: notionGuideUrl ?? this.notionGuideUrl,
      dueAt: dueAt ?? this.dueAt,
      published: published ?? this.published,
      responseCount: responseCount ?? this.responseCount,
      createdAt: createdAt,
      updatedAt: updatedAt,
    );
  }
}

/// 학생별 구글폼 제출 기록
class FormResponseModel {
  const FormResponseModel({
    required this.id,
    required this.userId,
    required this.userEmail,
    required this.taskId,
    required this.cohortId,
    this.userDisplayName = '',
    this.source = 'google_form',
    this.googleResponseId,
    this.submittedAt,
  });

  final String id;
  final String userId;
  final String userEmail;
  final String userDisplayName;
  final String taskId;
  final String cohortId;
  final String source;
  final String? googleResponseId;
  final DateTime? submittedAt;

  factory FormResponseModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data()!;
    return FormResponseModel(
      id: doc.id,
      userId: data['userId'] as String? ?? doc.id,
      userEmail: data['userEmail'] as String? ?? '',
      userDisplayName: data['userDisplayName'] as String? ?? '',
      taskId: data['taskId'] as String? ?? '',
      cohortId: data['cohortId'] as String? ?? '',
      source: data['source'] as String? ?? 'google_form',
      googleResponseId: data['googleResponseId'] as String?,
      submittedAt: AppDateUtils.timestampToDateTime(data['submittedAt']),
    );
  }

  Map<String, dynamic> toFirestore() => {
        'userId': userId,
        'userEmail': userEmail,
        'userDisplayName': userDisplayName,
        'taskId': taskId,
        'cohortId': cohortId,
        'source': source,
        if (googleResponseId != null) 'googleResponseId': googleResponseId,
        'submittedAt': FieldValue.serverTimestamp(),
      };
}

/// UI용 — 과제 + 내 제출 여부
class FormTaskWithStatus {
  const FormTaskWithStatus({
    required this.task,
    this.myResponse,
  });

  final FormTaskModel task;
  final FormResponseModel? myResponse;

  bool get isCompleted => myResponse != null;
  bool get isOverdue => task.isOverdue && !isCompleted;

  String get statusLabel {
    if (isCompleted) return '제출 완료';
    if (isOverdue) return '마감';
    if (task.daysRemaining == 0) return '오늘 마감';
    return '미제출';
  }
}
