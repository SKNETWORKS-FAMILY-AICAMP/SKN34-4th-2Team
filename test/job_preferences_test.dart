import 'package:flutter_test/flutter_test.dart';

import 'package:playdata_lms/shared/models/job_preferences.dart';

void main() {
  group('JobPreferences', () {
    test('Firestore 맵과 왕복하며 빈 문자열은 버린다', () {
      final prefs = JobPreferences.fromMap({
        'targetRoles': ['백엔드 개발자', ' '],
        'regions': ['서울', 'x'],
        'employmentTypes': null,
      });
      expect(prefs.targetRoles, ['백엔드 개발자']);
      expect(prefs.regions, ['서울', 'x']);
      expect(prefs.employmentTypes, isEmpty);
      expect(JobPreferences.fromMap(prefs.toMap()).summary, prefs.summary);
    });

    test('요약은 채운 항목만 이어 붙인다', () {
      expect(const JobPreferences().summary, '');
      expect(
        const JobPreferences(regions: ['서울', '경기'], employmentTypes: ['정규직']).summary,
        '서울, 경기 · 정규직',
      );
    });
  });
}
