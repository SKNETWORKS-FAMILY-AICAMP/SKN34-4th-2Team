import '../../../../shared/models/resume_content.dart';

/// 앱 안에서 빈 이력서에 채워 넣을 수 있는 가상 이력서 한 벌.
///
/// 실제 데이터는 `data/generated/resume_mocks.g.dart`에 자동 생성된다.
/// 원본은 `scripts/resume_mocks.json`이며 Dart에서 직접 내용을 고치지 않는다.
/// 키는 job_matching_bot/schemas/resume.py 의 mock_resumes() 와 같다.
class ResumeMockPersona {
  const ResumeMockPersona({
    required this.key,
    required this.title,
    required this.content,
  });

  final String key;
  final String title;

  /// Firestore `content` 필드와 같은 모양. `ResumeContent.fromMap`으로 읽는다.
  final Map<String, dynamic> content;

  /// 이름·이메일을 로그인 계정 값으로 채운 이력서 본문.
  /// 가상 인물 데이터가 남의 이름으로 저장되지 않게 한다.
  ResumeContent toContent({required String name, required String email}) {
    final parsed = ResumeContent.fromMap(content);
    return parsed.copyWith(
      basicInfo: parsed.basicInfo.copyWith(name: name, email: email),
    );
  }
}
