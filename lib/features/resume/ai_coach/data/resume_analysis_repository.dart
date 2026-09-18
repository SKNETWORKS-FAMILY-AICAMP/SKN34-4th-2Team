import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../shared/models/resume_content.dart';
import '../models/resume_readiness.dart';
import 'resume_analyzer.dart';

/// 이력서 분석. 앱 안의 규칙으로 필수 항목과 근거 유무를 점검한다.
///
/// 공고에 맞춘 첨삭은 팀원의 첨삭 모듈(S32-17)이 맡으므로 여기서는 서버를 부르지 않는다.
class ResumeAnalysisRepository {
  const ResumeAnalysisRepository();

  Future<ResumeAnalysis> analyze(ResumeContent content) async {
    final readiness = ResumeReadiness.of(content);
    if (!readiness.canAnalyzeResume) {
      throw StateError(readiness.blockedReason(AiCoachFeature.resumeAnalysis)!);
    }
    return analyzeResume(content);
  }
}

final resumeAnalysisRepositoryProvider = Provider<ResumeAnalysisRepository>(
  (ref) => const ResumeAnalysisRepository(),
);
