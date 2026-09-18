import 'package:flutter_test/flutter_test.dart';

import 'package:playdata_lms/features/resume/ai_coach/data/generated/resume_mocks.g.dart';
import 'package:playdata_lms/features/resume/ai_coach/models/resume_readiness.dart';

void main() {
  group('목업 이력서', () {
    test('생성 파일의 인물이 전부 이력서 본문으로 읽힌다', () {
      expect(resumeMockPersonas, isNotEmpty);
      for (final persona in resumeMockPersonas) {
        final content = persona.toContent(name: '테스트', email: 't@example.com');
        // 이게 거짓이면 앱이 맞춤 공고 추천을 막는다.
        expect(content.hasMatchingEvidence, isTrue, reason: persona.key);
        expect(content.techStack.where((e) => e.isFilled), isNotEmpty, reason: persona.key);
      }
    });

    test('이름·이메일은 계정 값으로 채워진다', () {
      final content = resumeMockPersonas.first.toContent(
        name: '최성욱',
        email: 'me@example.com',
      );
      expect(content.basicInfo.name, '최성욱');
      expect(content.basicInfo.email, 'me@example.com');
      expect(content.basicInfo.isFilled, isTrue);
    });

    test('경력 인물만 경력 항목을 가진다', () {
      final byKey = {for (final p in resumeMockPersonas) p.key: p};
      final experienced = byKey['backend_experienced_3y']!.toContent(name: 'a', email: 'b');
      final entry = byKey['backend_entry']!.toContent(name: 'a', email: 'b');
      expect(experienced.experience.where((e) => e.isFilled), isNotEmpty);
      expect(entry.experience.where((e) => e.isFilled), isEmpty);
    });

    test('추천 준비 판정이 목업으로 통과한다', () {
      for (final persona in resumeMockPersonas) {
        final content = persona.toContent(name: '테스트', email: 't@example.com');
        final readiness = ResumeReadiness.of(content);
        expect(readiness.canRecommendJobs, isTrue, reason: persona.key);
        expect(readiness.canAnalyzeResume, isTrue, reason: persona.key);
      }
    });
  });
}
