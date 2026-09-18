import 'package:flutter_test/flutter_test.dart';

import 'package:playdata_lms/features/resume/ai_coach/data/chat_text.dart';

/// 챗봇 답을 그릴 조각으로 나누는 규칙.
///
/// 말풍선이 글자를 그대로 그리던 때에는 강조가 "**엠클라우독은 진입조건이 더 낮고**"
/// 처럼 별표째 나왔다. 항목도 줄글과 구분되지 않았다.
void main() {
  group('굵게', () {
    test('별표로 감싼 말은 굵은 조각이 된다', () {
      expect(parseChatSpans('둘의 차이는 **경력 조건**입니다.'), const [
        ChatSpan('둘의 차이는 '),
        ChatSpan('경력 조건', bold: true),
        ChatSpan('입니다.'),
      ]);
    });

    test('한 줄에 여러 번 나와도 된다', () {
      expect(parseChatSpans('**직무:** 백엔드, **근무지:** 서울'), const [
        ChatSpan('직무:', bold: true),
        ChatSpan(' 백엔드, '),
        ChatSpan('근무지:', bold: true),
        ChatSpan(' 서울'),
      ]);
    });

    test('짝이 안 맞는 별표는 글자로 둔다', () {
      // 지우면 사용자가 쓴 별표까지 사라진다.
      expect(parseChatSpans('별점 **5점'), const [ChatSpan('별점 **5점')]);
    });

    test('별표가 없으면 조각 하나다', () {
      expect(parseChatSpans('안녕하세요!'), const [ChatSpan('안녕하세요!')]);
    });
  });

  group('덩어리', () {
    test('항목 줄은 항목으로 표시된다', () {
      final blocks = parseChatText('준비 순서는 이렇습니다.\n- Java를 정한다\n- SQL을 익힌다');
      expect(blocks.length, 3);
      expect(blocks[0].bullet, isFalse);
      expect(blocks[1].bullet, isTrue);
      expect(blocks[1].plain, 'Java를 정한다');
      expect(blocks[2].plain, 'SQL을 익힌다');
    });

    test('점 기호가 달라도 항목으로 본다', () {
      for (final marker in ['- ', '• ', '* ']) {
        expect(parseChatText('$marker서울 강남구').single.bullet, isTrue,
            reason: marker);
      }
    });

    test('빈 줄은 덩어리가 되지 않는다', () {
      // 덩어리 사이 여백은 화면이 준다. 빈 말풍선 줄을 만들면 안 된다.
      final blocks = parseChatText('첫 문단입니다.\n\n\n둘째 문단입니다.');
      expect(blocks.length, 2);
    });

    test('항목 안의 강조도 읽는다', () {
      final block = parseChatText('- **직무:** 백엔드 개발자').single;
      expect(block.bullet, isTrue);
      expect(block.spans.first, const ChatSpan('직무:', bold: true));
    });

    test('빈 글은 덩어리가 없다', () {
      expect(parseChatText(''), isEmpty);
      expect(parseChatText('   \n  \n'), isEmpty);
    });

    test('점만 있고 내용이 없는 줄은 버린다', () {
      expect(parseChatText('-  \n실제 내용').single.plain, '실제 내용');
    });
  });
}
