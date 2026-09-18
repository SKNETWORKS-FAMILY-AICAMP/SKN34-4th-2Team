import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/models/assessment_model.dart';

class GenerateAssessmentResult {
  const GenerateAssessmentResult({
    required this.questions,
    this.logId,
    this.promptVersion,
    this.model,
    this.rowCount = 0,
    this.targetCount,
    this.sheetId,
    this.dayFrom,
    this.dayTo,
    this.isRegen = false,
  });

  final List<AssessmentQuestionModel> questions;
  final String? logId;
  final String? promptVersion;
  final String? model;
  final int rowCount;

  /// 강사가 정한 이번 평가 목표 문항 수 (가이드용)
  final int? targetCount;
  final String? sheetId;
  final int? dayFrom;
  final int? dayTo;
  final bool isRegen;
}

/// 성취도 평가 Callable Functions
class AssessmentFunctionsService {
  AssessmentFunctionsService({FirebaseFunctions? functions})
      : _functions = functions ??
            FirebaseFunctions.instanceFor(region: 'asia-northeast3');

  final FirebaseFunctions _functions;

  Future<Map<String, dynamic>> getAssessmentForTake({
    required String cohortId,
    required String assessmentId,
  }) async {
    final result = await _functions.httpsCallable('getAssessmentForTake').call({
      'cohortId': cohortId,
      'assessmentId': assessmentId,
    });
    final raw = result.data;
    if (raw is Map) {
      return Map<String, dynamic>.from(raw);
    }
    throw FirebaseFunctionsException(
      code: 'internal',
      message: '평가 응답 형식이 올바르지 않습니다.',
    );
  }

  Future<Map<String, dynamic>> submitAssessment({
    required String cohortId,
    required String assessmentId,
    required Map<String, dynamic> answers,
  }) async {
    final result = await _functions.httpsCallable('submitAssessment').call({
      'cohortId': cohortId,
      'assessmentId': assessmentId,
      'answers': answers,
    });
    return Map<String, dynamic>.from(result.data as Map);
  }

  /// 제출 후 리뷰용 — 정답 포함 문항 + 제출 답안
  Future<Map<String, dynamic>> getAssessmentReview({
    required String cohortId,
    required String assessmentId,
    String? submissionId,
  }) async {
    final result = await _functions.httpsCallable('getAssessmentReview').call({
      'cohortId': cohortId,
      'assessmentId': assessmentId,
      if (submissionId != null) 'submissionId': submissionId,
    });
    return Map<String, dynamic>.from(result.data as Map);
  }

  Future<Map<String, dynamic>> adjustAssessmentScores({
    required String cohortId,
    required String submissionId,
    required List<Map<String, dynamic>> adjustments,
    String? note,
  }) async {
    final result =
        await _functions.httpsCallable('adjustAssessmentScores').call({
      'cohortId': cohortId,
      'submissionId': submissionId,
      'adjustments': adjustments,
      if (note != null && note.isNotEmpty) 'note': note,
    });
    return Map<String, dynamic>.from(result.data as Map);
  }

  Future<GenerateAssessmentResult> generateAssessmentQuestions({
    required String cohortId,
    required String sheetId,
    required int dayFrom,
    required int dayTo,
    int mcCount = 20,
    int saCount = 5,
    String? subjectFilter,
    String? parentLogId,
    List<Map<String, dynamic>>? replaceOf,
  }) async {
    final result = await _functions
        .httpsCallable(
          'generateAssessmentQuestions',
          options: HttpsCallableOptions(timeout: const Duration(seconds: 300)),
        )
        .call({
      'cohortId': cohortId,
      'sheetId': sheetId,
      'dayFrom': dayFrom,
      'dayTo': dayTo,
      'mcCount': mcCount,
      'saCount': saCount,
      if (subjectFilter != null && subjectFilter.isNotEmpty)
        'subjectFilter': subjectFilter,
      if (parentLogId != null) 'parentLogId': parentLogId,
      if (replaceOf != null && replaceOf.isNotEmpty) 'replaceOf': replaceOf,
    });
    final data = Map<String, dynamic>.from(result.data as Map);
    final raw = data['questions'] as List? ?? [];
    final questions = raw.asMap().entries.map((e) {
      final m = Map<String, dynamic>.from(e.value as Map);
      return AssessmentQuestionModel.fromMap(
        m['id'] as String? ?? 'draft_${e.key}',
        m,
      );
    }).toList();
    return GenerateAssessmentResult(
      questions: questions,
      logId: data['logId']?.toString(),
      promptVersion: data['promptVersion']?.toString(),
      model: data['model']?.toString(),
      rowCount: (data['rowCount'] as num?)?.toInt() ?? 0,
      sheetId: sheetId,
      dayFrom: dayFrom,
      dayTo: dayTo,
      isRegen: data['isRegen'] == true,
    );
  }

  Future<void> recordAiQuestionFeedback({
    required String cohortId,
    required String logId,
    String? promptVersion,
    String? assessmentId,
    required List<Map<String, dynamic>> items,
  }) async {
    await _functions.httpsCallable('recordAiQuestionFeedback').call({
      'cohortId': cohortId,
      'logId': logId,
      if (promptVersion != null) 'promptVersion': promptVersion,
      if (assessmentId != null) 'assessmentId': assessmentId,
      'items': items,
    });
  }
}

final assessmentFunctionsServiceProvider =
    Provider<AssessmentFunctionsService>((ref) {
  return AssessmentFunctionsService();
});
