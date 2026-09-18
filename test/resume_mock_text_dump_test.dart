// 파이썬 판(job_matching_bot/evaluation/app_resume.py)과 대조할 정답지를 만든다.
//
// 추천 평가는 앱이 서버로 보내는 것과 **같은 글**을 보내야 한다. 예전에는 평가용
// 이력서를 따로 손으로 써서, 자격사항·학력사항·기술스택이 아예 없는 글로 품질을
// 재고 있었다. 이제 원본은 `scripts/resume_mocks.json` 하나이고, 파이썬이 이 파일이
// 떨군 글과 한 글자라도 다르면 `test_app_resume.py`가 잡는다.
//
// 앱 쪽 직렬화를 고쳤다면 이걸 다시 돌려 정답지를 갱신하세요.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/features/resume/ai_coach/data/generated/resume_mocks.g.dart';
import 'package:playdata_lms/features/resume/ai_coach/data/resume_profile.dart';
import 'package:playdata_lms/features/resume/ai_coach/data/resume_text_builder.dart';
import 'package:playdata_lms/shared/models/resume_content.dart';

void main() {
  test('목업 이력서를 서버로 보내는 모양 그대로 떨군다', () {
    final out = <String, dynamic>{};
    for (final persona in resumeMockPersonas) {
      final content = ResumeContent.fromMap(persona.content);
      final profile = RecommendResumeProfile.fromContent(content);
      out[persona.key] = {
        'title': persona.title,
        'resume_text': buildResumeText(content),
        'education_level': profile.educationLevel,
        'career_years': profile.careerYears,
        'majors': profile.majors,
        'certifications': profile.certifications,
      };
    }
    final file = File('test/tmp_dump/dart_resume_text.json');
    file.parent.createSync(recursive: true);
    file.writeAsStringSync(const JsonEncoder.withIndent('  ').convert(out));
    expect(out, hasLength(resumeMockPersonas.length));
  });
}
