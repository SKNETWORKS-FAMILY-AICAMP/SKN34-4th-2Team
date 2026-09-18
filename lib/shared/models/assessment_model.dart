import 'package:cloud_firestore/cloud_firestore.dart';

import '../../core/utils/date_utils.dart';

/// 문항 유형
enum AssessmentQuestionType {
  multipleChoice('mc'),
  shortAnswer('sa');

  const AssessmentQuestionType(this.value);
  final String value;

  static AssessmentQuestionType fromString(String? value) {
    return AssessmentQuestionType.values.firstWhere(
      (e) => e.value == value,
      orElse: () => AssessmentQuestionType.multipleChoice,
    );
  }
}

/// 커리큘럼 CSV 출처 (AI 출제 구간)
class AssessmentCurriculumSource {
  const AssessmentCurriculumSource({
    this.sheetId,
    this.dayFrom,
    this.dayTo,
    this.subjectFilter,
  });

  final String? sheetId;
  final int? dayFrom;
  final int? dayTo;
  final String? subjectFilter;

  factory AssessmentCurriculumSource.fromMap(Map<String, dynamic>? data) {
    if (data == null) return const AssessmentCurriculumSource();
    return AssessmentCurriculumSource(
      sheetId: data['sheetId'] as String? ?? data['moduleId'] as String?,
      dayFrom: (data['dayFrom'] as num?)?.toInt() ??
          (data['snFrom'] as num?)?.toInt(),
      dayTo:
          (data['dayTo'] as num?)?.toInt() ?? (data['snTo'] as num?)?.toInt(),
      subjectFilter:
          data['subjectFilter'] as String? ?? data['moduleName'] as String?,
    );
  }

  Map<String, dynamic> toMap() => {
        if (sheetId != null) 'sheetId': sheetId,
        if (dayFrom != null) 'dayFrom': dayFrom,
        if (dayTo != null) 'dayTo': dayTo,
        if (subjectFilter != null) 'subjectFilter': subjectFilter,
      };
}

/// @Deprecated — AssessmentCurriculumSource 사용
typedef AssessmentNotionSource = AssessmentCurriculumSource;

/// 성취도 평가 메타 (정답 없음 — 학생도 published 읽기 가능)
class AssessmentModel {
  const AssessmentModel({
    required this.id,
    required this.title,
    required this.tags,
    required this.questionCount,
    required this.maxScore,
    required this.startAt,
    required this.endAt,
    this.thumbnailUrl,
    this.thumbnailPath,
    this.published = false,
    this.createdBy,
    this.createdAt,
    this.updatedAt,
    this.curriculumSource,
  });

  final String id;
  final String title;
  final List<String> tags;
  final int questionCount;
  final int maxScore;
  final DateTime startAt;
  final DateTime endAt;
  final String? thumbnailUrl;
  final String? thumbnailPath;
  final bool published;
  final String? createdBy;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final AssessmentCurriculumSource? curriculumSource;

  bool get isEnded => DateTime.now().isAfter(endAt);
  bool get isUpcoming => DateTime.now().isBefore(startAt);
  bool get isActive => !isUpcoming && !isEnded;

  String get periodLabel =>
      '${AppDateUtils.formatDisplay(startAt)} ~ ${AppDateUtils.formatDisplay(endAt)}';

  String get statusLabel {
    if (!published) return '임시저장';
    if (isEnded) return '종료';
    if (isUpcoming) return '예정';
    return '진행중';
  }

  factory AssessmentModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data()!;
    return AssessmentModel.fromMap(doc.id, data);
  }

  factory AssessmentModel.fromMap(String id, Map<String, dynamic> data) {
    return AssessmentModel(
      id: id,
      title: data['title'] as String? ?? '',
      tags: List<String>.from(data['tags'] as List? ?? []),
      questionCount: (data['questionCount'] as num?)?.toInt() ?? 0,
      maxScore: (data['maxScore'] as num?)?.toInt() ?? 100,
      startAt:
          AppDateUtils.timestampToDateTime(data['startAt']) ?? DateTime.now(),
      endAt: AppDateUtils.timestampToDateTime(data['endAt']) ?? DateTime.now(),
      thumbnailUrl: data['thumbnailUrl'] as String?,
      thumbnailPath: data['thumbnailPath'] as String?,
      published: data['published'] as bool? ?? false,
      createdBy: data['createdBy'] as String?,
      createdAt: AppDateUtils.timestampToDateTime(data['createdAt']),
      updatedAt: AppDateUtils.timestampToDateTime(data['updatedAt']),
      curriculumSource: data['curriculumSource'] is Map
          ? AssessmentCurriculumSource.fromMap(
              Map<String, dynamic>.from(data['curriculumSource'] as Map),
            )
          : data['notionSource'] is Map
              ? AssessmentCurriculumSource.fromMap(
                  Map<String, dynamic>.from(data['notionSource'] as Map),
                )
              : null,
    );
  }

  Map<String, dynamic> toFirestore({bool? published}) => {
        'title': title,
        'tags': tags,
        'questionCount': questionCount,
        'maxScore': maxScore,
        'startAt': Timestamp.fromDate(startAt),
        'endAt': Timestamp.fromDate(endAt),
        if (thumbnailUrl != null) 'thumbnailUrl': thumbnailUrl,
        if (thumbnailPath != null) 'thumbnailPath': thumbnailPath,
        'published': published ?? this.published,
        if (createdBy != null) 'createdBy': createdBy,
        if (curriculumSource != null)
          'curriculumSource': curriculumSource!.toMap(),
        'createdAt': FieldValue.serverTimestamp(),
        'updatedAt': FieldValue.serverTimestamp(),
      };

  AssessmentModel copyWith({
    String? id,
    String? title,
    List<String>? tags,
    int? questionCount,
    int? maxScore,
    DateTime? startAt,
    DateTime? endAt,
    String? thumbnailUrl,
    String? thumbnailPath,
    bool? published,
    String? createdBy,
    DateTime? createdAt,
    DateTime? updatedAt,
    AssessmentCurriculumSource? curriculumSource,
  }) {
    return AssessmentModel(
      id: id ?? this.id,
      title: title ?? this.title,
      tags: tags ?? this.tags,
      questionCount: questionCount ?? this.questionCount,
      maxScore: maxScore ?? this.maxScore,
      startAt: startAt ?? this.startAt,
      endAt: endAt ?? this.endAt,
      thumbnailUrl: thumbnailUrl ?? this.thumbnailUrl,
      thumbnailPath: thumbnailPath ?? this.thumbnailPath,
      published: published ?? this.published,
      createdBy: createdBy ?? this.createdBy,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
      curriculumSource: curriculumSource ?? this.curriculumSource,
    );
  }
}

/// 문항 (정답 포함 — 강사/관리자·Functions만)
class AssessmentQuestionModel {
  const AssessmentQuestionModel({
    required this.id,
    required this.order,
    required this.type,
    required this.prompt,
    required this.points,
    this.choices = const [],
    this.correctIndex,
    this.acceptedAnswers = const [],
    this.explanation,
    this.origin = 'manual',
    this.aiLogId,
    this.promptVersion,
    this.sourceDay,
    this.sourceTopic,
    this.aiDraftId,
  });

  final String id;
  final int order;
  final AssessmentQuestionType type;
  final String prompt;
  final int points;
  final List<String> choices;
  final int? correctIndex;
  final List<String> acceptedAnswers;
  final String? explanation;

  /// `ai` | `manual` — 오답→추천 확장 시 sourceTopic 조인 키
  final String origin;
  final String? aiLogId;
  final String? promptVersion;
  final int? sourceDay;
  final String? sourceTopic;
  final String? aiDraftId;

  factory AssessmentQuestionModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data()!;
    return AssessmentQuestionModel.fromMap(doc.id, data);
  }

  factory AssessmentQuestionModel.fromMap(String id, Map<String, dynamic> data) {
    int? toInt(dynamic v) {
      if (v == null) return null;
      if (v is int) return v;
      if (v is num) return v.toInt();
      return int.tryParse('$v');
    }

    return AssessmentQuestionModel(
      id: id,
      order: toInt(data['order']) ?? 0,
      type: AssessmentQuestionType.fromString(data['type']?.toString()),
      prompt: data['prompt']?.toString() ?? '',
      points: toInt(data['points']) ?? 1,
      choices: List<String>.from(
        (data['choices'] as List? ?? []).map((e) => '$e'),
      ),
      correctIndex: toInt(data['correctIndex']),
      acceptedAnswers: List<String>.from(
        (data['acceptedAnswers'] as List? ?? []).map((e) => '$e'),
      ),
      explanation: data['explanation']?.toString(),
      origin: data['origin']?.toString() == 'ai' ? 'ai' : 'manual',
      aiLogId: data['aiLogId']?.toString(),
      promptVersion: data['promptVersion']?.toString(),
      sourceDay: toInt(data['sourceDay']),
      sourceTopic: data['sourceTopic']?.toString(),
      aiDraftId: data['aiDraftId']?.toString(),
    );
  }

  Map<String, dynamic> toFirestore() => {
        'order': order,
        'type': type.value,
        'prompt': prompt,
        'points': points,
        'choices': choices,
        if (correctIndex != null) 'correctIndex': correctIndex,
        'acceptedAnswers': acceptedAnswers,
        if (explanation != null) 'explanation': explanation,
        'origin': origin,
        if (aiLogId != null) 'aiLogId': aiLogId,
        if (promptVersion != null) 'promptVersion': promptVersion,
        if (sourceDay != null) 'sourceDay': sourceDay,
        if (sourceTopic != null) 'sourceTopic': sourceTopic,
        if (aiDraftId != null) 'aiDraftId': aiDraftId,
      };

  /// 학생 응시용 — 정답 제거
  Map<String, dynamic> toStudentPayload() => {
        'id': id,
        'order': order,
        'type': type.value,
        'prompt': prompt,
        'points': points,
        if (type == AssessmentQuestionType.multipleChoice) 'choices': choices,
      };

  AssessmentQuestionModel copyWith({
    String? id,
    int? order,
    AssessmentQuestionType? type,
    String? prompt,
    int? points,
    List<String>? choices,
    int? correctIndex,
    List<String>? acceptedAnswers,
    String? explanation,
    String? origin,
    String? aiLogId,
    String? promptVersion,
    int? sourceDay,
    String? sourceTopic,
    String? aiDraftId,
  }) {
    return AssessmentQuestionModel(
      id: id ?? this.id,
      order: order ?? this.order,
      type: type ?? this.type,
      prompt: prompt ?? this.prompt,
      points: points ?? this.points,
      choices: choices ?? this.choices,
      correctIndex: correctIndex ?? this.correctIndex,
      acceptedAnswers: acceptedAnswers ?? this.acceptedAnswers,
      explanation: explanation ?? this.explanation,
      origin: origin ?? this.origin,
      aiLogId: aiLogId ?? this.aiLogId,
      promptVersion: promptVersion ?? this.promptVersion,
      sourceDay: sourceDay ?? this.sourceDay,
      sourceTopic: sourceTopic ?? this.sourceTopic,
      aiDraftId: aiDraftId ?? this.aiDraftId,
    );
  }
}

/// 문항별 답안/채점
class AssessmentAnswerEntry {
  const AssessmentAnswerEntry({
    required this.value,
    required this.autoScore,
    required this.finalScore,
    required this.isCorrect,
  });

  final dynamic value;
  final int autoScore;
  final int finalScore;
  final bool isCorrect;

  factory AssessmentAnswerEntry.fromMap(Map<String, dynamic> data) {
    int toInt(dynamic v) {
      if (v is int) return v;
      if (v is num) return v.toInt();
      return int.tryParse('$v') ?? 0;
    }

    return AssessmentAnswerEntry(
      value: data['value'],
      autoScore: toInt(data['autoScore']),
      finalScore: toInt(data['finalScore']),
      isCorrect: data['isCorrect'] == true,
    );
  }

  Map<String, dynamic> toMap() => {
        'value': value,
        'autoScore': autoScore,
        'finalScore': finalScore,
        'isCorrect': isCorrect,
      };
}

/// 점수 수정 이력
class AssessmentScoreAdjustment {
  const AssessmentScoreAdjustment({
    required this.questionId,
    required this.previous,
    required this.next,
    required this.by,
    this.byName,
    this.at,
    this.note,
  });

  final String questionId;
  final int previous;
  final int next;
  final String by;
  final String? byName;
  final DateTime? at;
  final String? note;

  factory AssessmentScoreAdjustment.fromMap(Map<String, dynamic> data) {
    return AssessmentScoreAdjustment(
      questionId: data['questionId'] as String? ?? '',
      previous: (data['previous'] as num?)?.toInt() ?? 0,
      next: (data['next'] as num?)?.toInt() ?? 0,
      by: data['by'] as String? ?? '',
      byName: data['byName'] as String?,
      at: AppDateUtils.timestampToDateTime(data['at']),
      note: data['note'] as String?,
    );
  }

  Map<String, dynamic> toMap() => {
        'questionId': questionId,
        'previous': previous,
        'next': next,
        'by': by,
        if (byName != null) 'byName': byName,
        'at': at != null ? Timestamp.fromDate(at!) : FieldValue.serverTimestamp(),
        if (note != null) 'note': note,
      };
}

/// 응시 결과
class AssessmentSubmissionModel {
  const AssessmentSubmissionModel({
    required this.id,
    required this.assessmentId,
    required this.userId,
    required this.userDisplayName,
    required this.answers,
    required this.autoTotalScore,
    required this.totalScore,
    this.status = 'submitted',
    this.submittedAt,
    this.scoreAdjustments = const [],
  });

  final String id;
  final String assessmentId;
  final String userId;
  final String userDisplayName;
  final Map<String, AssessmentAnswerEntry> answers;
  final int autoTotalScore;
  final int totalScore;
  final String status;
  final DateTime? submittedAt;
  final List<AssessmentScoreAdjustment> scoreAdjustments;

  bool get completed => status == 'submitted';

  factory AssessmentSubmissionModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data()!;
    return AssessmentSubmissionModel.fromMap(doc.id, data);
  }

  factory AssessmentSubmissionModel.fromMap(
    String id,
    Map<String, dynamic> data,
  ) {
    final rawAnswers = data['answers'];
    final answers = <String, AssessmentAnswerEntry>{};
    if (rawAnswers is Map) {
      for (final e in rawAnswers.entries) {
        if (e.value is Map) {
          answers[e.key as String] = AssessmentAnswerEntry.fromMap(
            Map<String, dynamic>.from(e.value as Map),
          );
        }
      }
    }

    final adjustments = <AssessmentScoreAdjustment>[];
    final rawAdj = data['scoreAdjustments'];
    if (rawAdj is List) {
      for (final item in rawAdj) {
        if (item is Map) {
          adjustments.add(
            AssessmentScoreAdjustment.fromMap(
              Map<String, dynamic>.from(item),
            ),
          );
        }
      }
    }

    return AssessmentSubmissionModel(
      id: id,
      assessmentId: data['assessmentId'] as String? ?? '',
      userId: data['userId'] as String? ?? '',
      userDisplayName: data['userDisplayName'] as String? ?? '',
      answers: answers,
      autoTotalScore: (data['autoTotalScore'] as num?)?.toInt() ?? 0,
      totalScore: (data['totalScore'] as num?)?.toInt() ?? 0,
      status: data['status'] as String? ?? 'submitted',
      submittedAt: AppDateUtils.timestampToDateTime(data['submittedAt']),
      scoreAdjustments: adjustments,
    );
  }

  Map<String, dynamic> toFirestore() => {
        'assessmentId': assessmentId,
        'userId': userId,
        'userDisplayName': userDisplayName,
        'answers': answers.map((k, v) => MapEntry(k, v.toMap())),
        'autoTotalScore': autoTotalScore,
        'totalScore': totalScore,
        'status': status,
        'submittedAt': FieldValue.serverTimestamp(),
        'scoreAdjustments': scoreAdjustments.map((e) => e.toMap()).toList(),
      };
}
