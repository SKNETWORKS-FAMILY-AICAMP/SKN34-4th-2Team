import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../constants/ai_ops_types.dart';

/// Firestore LLMOps 로그/피드백 Callable 래퍼.
/// 원문(이력서·채팅·공고)은 보내지 않고 메타만 전달한다.
class AiOpsService {
  AiOpsService({FirebaseFunctions? functions}) : _given = functions;

  // **만들 때가 아니라 쓸 때 잡는다.** 생성자에서 잡으면 Firebase가 아직 안 뜬
  // 곳에서 이 객체를 만들기만 해도 터진다. 위젯 시험이 실제로 그렇게 터졌다 —
  // 화면이 `ref.read(aiOpsServiceProvider)`를 읽는 순간 Firebase 없음 오류가 났다.
  // 로그는 곁다리라 여기서 화면을 막으면 본말이 뒤집힌다.
  final FirebaseFunctions? _given;

  FirebaseFunctions get _functions =>
      _given ?? FirebaseFunctions.instanceFor(region: 'asia-northeast3');

  /// 성공 시 logId. 실패해도 코치 UX를 막지 않도록 null을 반환한다.
  Future<String?> recordGenerationLog({
    required String type,
    required String cohortId,
    required int latencyMs,
    required String status,
    String? promptVersion,
    String? model,
    String? errorMessage,
    String? reasoningEffort,
    int? tokenIn,
    int? tokenOut,
    int generatedCount = 1,
    Map<String, Object?> meta = const {},
  }) async {
    try {
      final result = await _functions
          .httpsCallable('recordAiGenerationLog')
          .call<Map<String, dynamic>>({
            'type': type,
            'cohortId': cohortId,
            'latencyMs': latencyMs,
            'status': status,
            'generatedCount': generatedCount,
            if (promptVersion != null && promptVersion.isNotEmpty)
              'promptVersion': promptVersion,
            if (model != null && model.isNotEmpty) 'model': model,
            if (errorMessage != null && errorMessage.isNotEmpty)
              'errorMessage': errorMessage,
            if (reasoningEffort != null && reasoningEffort.isNotEmpty)
              'reasoningEffort': reasoningEffort,
            if (tokenIn != null) 'tokenIn': tokenIn,
            if (tokenOut != null) 'tokenOut': tokenOut,
            if (meta.isNotEmpty) 'meta': meta,
          });
      final data = result.data;
      return data['logId']?.toString();
    } catch (_) {
      return null;
    }
  }

  Future<void> recordOutcome({
    required String cohortId,
    required String logId,
    required String outcome,
    String draftId = 'session',
    String? promptVersion,
    String? type,
  }) async {
    if (logId.isEmpty) return;
    try {
      await _functions.httpsCallable('recordAiOutcomeFeedback').call({
        'cohortId': cohortId,
        'logId': logId,
        'draftId': draftId,
        'outcome': outcome,
        if (promptVersion != null && promptVersion.isNotEmpty)
          'promptVersion': promptVersion,
        if (type != null && type.isNotEmpty) 'type': type,
      });
    } catch (_) {
      // outcome 실패가 본 기능을 막지 않는다.
    }
  }

  Future<String?> recordCoachLog({
    required String type,
    required String cohortId,
    required Stopwatch watch,
    required bool success,
    String? promptVersion,
    String? model,
    Object? error,
    Map<String, Object?> meta = const {},
    int generatedCount = 1,
  }) {
    return recordGenerationLog(
      type: type,
      cohortId: cohortId,
      latencyMs: watch.elapsedMilliseconds,
      status: success ? 'success' : 'error',
      promptVersion: promptVersion ?? _fallbackVersion(type),
      model: model,
      errorMessage: success ? null : error?.toString(),
      generatedCount: success ? generatedCount : 0,
      meta: meta,
    );
  }

  static String _fallbackVersion(String type) => switch (type) {
    AiOpsTypes.jobChat => AiOpsPromptVersions.jobChat,
    AiOpsTypes.jobRecommend => AiOpsPromptVersions.jobRecommend,
    AiOpsTypes.resumeReview => AiOpsPromptVersions.resumeReview,
    AiOpsTypes.studentChatbot => AiOpsPromptVersions.studentChatbot,
    _ => type,
  };
}

final aiOpsServiceProvider = Provider<AiOpsService>((ref) => AiOpsService());
