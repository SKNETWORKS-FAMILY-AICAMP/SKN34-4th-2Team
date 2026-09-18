import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/core/theme/app_space.dart';
import 'package:playdata_lms/core/widgets/compact_text_scale.dart';
import 'package:playdata_lms/shared/widgets/app_section_card.dart';

void main() {
  tearDown(() => AppSpace.apply(compact: false));

  test('compact trims spacing, leaves alignment nudges alone', () {
    AppSpace.apply(compact: false);
    expect(AppSpace.s(16), 16);

    AppSpace.apply(compact: true);
    expect(AppSpace.s(16), lessThan(16));
    expect(AppSpace.s(24), lessThan(24));
    // 4 이하는 선·아이콘을 맞추는 값이라 줄이면 어긋난다.
    expect(AppSpace.s(4), 4);
    expect(AppSpace.s(2), 2);
  });

  test('fixed row heights shrink too, but less than spacing', () {
    // 공지 목록은 줄 높이가 42로 박혀 있어 여백만 줄였을 때 그대로였다.
    AppSpace.apply(compact: false);
    expect(AppSpace.row(42), 42);

    AppSpace.apply(compact: true);
    expect(AppSpace.row(42), lessThan(42));
    // 줄에는 글자가 들어가야 하므로 여백보다 덜 줄인다.
    expect(AppSpace.row(40) / 40, greaterThan(AppSpace.s(40) / 40));
  });

  Future<double> cardHeight(
    WidgetTester tester, {
    required bool compact,
  }) async {
    AppSpace.apply(compact: compact);
    // 색·여백은 새로 그릴 때 다시 묻는다. 키를 바꿔 새로 만든다.
    await tester.pumpWidget(
      MaterialApp(
        key: ValueKey(compact),
        builder: (context, child) =>
            CompactTextScale(compact: compact, child: child!),
        home: Scaffold(
          body: Align(
            alignment: Alignment.topLeft,
            child: SizedBox(
              width: 300,
              child: AppSectionCard(child: const Text('학생 한 명')),
            ),
          ),
        ),
      ),
    );
    return tester.getSize(find.byType(AppSectionCard)).height;
  }

  testWidgets(
    'compact makes both the card and its text smaller',
    (
      tester,
    ) async {
      final roomy = await cardHeight(tester, compact: false);
      final roomyText = tester.getSize(find.text('학생 한 명')).height;

      final tight = await cardHeight(tester, compact: true);
      final tightText = tester.getSize(find.text('학생 한 명')).height;

      expect(tight, lessThan(roomy));
      // 글자도 작아진다. 여백만 줄였을 때는 촘촘해진 게 눈에 잘 안 띄었다.
      expect(tightText, lessThan(roomyText));
    },
  );
}
