import 'package:flutter_test/flutter_test.dart';

import 'package:playdata_lms/features/resume/ai_coach/data/chat_job_refs.dart';

/// "2번"이 무엇을 가리키는가.
///
/// 서버는 대화를 저장하지 않으므로 앱이 목록을 되돌려 준다. 그 목록을 언제 갈아
/// 끼울지가 여기서 갈린다. 잘못 끼우면 답은 멀쩡해 보이는데 **다른 공고 이야기**를
/// 한다. 사용자가 알아채기 어렵다.
void main() {
  group('번호가 가리킬 목록', () {
    const shown = ['J1', 'J2', 'J3', 'J4', 'J5'];

    test('찾아 준 목록이 기준이 된다', () {
      expect(
        nextShownJobIds(mode: '검색', jobsInAnswer: shown, previous: const []),
        shown,
      );
    });

    test('비교한 두 건은 목록을 갈아치우지 않는다', () {
      // 2번과 5번을 비교한 뒤 "아까 1번 3번 중에서도 보고 싶어"가 걸리는 자리다.
      expect(
        nextShownJobIds(
          mode: '비교',
          jobsInAnswer: const ['J2', 'J5'],
          previous: shown,
        ),
        shown,
      );
    });

    test('질문 답에 붙는 근거 공고도 목록이 아니다', () {
      // 근거는 "이 숫자를 센 공고들"이지 고르라고 보여 준 목록이 아니다.
      expect(
        nextShownJobIds(
          mode: '질문',
          jobsInAnswer: const ['J9', 'J8', 'J7'],
          previous: shown,
        ),
        shown,
      );
    });

    test('공고 하나에 답한 턴도 그대로 둔다', () {
      expect(
        nextShownJobIds(mode: '공고', jobsInAnswer: const ['J2'], previous: shown),
        shown,
      );
    });

    test('0건인 검색은 앞 목록을 지운다고 볼 이유가 없다', () {
      expect(
        nextShownJobIds(mode: '검색', jobsInAnswer: const [], previous: shown),
        shown,
      );
    });

    test('새로 찾으면 그때는 갈아치운다', () {
      expect(
        nextShownJobIds(
          mode: '검색',
          jobsInAnswer: const ['K1', 'K2'],
          previous: shown,
        ),
        const ['K1', 'K2'],
      );
    });
  });

  group('"이거 말고"에 뺄 공고', () {
    // 예전에는 직전 목록만 기억해서, 서버가 빼 줘도 두 번째 "이거 말고"에 첫 목록이
    // 다시 나올 수밖에 없었다. 끝까지 넘겨 보려면 본 것을 모두 들고 있어야 한다.
    const page1 = ['J1', 'J2', 'J3'];
    const page2 = ['J4', 'J5', 'J6'];

    test('같은 조건으로 넘겨 보면 쌓인다', () {
      final afterTwo = nextSeenJobIds(
        mode: '검색',
        jobsInAnswer: page2,
        previous: page1,
        sameConditions: true,
      );
      expect(afterTwo, [...page1, ...page2]);
    });

    test('조건이 바뀌면 새로 센다', () {
      expect(
        nextSeenJobIds(
          mode: '검색',
          jobsInAnswer: const ['K1'],
          previous: page1,
          sameConditions: false,
        ),
        const ['K1'],
      );
    });

    test('검색이 아닌 답은 본 목록을 바꾸지 않는다', () {
      expect(
        nextSeenJobIds(
          mode: '비교',
          jobsInAnswer: const ['J2', 'J3'],
          previous: page1,
          sameConditions: true,
        ),
        page1,
      );
    });

    test('다 넘겨서 0건이면 그대로 둔다', () {
      expect(
        nextSeenJobIds(
          mode: '검색',
          jobsInAnswer: const [],
          previous: page1,
          sameConditions: true,
        ),
        page1,
      );
    });

    test('같은 공고가 두 번 쌓이지 않는다', () {
      expect(
        nextSeenJobIds(
          mode: '검색',
          jobsInAnswer: const ['J3', 'J4'],
          previous: page1,
          sameConditions: true,
        ),
        const ['J1', 'J2', 'J3', 'J4'],
      );
    });

    test('조건 비교는 서버가 돌려준 값 그대로 본다', () {
      final a = {'roles': ['백엔드'], 'regions': <String>[]};
      expect(sameChatConditions(a, {'roles': ['백엔드'], 'regions': <String>[]}), isTrue);
      expect(sameChatConditions(a, {'roles': ['백엔드'], 'regions': ['서울']}), isFalse);
      expect(sameChatConditions(null, a), isFalse, reason: '첫 검색은 새로 센다');
    });
  });
}
