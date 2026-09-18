/// 강사 화면의 「피드백 작성」 대화상자를 그대로 띄워 본다.
///
/// 실제 화면에서는 어두운 막만 뜨고 내용이 안 나오면서 로그가 쏟아졌다.
/// 여기서 재현되면 대화상자 안쪽 문제이고, 안 되면 부르는 쪽 문제다.
library;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/core/constants/app_constants.dart';
import 'package:playdata_lms/core/widgets/app_dropdown.dart';

Future<void> _open(WidgetTester tester) async {
  String sectionKey = AppConstants.resumeSections.first;
  final contentCtrl = TextEditingController();

  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () => showDialog<void>(
              context: context,
              builder: (ctx) => StatefulBuilder(
                builder: (ctx, setState) => AlertDialog(
                  title: const Text('피드백 작성'),
                  // 너비를 정해 준다. 안 그러면 AlertDialog 가 내용의 고유 크기를
                  // 재려 하는데, 섹션 드롭다운이 LayoutBuilder 로 되어 있어 그 계산을
                  // 하지 못한다. 레이아웃이 실패하면서 크기가 0이 되고, 마우스가
                  // 지날 때마다 히트 테스트 오류가 매 프레임 쏟아진다.
                  content: SizedBox(
                    width: 360,
                    child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      AppDropdownField<String>(
                        value: sectionKey,
                        decoration: const InputDecoration(labelText: '섹션'),
                        items: [
                          for (final k in AppConstants.resumeSections)
                            AppDropdownItem(
                              value: k,
                              label: AppConstants.resumeSectionLabels[k] ?? k,
                            ),
                        ],
                        onChanged: (v) {
                          if (v != null) setState(() => sectionKey = v);
                        },
                      ),
                      TextField(
                        controller: contentCtrl,
                        decoration:
                            const InputDecoration(labelText: '피드백 내용'),
                        maxLines: 3,
                      ),
                    ],
                  ),
                  ),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(ctx),
                      child: const Text('취소'),
                    ),
                    ElevatedButton(
                      onPressed: () => Navigator.pop(ctx),
                      child: const Text('등록'),
                    ),
                  ],
                ),
              ),
            ),
            child: const Text('피드백 작성'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('피드백 작성'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('대화상자가 뜨고 입력칸이 보인다', (tester) async {
    await _open(tester);
    expect(find.text('피드백 작성'), findsWidgets);
    expect(find.text('섹션'), findsOneWidget);
    expect(find.text('피드백 내용'), findsOneWidget);
    expect(find.byType(TextField), findsOneWidget);
  });

  testWidgets('입력칸이 눌린다 — 크기 없는 상자가 없다', (tester) async {
    await _open(tester);
    expect(find.byType(TextField).hitTestable(), findsOneWidget);
    await tester.tap(find.byType(TextField));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '성과를 숫자로 적어 주세요.');
    await tester.pumpAndSettle();
    expect(find.text('성과를 숫자로 적어 주세요.'), findsOneWidget);
  });

  testWidgets('섹션 목록을 펼칠 수 있다', (tester) async {
    await _open(tester);
    await tester.tap(find.text('기본정보'));
    await tester.pumpAndSettle();
    // 메뉴가 열리면 같은 이름이 두 번(필드 + 메뉴) 나온다.
    expect(find.text('프로젝트 경험'), findsWidgets);
  });

  testWidgets('마우스를 올려도 오류가 나지 않는다', (tester) async {
    await _open(tester);
    final pointer = TestPointer(1, PointerDeviceKind.mouse);
    await tester.sendEventToBinding(
      pointer.hover(tester.getCenter(find.byType(AlertDialog))),
    );
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget);
  });
}
