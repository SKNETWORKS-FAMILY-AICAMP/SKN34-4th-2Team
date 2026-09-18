import '../../../../core/constants/app_constants.dart';
import '../../../../shared/models/resume_content.dart';

/// AI 코치 기능별로 이력서에 요구하는 조건이 다르다.
///
/// - 맞춤 공고 추천: 조건 판정에 쓰는 항목이 있고, 직무 근거가 **하나라도** 있으면
///   실행한다. 근거 없는 순위를 내지 않으려는 것이지, 칸을 다 채우게 하려는 것이 아니다.
/// - 이력서 첨삭: 첨삭할 내용이 하나라도 있으면 실행한다.
/// - 코치에게 묻기(채용공고 대화): 이력서와 무관하게 언제나 실행한다.
enum AiCoachFeature { resumeAnalysis, jobRecommendation, jobSearch }

/// 맞춤 공고 추천 전에 반드시 채워야 하는 섹션.
///
/// **조건 판정에 쓰이는 것만** 둔다. 학력은 하드 필터가 공고의 학력 조건과 대조하고,
/// 기본정보는 이력서가 비어 있는지 가리는 값이다.
///
/// 경력사항·자격사항·수상내역·교육경험·기타활동은 제외했다. 이 서비스의 주
/// 사용자인 부트캠프 수료 예정자는 경력이나 수상 이력이 없는 경우가 많아,
/// 이를 필수로 두면 아무도 추천을 받을 수 없다.
const requiredSectionsForRecommendation = <String>[
  'basicInfo', // 기본정보
  'education', // 학력 — Hard Filter의 학력 조건에 사용
];

/// 직무 근거. 이 중 **하나 이상** 있으면 추천할 수 있다.
///
/// 예전에는 핵심역량·기술스택·프로젝트·자기소개서를 모두 요구했다. 그런데 직무
/// 근거는 이 중 어디에나 있다 — 자기소개서 여섯 항목에도, 프로젝트 설명에도,
/// 기술 태그에도 있다. 한 칸이 비었다고 막는 것은 값에 비해 불편하다.
///
/// 게다가 챗봇에서 "내 프로젝트 경험만 보고 추천해줘"처럼 범위를 좁혀 물을 수 있게
/// 되면서, 한 종류만 있어도 뜻있는 추천이 된다.
const evidenceSectionsForRecommendation = <String>[
  'coreCompetencies', // 핵심역량/강점
  'techStack', // 기술스택
  'projects', // 프로젝트 경험
  'selfIntroduction', // 자기소개서
  'experience', // 경력사항
];

/// 이력서 첨삭에 최소한 필요한 섹션. 이 중 하나라도 있으면 첨삭할 수 있다.
const analyzableSections = <String>[
  'coreCompetencies',
  'experience',
  'techStack',
  'projects',
];

/// 이력서가 각 기능을 실행할 준비가 되었는지 판정한 결과.
class ResumeReadiness {
  const ResumeReadiness({
    required this.filledSections,
    required this.missingRequiredSections,
  });

  /// 실제로 내용이 채워진 섹션 키.
  final Set<String> filledSections;

  /// 맞춤 공고 추천에 필요하지만 아직 비어 있는 섹션 키.
  final List<String> missingRequiredSections;

  factory ResumeReadiness.of(ResumeContent content) {
    final sections = content.computeSections();
    final filled = sections.entries
        .where((entry) => entry.value)
        .map((entry) => entry.key)
        .toSet();
    return ResumeReadiness(
      filledSections: filled,
      missingRequiredSections: requiredSectionsForRecommendation
          .where((key) => !filled.contains(key))
          .toList(),
    );
  }

  /// 조건 판정에 쓰는 항목이 있고, 직무 근거가 하나라도 있는 상태.
  bool get canRecommendJobs =>
      missingRequiredSections.isEmpty && hasJobEvidence;

  /// 무엇을 근거로 공고를 고를 수 있는가. 하나라도 있으면 된다.
  bool get hasJobEvidence =>
      evidenceSectionsForRecommendation.any(filledSections.contains);

  /// 추천은 되지만 근거가 얇을 때 건네는 말. 튼튼하면 null.
  ///
  /// 자기소개서는 여섯 항목 중 하나만 채워도 "있음"이 된다. 성장과정에 한 줄만 써도
  /// 버튼이 열린다는 뜻이다. 막지는 않는다 — 핵심역량을 필수에서 뺀 것과 같은
  /// 이유다. 대신 왜 결과가 약한지 알려 준다.
  ///
  /// 기술스택이나 프로젝트는 공고의 요구 기술과 바로 대조되는 자리라, 하나라도 있으면
  /// 근거가 튼튼하다고 본다.
  String? get weakEvidenceHint {
    if (!hasJobEvidence) return null; // 그때는 blockedReason 이 말한다
    const strong = ['techStack', 'projects', 'experience'];
    if (strong.any(filledSections.contains)) return null;
    return '기술스택이나 프로젝트 경험을 적으면 공고와 맞춰 볼 근거가 늘어 '
        '추천이 훨씬 정확해집니다.';
  }

  /// 분석할 내용이 하나라도 있는 상태.
  bool get canAnalyzeResume =>
      analyzableSections.any(filledSections.contains);

  /// 코치에게 묻기(채용공고 대화)는 이력서 상태와 무관하다.
  bool get canSearchJobs => true;

  bool canRun(AiCoachFeature feature) {
    switch (feature) {
      case AiCoachFeature.jobRecommendation:
        return canRecommendJobs;
      case AiCoachFeature.resumeAnalysis:
        return canAnalyzeResume;
      case AiCoachFeature.jobSearch:
        return canSearchJobs;
    }
  }

  /// 실행할 수 없을 때 사용자에게 보여줄 이유. 실행 가능하면 null.
  String? blockedReason(AiCoachFeature feature) {
    if (canRun(feature)) return null;
    switch (feature) {
      case AiCoachFeature.jobRecommendation:
        if (missingRequiredSections.isNotEmpty) {
          return '맞춤 공고를 추천하려면 다음 항목을 먼저 작성해주세요: '
              '${missingRequiredSectionLabels.join(', ')}';
        }
        // 필수는 다 찼는데 근거가 없는 경우. 무엇이든 하나 적으면 된다고 알린다.
        return '무엇을 근거로 공고를 고를지 알 수 없습니다. '
            '핵심역량, 기술스택, 프로젝트, 자기소개서, 경력 중 '
            '하나 이상을 작성해주세요.';
      case AiCoachFeature.resumeAnalysis:
        return '첨삭할 내용이 아직 없습니다. 핵심역량, 경력, 기술스택, '
            '프로젝트 중 하나 이상을 작성해주세요.';
      case AiCoachFeature.jobSearch:
        return null;
    }
  }

  /// 비어 있는 필수 항목의 한글 라벨.
  List<String> get missingRequiredSectionLabels => missingRequiredSections
      .map((key) => AppConstants.resumeSectionLabels[key] ?? key)
      .toList();

  /// 진행 표시에 쓰는 값. 필수 항목에 "직무 근거" 한 칸을 더해 센다.
  ///
  /// 근거는 여러 항목 중 하나면 되므로 개수로 세면 뜻이 흐려진다. 있으면 한 칸을
  /// 채운 것으로 본다.
  int get completedRequiredCount =>
      (requiredSectionsForRecommendation.length - missingRequiredSections.length) +
      (hasJobEvidence ? 1 : 0);

  int get totalRequiredCount => requiredSectionsForRecommendation.length + 1;
}
