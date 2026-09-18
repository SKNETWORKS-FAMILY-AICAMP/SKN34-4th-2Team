import 'package:flutter_test/flutter_test.dart';

import 'package:playdata_lms/features/resume/ai_coach/data/resume_analyzer.dart';
import 'package:playdata_lms/features/resume/ai_coach/models/resume_readiness.dart';
import 'package:playdata_lms/shared/models/resume_content.dart';

/// 필수 항목을 모두 채운 이력서.
ResumeContent _completeResume() => const ResumeContent(
  basicInfo: ResumeBasicInfo(name: '홍길동', email: 'hong@example.com'),
  coreCompetencies: ResumeCoreCompetencies(text: 'Python 백엔드 개발자입니다.'),
  education: [ResumeEducationItem(id: 'e1', school: '한국대학교', major: '컴퓨터공학')],
  techStack: [ResumeTechStackItem(id: 't1', name: 'Python')],
  projects: [
    ResumeProjectItem(
      id: 'p1',
      name: '추천 서비스',
      role: '백엔드 개발',
      techStack: 'Python, FastAPI',
      description: 'FastAPI로 추천 API를 개발하고 응답 속도를 개선했습니다.',
    ),
  ],
  selfIntroduction: ResumeSelfIntroduction(
    growth: ResumeIntroSection(subtitle: '성장 과정', body: '꾸준히 학습했습니다.'),
  ),
);

void main() {
  group('맞춤 공고 추천 게이트', () {
    test('빈 이력서는 추천을 실행할 수 없다', () {
      final readiness = ResumeReadiness.of(ResumeContent.empty());
      expect(readiness.canRecommendJobs, isFalse);
      expect(
        readiness.missingRequiredSections.length,
        requiredSectionsForRecommendation.length,
      );
    });

    test('학력이 비면 추천을 실행할 수 없다', () {
      // 하드 필터가 공고의 학력 조건과 대조하는 값이라 없으면 판정이 흐려진다.
      final content = _completeResume().copyWith(education: const []);
      final readiness = ResumeReadiness.of(content);
      expect(readiness.canRecommendJobs, isFalse);
      expect(readiness.missingRequiredSectionLabels, contains('학력사항'));
    });

    test('핵심역량이 비어도 다른 근거가 있으면 추천한다', () {
      // 직무 근거는 자기소개서에도 프로젝트에도 기술스택에도 있다. 한 칸이 비었다고
      // 막는 것은 값에 비해 불편하다.
      final content = _completeResume().copyWith(
        coreCompetencies: const ResumeCoreCompetencies(),
      );
      final readiness = ResumeReadiness.of(content);
      expect(readiness.canRecommendJobs, isTrue);
      expect(readiness.blockedReason(AiCoachFeature.jobRecommendation), isNull);
    });

    test('기술스택이 비어도 프로젝트가 있으면 추천한다', () {
      final content = _completeResume().copyWith(techStack: const []);
      expect(ResumeReadiness.of(content).canRecommendJobs, isTrue);
    });

    test('근거가 하나도 없으면 무엇을 적어야 할지 알려준다', () {
      final content = _completeResume().copyWith(
        coreCompetencies: const ResumeCoreCompetencies(),
        techStack: const [],
        projects: const [],
        selfIntroduction: const ResumeSelfIntroduction(),
      );
      final readiness = ResumeReadiness.of(content);
      expect(readiness.canRecommendJobs, isFalse);
      expect(readiness.hasJobEvidence, isFalse);
      final reason = readiness.blockedReason(AiCoachFeature.jobRecommendation);
      expect(reason, contains('하나 이상'));
      expect(reason, contains('자기소개서'));
    });

    test('필수 항목을 모두 채우면 추천을 실행할 수 있다', () {
      final readiness = ResumeReadiness.of(_completeResume());
      expect(readiness.canRecommendJobs, isTrue);
      expect(readiness.missingRequiredSections, isEmpty);
      expect(readiness.blockedReason(AiCoachFeature.jobRecommendation), isNull);
    });

    test('경력이 없어도 추천을 막지 않는다', () {
      // 신입 사용자가 영구히 막히면 안 된다.
      final readiness = ResumeReadiness.of(_completeResume());
      expect(readiness.filledSections, isNot(contains('experience')));
      expect(readiness.canRecommendJobs, isTrue);
    });

    test('자기소개서만 있으면 막지 않되 근거가 얇다고 알린다', () {
      // 여섯 항목 중 하나만 채워도 "있음"이 된다. 막지 않는 대신 왜 약한지 말한다.
      final content = _completeResume().copyWith(
        coreCompetencies: const ResumeCoreCompetencies(),
        techStack: const [],
        projects: const [],
      );
      final readiness = ResumeReadiness.of(content);
      expect(readiness.canRecommendJobs, isTrue);
      expect(readiness.weakEvidenceHint, contains('기술스택'));
    });

    test('기술스택이나 프로젝트가 있으면 안내하지 않는다', () {
      expect(ResumeReadiness.of(_completeResume()).weakEvidenceHint, isNull);
    });

    test('근거가 아예 없으면 안내 대신 막는다', () {
      final content = _completeResume().copyWith(
        coreCompetencies: const ResumeCoreCompetencies(),
        techStack: const [],
        projects: const [],
        selfIntroduction: const ResumeSelfIntroduction(),
      );
      final readiness = ResumeReadiness.of(content);
      expect(readiness.weakEvidenceHint, isNull);
      expect(readiness.canRecommendJobs, isFalse);
    });

    test('막힌 이유에 비어 있는 필수 항목 이름이 들어간다', () {
      final content = _completeResume().copyWith(education: const []);
      final reason = ResumeReadiness.of(
        content,
      ).blockedReason(AiCoachFeature.jobRecommendation);
      expect(reason, contains('학력사항'));
    });
  });

  group('이력서 분석 게이트', () {
    test('빈 이력서는 분석할 수 없다', () {
      expect(
        ResumeReadiness.of(ResumeContent.empty()).canAnalyzeResume,
        isFalse,
      );
    });

    test('기술스택만 있어도 분석할 수 있다', () {
      const content = ResumeContent(
        techStack: [ResumeTechStackItem(id: 't1', name: 'Python')],
      );
      final readiness = ResumeReadiness.of(content);
      expect(readiness.canAnalyzeResume, isTrue);
      // 분석은 되지만 추천은 아직 안 된다.
      expect(readiness.canRecommendJobs, isFalse);
    });

    test('프로젝트 근거가 없는 기술을 보완 항목으로 알려준다', () {
      const content = ResumeContent(
        techStack: [ResumeTechStackItem(id: 't1', name: 'Kubernetes')],
      );
      final analysis = analyzeResume(content);
      expect(
        analysis.improvements.map((item) => item.text).join(),
        contains('Kubernetes'),
      );
    });
  });

}
