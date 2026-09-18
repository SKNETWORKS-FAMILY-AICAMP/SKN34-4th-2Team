import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/features/resume/ai_coach/data/generated/resume_mocks.g.dart';
import 'package:playdata_lms/features/resume/ai_coach/data/resume_review_api_client.dart';
import 'package:playdata_lms/shared/models/resume_content.dart';

/// 이력서에 한 글자 칠 때 드는 비용을 잰다.
///
/// 편집 화면은 키 입력마다 화면 전체를 다시 만든다. 그 안에서 이력서 전체를 JSON으로
/// 두 번 직렬화해 견주는 비교가 돌면, 글자가 손가락을 못 따라온다.
void main() {
  test('한 글자 입력이 부르는 비교 비용', () {
    final resume = ResumeContent.fromMap(
      Map<String, dynamic>.from(resumeMockPersonas.first.content),
    );
    final typed = resume.copyWith(
      coreCompetencies: resume.coreCompetencies.copyWith(
        text: '${resume.coreCompetencies.text}가',
      ),
    );
    final stored = resume.toMap();

    final watch = Stopwatch()..start();
    const runs = 200;
    for (var i = 0; i < runs; i++) {
      sameResumeContent(typed, stored);
    }
    watch.stop();

    final perCall = watch.elapsedMicroseconds / runs / 1000;
    // ignore: avoid_print
    print('한 번 비교에 ${perCall.toStringAsFixed(2)}ms '
        '(60fps 한 프레임 예산은 16.7ms)');
    expect(perCall, greaterThan(0));
  });
}
