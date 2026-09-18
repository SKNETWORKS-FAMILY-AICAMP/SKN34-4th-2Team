import '../constants/ai_ops_types.dart';
import '../models/ai_ops_models.dart';
import 'demo_accounts.dart';

/// 데모 모드의 LLMOps 화면에 보여 줄 예시 로그·피드백·평가 실행.
///
/// 실제 Firestore(`aiGenerationLogs` 등)를 읽지 않는 데모에서도 지표와 로그 카드가
/// 어떻게 보이는지 안내할 수 있게 한다. 숫자는 모두 예시다.
abstract final class DemoAiOps {
  static DateTime _ago(Duration d) => DateTime.now().subtract(d);

  static List<AiGenerationLogModel> logs() {
    const cohortId = DemoConfig.cohortId;
    return [
      AiGenerationLogModel(
        id: 'demo-log-1',
        type: AiOpsTypes.studentChatbot,
        promptVersion: AiOpsPromptVersions.studentChatbot,
        model: 'gpt-5.6-sol',
        cohortId: cohortId,
        latencyMs: 2140,
        tokenIn: 1820,
        tokenOut: 310,
        route: 'policy',
        namespaces: 'lms-policy',
        retrievalMs: 380,
        llmMs: 1690,
        createdAt: _ago(const Duration(minutes: 12)),
      ),
      AiGenerationLogModel(
        id: 'demo-log-2',
        type: AiOpsTypes.resumeReview,
        promptVersion: AiOpsPromptVersions.resumeReview,
        model: 'gpt-5.6-luna',
        cohortId: cohortId,
        latencyMs: 6480,
        tokenIn: 5240,
        tokenOut: 1120,
        reviewMode: 'job_tailored',
        appliedCount: 3,
        createdAt: _ago(const Duration(minutes: 40)),
      ),
      AiGenerationLogModel(
        id: 'demo-log-3',
        type: AiOpsTypes.jobRecommend,
        promptVersion: AiOpsPromptVersions.jobRecommend,
        model: 'gpt-5.6-luna',
        cohortId: cohortId,
        latencyMs: 3920,
        tokenIn: 2960,
        tokenOut: 640,
        topK: 5,
        jobCount: 5,
        createdAt: _ago(const Duration(hours: 2)),
      ),
      AiGenerationLogModel(
        id: 'demo-log-4',
        type: AiOpsTypes.assessmentQuestions,
        promptVersion: 'assess_q_v2',
        model: 'gpt-4o-mini',
        cohortId: cohortId,
        dayFrom: 1,
        dayTo: 8,
        mcCount: 10,
        saCount: 5,
        generatedCount: 15,
        latencyMs: 8750,
        tokenIn: 4100,
        tokenOut: 2380,
        createdAt: _ago(const Duration(hours: 5)),
      ),
      AiGenerationLogModel(
        id: 'demo-log-5',
        type: AiOpsTypes.studentChatbot,
        promptVersion: AiOpsPromptVersions.studentChatbot,
        model: 'gpt-5.6-sol',
        cohortId: cohortId,
        latencyMs: 12040,
        status: 'error',
        errorMessage: '예시: 검색 서버 응답 시간 초과',
        route: 'project',
        createdAt: _ago(const Duration(days: 1)),
      ),
    ];
  }

  static List<AiQuestionFeedbackModel> feedback() {
    const cohortId = DemoConfig.cohortId;
    AiQuestionFeedbackModel fb(String id, String logId, String outcome, String type, String version) =>
        AiQuestionFeedbackModel(
          id: id,
          logId: logId,
          draftId: '',
          cohortId: cohortId,
          outcome: outcome,
          promptVersion: version,
          type: type,
        );
    return [
      fb('demo-fb-1', 'demo-log-1', AiOpsOutcomes.helpful, AiOpsTypes.studentChatbot, AiOpsPromptVersions.studentChatbot),
      fb('demo-fb-2', 'demo-log-2', AiOpsOutcomes.applied, AiOpsTypes.resumeReview, AiOpsPromptVersions.resumeReview),
      fb('demo-fb-3', 'demo-log-3', AiOpsOutcomes.selectedForReview, AiOpsTypes.jobRecommend, AiOpsPromptVersions.jobRecommend),
      for (var i = 0; i < 9; i++)
        fb('demo-fb-a$i', 'demo-log-4', AiOpsOutcomes.adopted, AiOpsTypes.assessmentQuestions, 'assess_q_v2'),
      for (var i = 0; i < 4; i++)
        fb('demo-fb-e$i', 'demo-log-4', AiOpsOutcomes.edited, AiOpsTypes.assessmentQuestions, 'assess_q_v2'),
      for (var i = 0; i < 2; i++)
        fb('demo-fb-d$i', 'demo-log-4', AiOpsOutcomes.discarded, AiOpsTypes.assessmentQuestions, 'assess_q_v2'),
    ];
  }

  static AiEvalRunModel evalRun() => AiEvalRunModel(
    id: 'demo-eval-1',
    promptVersion: AiOpsPromptVersions.studentChatbot,
    model: 'gpt-5.6-sol',
    totalCases: 40,
    passed: 36,
    accuracy: 0.9,
    avgLatencyMs: 2310,
    createdAt: _ago(const Duration(days: 2)),
  );
}
