import '../../../../core/constants/app_constants.dart';
import '../../../../shared/models/resume_content.dart';
import '../models/resume_readiness.dart';

/// 분석 소견 한 줄. [quote]가 있으면 이력서 원문에서 그대로 가져온 근거다.
class ResumeAnalysisItem {
  const ResumeAnalysisItem(this.text, {this.quote});

  final String text;
  final String? quote;
}

/// 이력서 자체를 규칙으로 점검한 결과. AI가 문장을 고쳐 주지 않고 보완할 지점만 짚는다.
///
/// 공고에 맞춘 첨삭은 팀원의 첨삭 모듈(S32-17)이 맡는다. 여기엔 그 연결이 없다.
class ResumeAnalysis {
  const ResumeAnalysis({
    required this.strengths,
    required this.improvements,
    required this.nextSteps,
  });

  final List<ResumeAnalysisItem> strengths;
  final List<ResumeAnalysisItem> improvements;
  final List<String> nextSteps;
}

/// 이력서를 규칙 기반으로 분석한다.
///
/// AI가 문장을 대신 고쳐 쓰지 않고, 어디를 어떻게 보완하면 좋은지만 알려준다.
/// 이력서에 적혀 있지 않다는 이유로 경험이 없다고 단정하지도 않는다.
ResumeAnalysis analyzeResume(ResumeContent content) {
  final readiness = ResumeReadiness.of(content);
  final strengths = <ResumeAnalysisItem>[];
  final improvements = <ResumeAnalysisItem>[];
  final nextSteps = <String>[];

  final techStack = content.techStack.where((item) => item.isFilled).toList();
  final projects = content.projects.where((item) => item.isFilled).toList();
  final experience = content.experience.where((item) => item.isFilled).toList();

  if (techStack.isNotEmpty) {
    final names = techStack.map((item) => item.name.trim()).take(6).join(', ');
    strengths.add(
      ResumeAnalysisItem('기술스택 ${techStack.length}건이 작성되어 있습니다: $names'),
    );
  }
  if (projects.isNotEmpty) {
    strengths.add(
      ResumeAnalysisItem('프로젝트 경험 ${projects.length}건이 작성되어 있습니다.'),
    );
  }
  if (experience.isNotEmpty) {
    strengths.add(
      ResumeAnalysisItem('경력 ${experience.length}건이 작성되어 있습니다.'),
    );
  }
  if (content.coreCompetencies.isFilled) {
    strengths.add(
      const ResumeAnalysisItem('핵심역량이 작성되어 있어 첫인상을 전달할 수 있습니다.'),
    );
  }

  // 기술스택에는 있지만 어떤 프로젝트에서 썼는지 드러나지 않는 기술을 찾는다.
  final projectTechText = projects
      .map((item) => '${item.techStack} ${item.description}')
      .join(' ')
      .toLowerCase();
  final unlinkedSkills = techStack
      .map((item) => item.name.trim())
      .where((name) => name.isNotEmpty)
      .where((name) => !projectTechText.contains(name.toLowerCase()))
      .toList();
  if (unlinkedSkills.isNotEmpty) {
    improvements.add(
      ResumeAnalysisItem(
        '${unlinkedSkills.take(5).join(', ')}: 기술스택에는 있으나 어떤 프로젝트에서 '
        '어떻게 사용했는지 드러나지 않습니다.',
      ),
    );
    nextSteps.add('프로젝트 설명에 사용 기술과 담당 기능을 연결해 적어보세요.');
  }

  for (final project in projects) {
    final label = project.name.trim().isEmpty ? '프로젝트' : project.name.trim();
    if (project.role.trim().isEmpty) {
      improvements.add(ResumeAnalysisItem('$label: 담당 역할이 비어 있습니다.'));
    }
    if (project.description.trim().length < 50) {
      improvements.add(
        ResumeAnalysisItem('$label: 설명이 짧아 문제 해결 과정과 성과가 드러나지 않습니다.'),
      );
    }
  }
  if (projects.isEmpty) {
    improvements.add(
      const ResumeAnalysisItem('프로젝트 경험이 없어 기술을 실제로 사용한 근거를 보여주기 어렵습니다.'),
    );
  }

  if (readiness.missingRequiredSections.isNotEmpty) {
    improvements.add(
      ResumeAnalysisItem(
        '맞춤 공고 추천에 필요한 항목이 비어 있습니다: '
        '${readiness.missingRequiredSectionLabels.join(', ')}',
      ),
    );
  }

  // 아직 작성하지 않은 선택 항목은 '부족'이 아니라 '추가하면 좋은 것'으로 안내한다.
  final optionalEmpty = AppConstants.resumeSections
      .where((key) => !requiredSectionsForRecommendation.contains(key))
      .where((key) => !evidenceSectionsForRecommendation.contains(key))
      .where((key) => !readiness.filledSections.contains(key))
      .map((key) => AppConstants.resumeSectionLabels[key] ?? key)
      .toList();
  if (optionalEmpty.isNotEmpty) {
    nextSteps.add('선택 항목으로 ${optionalEmpty.join(', ')}을(를) 추가할 수 있습니다.');
  }

  if (improvements.isEmpty) {
    nextSteps.add('주요 항목이 모두 작성되어 있습니다. 맞춤 공고 추천을 실행해보세요.');
  }

  return ResumeAnalysis(
    strengths: strengths,
    improvements: improvements,
    nextSteps: nextSteps,
  );
}
