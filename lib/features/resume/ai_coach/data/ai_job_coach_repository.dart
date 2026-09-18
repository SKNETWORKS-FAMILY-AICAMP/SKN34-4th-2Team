import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../shared/demo/demo_accounts.dart';
import '../../../../shared/models/job_preferences.dart';
import '../../../../shared/models/resume_content.dart';
import '../models/ai_job_coach_result.dart';
import '../models/resume_readiness.dart';
import 'demo_ai_coach_clients.dart';
import 'job_recommend_api_client.dart';

/// 맞춤 공고 추천.
///
/// 추천 서버(`job_matching_bot` API)에 이력서 평문과 희망 조건을 보내면 벡터 검색 →
/// 하드 필터 → LLM 재정렬 → 근거 검증을 거친 공고를 근거 인용과 함께 돌려준다.
/// 서버가 없으면 추천하지 않는다. 앱 안에서 태그만 보고 추측하던 규칙 기반 추천은
/// 근거가 약해 없앴다. 실패 이유는 예외 메시지로 화면에 그대로 보인다.
class AiJobCoachRepository {
  AiJobCoachRepository({required this._apiClient});

  final JobRecommendApiClient? _apiClient;

  /// [focus]를 주면 서버가 읽을 글만 그것으로 바꾼다. 필수 항목 검증과 조건(학력·연차·
  /// 전공·자격증)은 [draftContent] 그대로 본다.
  ///
  /// "프로젝트 경험만 보고 추천해줘"를 위한 것이다. 좁힌 것을 검증에까지 쓰면 원래
  /// 이력서가 멀쩡한데도 "핵심역량·기술스택·자기소개서를 작성해 주세요"로 막힌다.
  ///
  /// [onProgress]를 주면 서버가 단계를 넘길 때마다 부른다. [detail]이 null이면 그 단계를
  /// 시작한 것이고, 문자열이면 그 단계를 끝내며 남긴 결과 한 줄이다.
  Future<AiJobCoachResult> analyzeAndMatch({
    required ResumeContent draftContent,
    JobPreferences preferences = const JobPreferences(),
    ResumeContent? focus,
    void Function(String stage, String? detail)? onProgress,
  }) async {
    // 필수 항목이 비면 서버에 보내기 전에 막는다. 이유는 화면이 그대로 보여 준다.
    final readiness = ResumeReadiness.of(draftContent);
    if (!readiness.canRecommendJobs) {
      throw StateError(
        readiness.blockedReason(AiCoachFeature.jobRecommendation)!,
      );
    }

    final api = _apiClient;
    if (api == null) {
      throw const JobRecommendApiException(
        '추천 서버 주소가 비어 있습니다. --dart-define=JOB_RECOMMEND_API_URL=... 로 지정하세요.',
      );
    }

    final outgoing = JobRecommendRequest.fromResume(
      draftContent,
      preferences: preferences,
      focus: focus,
    );
    final response = onProgress == null
        ? await api.recommend(outgoing)
        : await api.recommendWithProgress(outgoing, onProgress: onProgress);
    return AiJobCoachResult(
      testMode: false,
      notice: response.reranked
          ? response.notice
          : '${response.notice} · LLM 재정렬 없이 검색 순서대로 표시했습니다.',
      recommendations: response.recommendations,
      selectedJob: null,
      skillJudgements: const [],
      resumeFeedback: const [],
      learningRecommendations: const [],
      analysisId: '',
      fromServer: true,
      searchQuery: response.searchQuery,
      profileSummary: response.profileSummary,
      warnings: response.warnings,
      promptVersion: response.promptVersion,
      model: response.model,
      reasoningEffort: response.reasoningEffort,
      reranked: response.reranked,
    );
  }
}

/// 추천 서버 클라이언트. 주소가 비어 있으면 null이고 추천 버튼은 안내 오류를 낸다.
final jobRecommendApiClientProvider = Provider<JobRecommendApiClient?>((ref) {
  // 데모 모드에는 추천 서버가 없다. 온보딩 캡처용 예시 결과를 돌려준다.
  if (DemoConfig.enabled) return DemoJobRecommendApiClient();
  return JobRecommendApiConfig.isConfigured ? JobRecommendApiClient() : null;
});

final aiJobCoachRepositoryProvider = Provider<AiJobCoachRepository>((ref) {
  return AiJobCoachRepository(apiClient: ref.watch(jobRecommendApiClientProvider));
});
