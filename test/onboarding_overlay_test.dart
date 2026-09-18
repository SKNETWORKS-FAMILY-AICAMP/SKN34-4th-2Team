import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/features/onboarding/domain/onboarding_step.dart';
import 'package:playdata_lms/features/onboarding/domain/onboarding_target_registry.dart';
import 'package:playdata_lms/features/onboarding/presentation/onboarding_overlay.dart';

const _left = OnboardingStep(
  id: 'left',
  title: '왼쪽',
  body: '왼쪽 자리 설명',
  targetId: 'onboarding-test-left',
);

const _right = OnboardingStep(
  id: 'right',
  title: '오른쪽',
  body: '오른쪽 자리 설명',
  targetId: 'onboarding-test-right',
);

/// 두 타깃을 화면 양 끝에 놓고 그 위에 안내를 띄운다.
Widget _screen(
  OnboardingStep step, {
  required VoidCallback onNext,
  VoidCallback? onPrevious,
}) => MaterialApp(
  home: Scaffold(
    body: Stack(
      children: [
        Positioned(
          left: 24,
          top: 80,
          child: SizedBox(
            key: OnboardingTargetRegistry.keyOf(_left.targetId),
            width: 120,
            height: 48,
          ),
        ),
        Positioned(
          left: 24,
          top: 420,
          child: SizedBox(
            key: OnboardingTargetRegistry.keyOf(_right.targetId),
            width: 120,
            height: 48,
          ),
        ),
        OnboardingOverlay(
          step: step,
          stepIndex: step == _left ? 0 : 1,
          totalSteps: 2,
          onNext: onNext,
          onPrevious: onPrevious,
          onDismissForever: () {},
          onSkipMissing: () {},
        ),
      ],
    ),
  ),
);

double _cardTop(WidgetTester tester, Finder title) => tester
    .getTopLeft(find.ancestor(of: title, matching: find.byType(Material)).first)
    .dy;

double _cardOpacity(WidgetTester tester, Finder title) => tester
    .widget<AnimatedOpacity>(
      find.ancestor(of: title, matching: find.byType(AnimatedOpacity)).first,
    )
    .opacity;

void main() {
  testWidgets('the first step offers no way back', (tester) async {
    await tester.pumpWidget(_screen(_left, onNext: () {}));
    await tester.pumpAndSettle();
    expect(find.text('이전'), findsNothing);
    expect(find.text('다음'), findsOneWidget);
  });

  testWidgets('a later step can step back, and the last one finishes', (
    tester,
  ) async {
    var back = 0;
    await tester.pumpWidget(
      _screen(_right, onNext: () {}, onPrevious: () => back++),
    );
    await tester.pumpAndSettle();
    // 두 단계짜리 투어의 끝이다.
    expect(find.text('완료'), findsOneWidget);
    await tester.tap(find.text('이전'));
    await tester.pump();
    expect(back, 1);
  });

  testWidgets('the card stays hidden until it knows where to sit', (
    tester,
  ) async {
    await tester.pumpWidget(_screen(_left, onNext: () {}));
    expect(_cardOpacity(tester, find.text('왼쪽')), 0);
    await tester.pumpAndSettle();
    expect(_cardOpacity(tester, find.text('왼쪽')), 1);
  });

  testWidgets('the card is never seen anywhere but its own place', (
    tester,
  ) async {
    var step = _left;
    late StateSetter rebuild;
    await tester.pumpWidget(
      StatefulBuilder(
        builder: (context, setState) {
          rebuild = setState;
          return _screen(step, onNext: () => setState(() => step = _right));
        },
      ),
    );
    await tester.pumpAndSettle();
    final firstTop = _cardTop(tester, find.text('왼쪽'));

    // 자리를 모르는 카드가 떨어지던 곳. 화면 한가운데다.
    final middle = (600 - 168) / 2;
    expect((firstTop - middle).abs(), greaterThan(1));

    rebuild(() => step = _right);
    // 새 자리를 재는 동안에는 앞자리에 머문다. 한가운데로 흘러가면 안 된다.
    final seen = <double>[];
    for (var i = 0; i < 12; i++) {
      await tester.pump(const Duration(milliseconds: 30));
      final title = find.text('오른쪽');
      if (title.evaluate().isEmpty) continue;
      if (_cardOpacity(tester, title) > 0) seen.add(_cardTop(tester, title));
    }
    await tester.pumpAndSettle();

    final lastTop = _cardTop(tester, find.text('오른쪽'));
    expect(_cardOpacity(tester, find.text('오른쪽')), 1);
    expect(lastTop, isNot(firstTop));
    // 앞자리 아니면 새 자리. 그 사이 어디에도 서지 않는다.
    expect(seen, everyElement(anyOf(firstTop, lastTop)));
    expect(seen, isNot(contains(middle)));
    expect(tester.takeException(), isNull);
  });

  testWidgets('a target down the list is pulled in with one jump', (
    tester,
  ) async {
    final controller = ScrollController();
    addTearDown(controller.dispose);
    const far = OnboardingStep(
      id: 'far',
      title: '멀리',
      body: '목록 아래쪽 항목',
      targetId: 'onboarding-test-far',
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Stack(
            children: [
              SingleChildScrollView(
                controller: controller,
                child: Column(
                  children: [
                    for (var i = 0; i < 30; i++) const SizedBox(height: 48),
                    SizedBox(
                      key: OnboardingTargetRegistry.keyOf(far.targetId),
                      height: 48,
                      width: 100,
                    ),
                    for (var i = 0; i < 30; i++) const SizedBox(height: 48),
                  ],
                ),
              ),
              OnboardingOverlay(
                step: far,
                stepIndex: 0,
                totalSteps: 1,
                onNext: () {},
                onPrevious: null,
                onDismissForever: () {},
                onSkipMissing: () {},
              ),
            ],
          ),
        ),
      ),
    );
    expect(controller.offset, 0);

    final offsets = <double>{};
    for (var i = 0; i < 12; i++) {
      await tester.pump(const Duration(milliseconds: 30));
      offsets.add(controller.offset);
    }
    await tester.pumpAndSettle();

    // 목록이 실제로 끌려왔다.
    expect(controller.offset, greaterThan(0));
    // 그 사이 어떤 중간 자리도 거치지 않았다. 굴러가면 여러 값이 찍힌다.
    expect(offsets.length, lessThanOrEqualTo(2));
    expect(tester.takeException(), isNull);
  });
  testWidgets('a new step never highlights the previous target', (
    tester,
  ) async {
    await tester.pumpWidget(_screen(_left, onNext: () {}));
    await tester.pumpAndSettle();
    final highlight = find.byKey(const ValueKey('onboarding-highlight'));
    expect(
      tester.getRect(highlight),
      tester
          .getRect(
            find.byKey(
              OnboardingTargetRegistry.keyOf(_left.targetId),
            ),
          )
          .inflate(10),
    );

    await tester.pumpWidget(_screen(_right, onNext: () {}));
    expect(highlight, findsNothing);
    await tester.pumpAndSettle();
    expect(
      tester.getRect(highlight),
      tester
          .getRect(
            find.byKey(
              OnboardingTargetRegistry.keyOf(_right.targetId),
            ),
          )
          .inflate(10),
    );
  });

  testWidgets(
    'visible menus stay still and clipped menus scroll only to the edge',
    (tester) async {
      final controller = ScrollController();
      addTearDown(controller.dispose);
      final steps = List.generate(
        3,
        (i) => OnboardingStep(
          id: 'scroll-$i',
          title: 'Menu $i',
          body: 'Menu description',
          targetId: 'onboarding-test-scroll-$i',
        ),
      );
      var index = 0;
      late StateSetter rebuild;
      await tester.pumpWidget(
        MaterialApp(
          home: StatefulBuilder(
            builder: (context, setState) {
              rebuild = setState;
              return Scaffold(
                body: Stack(
                  children: [
                    SizedBox(
                      height: 360,
                      width: 200,
                      child: SingleChildScrollView(
                        controller: controller,
                        child: Column(
                          children: [
                            const SizedBox(height: 100),
                            SizedBox(
                              key: OnboardingTargetRegistry.keyOf(
                                steps[0].targetId,
                              ),
                              height: 48,
                              width: 160,
                            ),
                            const SizedBox(height: 52),
                            SizedBox(
                              key: OnboardingTargetRegistry.keyOf(
                                steps[1].targetId,
                              ),
                              height: 48,
                              width: 160,
                            ),
                            const SizedBox(height: 92),
                            SizedBox(
                              key: OnboardingTargetRegistry.keyOf(
                                steps[2].targetId,
                              ),
                              height: 48,
                              width: 160,
                            ),
                            const SizedBox(height: 600),
                          ],
                        ),
                      ),
                    ),
                    OnboardingOverlay(
                      step: steps[index],
                      stepIndex: index,
                      totalSteps: 3,
                      onNext: () {},
                      onPrevious: null,
                      onDismissForever: () {},
                      onSkipMissing: () {},
                    ),
                  ],
                ),
              );
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(controller.offset, 0);
      rebuild(() => index = 1);
      await tester.pumpAndSettle();
      expect(controller.offset, 0);
      rebuild(() => index = 2);
      await tester.pumpAndSettle();
      // The target ends at 388; the scroll viewport ends at 360, above the footer.
      expect(controller.offset, 28);

      // Going back to a menu clipped above the viewport reveals its leading edge.
      controller.jumpTo(180);
      await tester.pump();
      rebuild(() => index = 0);
      await tester.pumpAndSettle();
      expect(controller.offset, 100);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets('a lower rail card stays beside the highlighted menu', (
    tester,
  ) async {
    await tester.pumpWidget(_screen(_right, onNext: () {}, onPrevious: () {}));
    await tester.pumpAndSettle();
    final card = tester.getRect(
      find
          .ancestor(of: find.text('오른쪽'), matching: find.byType(Material))
          .first,
    );
    final highlight = tester.getRect(
      find.byKey(const ValueKey('onboarding-highlight')),
    );
    expect(card.left, closeTo(highlight.right + 12, 0.01));
    expect(card.center.dy, closeTo(highlight.center.dy, 0.01));
  });

  for (final longBody in [false, true]) {
    testWidgets('bottom card uses its actual height (long body: $longBody)', (
      tester,
    ) async {
      final step = OnboardingStep(
        id: 'bottom-card',
        title: 'Bottom menu',
        body: longBody
            ? List.filled(6, 'A longer menu description.').join(' ')
            : 'Short description.',
        targetId: 'onboarding-bottom-card',
      );
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Stack(
              children: [
                Positioned(
                  left: 24,
                  bottom: 32,
                  child: SizedBox(
                    key: OnboardingTargetRegistry.keyOf(step.targetId),
                    width: 120,
                    height: 48,
                  ),
                ),
                OnboardingOverlay(
                  step: step,
                  stepIndex: 1,
                  totalSteps: 3,
                  onNext: () {},
                  onPrevious: () {},
                  onDismissForever: () {},
                  onSkipMissing: () {},
                ),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final card = tester.getRect(
        find
            .ancestor(
              of: find.text(step.title),
              matching: find.byType(Material),
            )
            .first,
      );
      final highlight = tester.getRect(
        find.byKey(const ValueKey('onboarding-highlight')),
      );
      expect(card.left, closeTo(highlight.right + 12, 0.01));
      expect(card.bottom, closeTo(600 - 16, 0.01));
      expect(card.top, lessThan(highlight.bottom));
      expect(card.bottom, greaterThan(highlight.top));
      expect(card.overlaps(highlight), isFalse);
      expect(tester.takeException(), isNull);
    });
  }
}
