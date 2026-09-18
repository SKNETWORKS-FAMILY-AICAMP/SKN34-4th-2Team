import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/features/resume/ai_coach/presentation/job_resume_review_dialog.dart';
import 'package:playdata_lms/features/resume/ai_coach/presentation/review_dock.dart';
import 'package:playdata_lms/shared/models/resume_content.dart';

import 'job_resume_review_dialog_test.dart' show FakeReviewClient;

/// 첨삭 응답을 시험이 원할 때 돌려준다. 그 전까지 창은 "기다리는 중"이다.
class _SlowReviewClient extends FakeReviewClient {
  final Completer<void> release = Completer<void>();

  @override
  Future<Map<String, dynamic>> review(Map<String, dynamic> body) async {
    await release.future;
    return super.review(body);
  }
}

Widget _app({required Widget home}) => MaterialApp(
  builder: (context, child) => ReviewDockHost(child: child!),
  home: home,
);

void main() {
  testWidgets('첨삭을 기다리는 동안 창을 내려두고, 다른 화면을 봐도 결과를 받는다', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1400, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final client = _SlowReviewClient();
    Object? closedWith = 'not closed';

    await tester.pumpWidget(
      _app(
        home: Builder(
          builder: (context) => Scaffold(
            body: Column(
              children: [
                const Text('이력서 관리 화면'),
                FilledButton(
                  onPressed: () async {
                    const key = ValueKey('review');
                    closedWith = await ReviewDock.show<String>(
                      context,
                      key: key,
                      child: JobResumeReviewDialog(
                        key: key,
                        client: client,
                        cohortId: 'c',
                        resumeId: 'r',
                        generalReview: true,
                        draft: ResumeContent.fromMap({
                          'coreCompetencies': {'text': client.text},
                        }),
                        onChanged: (_) {},
                      ),
                    );
                  },
                  child: const Text('첨삭 열기'),
                ),
                FilledButton(
                  onPressed: () {},
                  child: const Text('다른 버튼'),
                ),
              ],
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('첨삭 열기'));
    await tester.pumpAndSettle();
    expect(find.text('내려두기'), findsNothing, reason: '기다릴 일이 없으면 내려둘 이유도 없다');

    await tester.tap(find.text('첨삭 시작'));
    await tester.pump();
    await tester.pump();
    expect(find.text('내려두기'), findsOneWidget);
    expect(find.textContaining('내려두기를 누르고'), findsOneWidget);

    await tester.tap(find.text('내려두기'));
    await tester.pump();
    expect(find.text('첨삭 시작'), findsNothing, reason: '창은 가려지고');
    expect(find.text('이력서 첨삭 중'), findsOneWidget, reason: '막대가 보인다');
    expect(find.textContaining('펼치기'), findsOneWidget);

    // 창이 가려진 동안 뒤 화면을 누를 수 있다.
    await tester.tap(find.text('다른 버튼'));
    await tester.pump();

    client.release.complete();
    // 결과를 받은 뒤 누락 점검이 한 번 더 돈다. 도는 동안 막대가 계속 움직여
    // pumpAndSettle은 끝나지 않는다. 시간을 조금씩 흘린다.
    for (var i = 0; i < 20; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    expect(find.text('이력서 첨삭 완료'), findsOneWidget);
    expect(client.reviews, 1);
    expect(closedWith, 'not closed', reason: '끝났다고 창을 닫지는 않는다');
    expect(find.text('이력서 첨삭이 끝났어요.'), findsOneWidget, reason: '내려둔 동안 끝나면 알림이 뜬다');
    await tester.pump(const Duration(seconds: 8));
    await tester.pump(const Duration(seconds: 1));
    expect(
      find.text('이력서 첨삭이 끝났어요.'),
      findsNothing,
      reason: '단추가 달려 있어도 안내 알림은 누르지 않으면 저절로 닫힌다',
    );

    await tester.tap(find.text('열기').first);
    await tester.pumpAndSettle();
    expect(
      find.text('이 문장으로 바꾸기'),
      findsOneWidget,
      reason: '내려둔 동안 온 결과가 창에 있다',
    );

    await tester.tap(find.byTooltip('닫기'));
    await tester.pumpAndSettle();
    expect(closedWith, isNull);
    expect(find.text('이력서 첨삭 완료'), findsNothing);

    client.close();
  });

  testWidgets('첨삭 창이 떠 있으면 다른 첨삭 창을 겹쳐 열지 않는다', (tester) async {
    final opened = <String>[];
    await tester.pumpWidget(
      _app(
        home: Builder(
          builder: (context) => Scaffold(
            body: Column(
              children: [
                for (final name in ['A', 'B'])
                  TextButton(
                    onPressed: () => ReviewDock.show<void>(
                      context,
                      key: ValueKey(name),
                      child: Builder(
                        builder: (panelContext) {
                          opened.add(name);
                          return Center(
                            child: Material(
                              child: TextButton(
                                onPressed: () => ReviewDockScope.read(
                                  panelContext,
                                )!.minimize(),
                                child: Text('$name 내려두기'),
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                    child: Text('$name 열기'),
                  ),
              ],
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('A 열기'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('A 내려두기'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('B 열기'));
    await tester.pumpAndSettle();

    expect(find.text('A 내려두기'), findsOneWidget, reason: '떠 있던 창을 다시 펼친다');
    expect(find.text('B 내려두기'), findsNothing);
    expect(opened.toSet(), {'A'});
    expect(find.textContaining('진행 중인 첨삭 창이 있어요'), findsOneWidget);
  });
}
