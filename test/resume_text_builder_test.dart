import 'package:flutter_test/flutter_test.dart';

import 'package:playdata_lms/features/resume/ai_coach/data/resume_text_builder.dart';
import 'package:playdata_lms/shared/models/resume_content.dart';

ResumeContent _resume() => const ResumeContent(
  basicInfo: ResumeBasicInfo(name: '홍길동', email: 'hong@example.com'),
  coreCompetencies: ResumeCoreCompetencies(text: 'Python 백엔드 개발자입니다.'),
  techStack: [
    ResumeTechStackItem(id: 't1', name: 'Python', level: '중급'),
    ResumeTechStackItem(id: 't2', name: 'FastAPI'),
  ],
  projects: [
    ResumeProjectItem(
      id: 'p1',
      name: '추천 서비스',
      startDate: '2026.01',
      endDate: '2026.03',
      role: '백엔드 개발',
      techStack: 'Python, FastAPI',
      description: 'FastAPI로 추천 API를 개발하고 응답 속도를 개선했습니다.',
    ),
  ],
  selfIntroduction: ResumeSelfIntroduction(
    motivation: ResumeIntroSection(subtitle: '왜 지원하나', body: '교육 서비스에 기여하고 싶습니다.'),
  ),
);

void main() {
  group('이력서 평문 변환', () {
    test('사용자 문장을 그대로 담아 서버가 인용을 대조할 수 있게 한다', () {
      final text = buildResumeText(_resume());
      expect(text, contains('[핵심역량]\nPython 백엔드 개발자입니다.'));
      expect(text, contains('Python (중급)'));
      expect(text, contains('- 추천 서비스 (2026.01 ~ 2026.03)'));
      expect(text, contains('FastAPI로 추천 API를 개발하고 응답 속도를 개선했습니다.'));
      expect(text, contains('[자기소개서]'));
      expect(text, contains('(지원동기) 왜 지원하나\n교육 서비스에 기여하고 싶습니다.'));
    });

    test('빈 항목은 섹션 자체를 만들지 않는다', () {
      final text = buildResumeText(
        const ResumeContent(
          techStack: [ResumeTechStackItem(id: 't1', name: 'Dart')],
        ),
      );
      expect(text, '[기술스택]\nDart');
    });
  });

  /// 이력서를 언제 실어 보낼지.
  ///
  /// "나한테 맞아?"는 이력서를 봐야 답이 된다. 그런데 이번 말이 공고를 놓고 묻는
  /// 말인지는 서버가 가른다. 앱은 **가리킬 것이 있는지**만 보고 정한다.
  group('이력서를 함께 보낼 때', () {
    test('카드를 눌러 물으면 보낸다', () {
      expect(
        shouldSendResume(askingAboutJob: true, hasShownJobs: false),
        isTrue,
      );
    });

    test('직전에 목록을 보여 줬으면 보낸다', () {
      // "1번하고 3번 중 나한테 맞는 건?"이 여기서 걸린다. 카드를 누르지 않았다.
      expect(
        shouldSendResume(askingAboutJob: false, hasShownJobs: true),
        isTrue,
      );
    });

    test('가리킬 것이 없으면 보내지 않는다', () {
      // 첫 질문과 잡담. 서버가 쓰지 않으므로 보낼 이유가 없다.
      expect(
        shouldSendResume(askingAboutJob: false, hasShownJobs: false),
        isFalse,
      );
    });
  });
}
