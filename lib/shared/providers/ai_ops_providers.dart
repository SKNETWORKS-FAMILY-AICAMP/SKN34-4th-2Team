import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../constants/ai_ops_types.dart';
import '../demo/demo_accounts.dart';
import '../demo/demo_ai_ops.dart';
import '../models/ai_ops_models.dart';
import '../providers/cohort_providers.dart';
import '../providers/lms_providers.dart';

/// Admin LLMOps type 필터. null = 전체
final aiQualityTypeFilterProvider =
    NotifierProvider.autoDispose<_AiQualityTypeFilter, String?>(
      _AiQualityTypeFilter.new,
    );

class _AiQualityTypeFilter extends Notifier<String?> {
  @override
  String? build() => null;

  void select(String? type) => state = type;
}

class AiQualityStats {
  const AiQualityStats({
    required this.totalRuns,
    required this.successRuns,
    required this.totalGenerated,
    required this.adopted,
    required this.edited,
    required this.discarded,
    required this.usefulOutcomes,
    required this.totalOutcomes,
    required this.avgLatencyMs,
    required this.p95LatencyMs,
    required this.tokenIn,
    required this.tokenOut,
    required this.byPromptVersion,
  });

  final int totalRuns;
  final int successRuns;
  final int totalGenerated;
  final int adopted;
  final int edited;
  final int discarded;
  final int usefulOutcomes;
  final int totalOutcomes;
  final double avgLatencyMs;
  final double p95LatencyMs;
  final int tokenIn;
  final int tokenOut;
  final Map<String, ({int generated, int adopted, int edited, int useful})>
  byPromptVersion;

  double get successRate {
    if (totalRuns <= 0) return 0;
    return successRuns / totalRuns;
  }

  double get adoptionRate {
    if (totalGenerated <= 0) return 0;
    return (adopted + edited) / totalGenerated;
  }

  double get editRate {
    final denom = adopted + edited;
    if (denom <= 0) return 0;
    return edited / denom;
  }

  double get usefulnessRate {
    if (totalOutcomes <= 0) return 0;
    return usefulOutcomes / totalOutcomes;
  }
}

final aiGenerationLogsProvider =
    StreamProvider.autoDispose<List<AiGenerationLogModel>>((ref) {
      if (DemoConfig.enabled) return Stream.value(DemoAiOps.logs());
      final cohortId = ref.watch(effectiveCohortIdProvider);
      if (cohortId == null) return Stream.value(const []);
      return ref.watch(lmsRepositoryProvider).watchAiGenerationLogs(cohortId);
    });

final aiQuestionFeedbackProvider =
    StreamProvider.autoDispose<List<AiQuestionFeedbackModel>>((ref) {
      if (DemoConfig.enabled) return Stream.value(DemoAiOps.feedback());
      final cohortId = ref.watch(effectiveCohortIdProvider);
      if (cohortId == null) return Stream.value(const []);
      return Stream.value(const <AiQuestionFeedbackModel>[]);
    });

final latestAiEvalRunProvider =
    StreamProvider.autoDispose<AiEvalRunModel?>((ref) {
      if (DemoConfig.enabled) return Stream.value(DemoAiOps.evalRun());
      return Stream.value(null);
    });

List<AiGenerationLogModel> filterLogsByType(
  List<AiGenerationLogModel> logs,
  String? typeFilter,
) {
  if (typeFilter == null || typeFilter.isEmpty) return logs;
  if (typeFilter == 'assessment') {
    return logs.where((l) => AiOpsTypes.assessmentTypes.contains(l.type)).toList();
  }
  return logs.where((l) => l.type == typeFilter).toList();
}

final aiQualityStatsProvider = Provider.autoDispose<AiQualityStats>((ref) {
  final allLogs = ref.watch(aiGenerationLogsProvider).asData?.value ?? const [];
  final typeFilter = ref.watch(aiQualityTypeFilterProvider);
  final logs = filterLogsByType(allLogs, typeFilter);
  final feedback =
      ref.watch(aiQuestionFeedbackProvider).asData?.value ?? const [];
  final logIds = logs.map((l) => l.id).toSet();
  final logTypeById = {for (final l in logs) l.id: l.type};

  var totalGenerated = 0;
  var successRuns = 0;
  var tokenIn = 0;
  var tokenOut = 0;
  final latencies = <int>[];
  final byVersion =
      <String, ({int generated, int adopted, int edited, int useful})>{};

  for (final log in logs) {
    if (log.status == 'success') {
      successRuns++;
      totalGenerated += log.generatedCount;
    }
    if (log.latencyMs > 0) latencies.add(log.latencyMs);
    tokenIn += log.tokenIn ?? 0;
    tokenOut += log.tokenOut ?? 0;
    final key = log.promptVersion.isEmpty ? '(unknown)' : log.promptVersion;
    final cur =
        byVersion[key] ?? (generated: 0, adopted: 0, edited: 0, useful: 0);
    byVersion[key] = (
      generated: cur.generated + (log.status == 'success' ? log.generatedCount : 0),
      adopted: cur.adopted,
      edited: cur.edited,
      useful: cur.useful,
    );
  }

  var adopted = 0;
  var edited = 0;
  var discarded = 0;
  var usefulOutcomes = 0;
  var totalOutcomes = 0;
  for (final f in feedback) {
    if (!logIds.contains(f.logId)) continue;
    totalOutcomes++;
    final logType = logTypeById[f.logId] ?? f.type ?? '';
    if (AiOpsOutcomes.isUseful(logType, f.outcome)) usefulOutcomes++;
    switch (f.outcome) {
      case AiOpsOutcomes.adopted:
        adopted++;
        break;
      case AiOpsOutcomes.edited:
        edited++;
        break;
      case AiOpsOutcomes.discarded:
        discarded++;
        break;
    }
    final key =
        (f.promptVersion == null || f.promptVersion!.isEmpty)
            ? '(unknown)'
            : f.promptVersion!;
    final cur =
        byVersion[key] ?? (generated: 0, adopted: 0, edited: 0, useful: 0);
    byVersion[key] = (
      generated: cur.generated,
      adopted: cur.adopted + (f.outcome == AiOpsOutcomes.adopted ? 1 : 0),
      edited: cur.edited + (f.outcome == AiOpsOutcomes.edited ? 1 : 0),
      useful:
          cur.useful +
          (AiOpsOutcomes.isUseful(logType, f.outcome) ? 1 : 0),
    );
  }

  latencies.sort();
  double avg = 0;
  double p95 = 0;
  if (latencies.isNotEmpty) {
    avg = latencies.reduce((a, b) => a + b) / latencies.length;
    final idx = ((latencies.length - 1) * 0.95).round();
    p95 = latencies[idx].toDouble();
  }

  return AiQualityStats(
    totalRuns: logs.length,
    successRuns: successRuns,
    totalGenerated: totalGenerated,
    adopted: adopted,
    edited: edited,
    discarded: discarded,
    usefulOutcomes: usefulOutcomes,
    totalOutcomes: totalOutcomes,
    avgLatencyMs: avg,
    p95LatencyMs: p95,
    tokenIn: tokenIn,
    tokenOut: tokenOut,
    byPromptVersion: byVersion,
  );
});
