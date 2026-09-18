import 'package:flutter_test/flutter_test.dart';

import 'package:playdata_lms/core/constants/app_constants.dart';
import 'package:playdata_lms/shared/models/resume_content.dart';

void main() {
  test('앱 상수 확인', () {
    expect(AppConstants.appName, 'PLAYDATA');
    expect(AppConstants.resumeSections.length, 11);
  });

  test('Resume 섹션 라벨 매핑 확인', () {
    expect(AppConstants.resumeSectionLabels['basicInfo'], '기본정보');
  });

  test('빈 이력서는 맞춤 공고 분석 근거가 없다', () {
    expect(ResumeContent.empty().hasMatchingEvidence, isFalse);
  });

  test('기술스택이 있으면 맞춤 공고 분석 근거가 있다', () {
    const content = ResumeContent(
      techStack: [ResumeTechStackItem(id: 'skill-1', name: 'Python')],
    );

    expect(content.hasMatchingEvidence, isTrue);
  });
}
