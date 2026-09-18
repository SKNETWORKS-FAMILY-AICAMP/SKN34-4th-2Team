import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:playdata_lms/features/auth/providers/auth_providers.dart';
import 'package:playdata_lms/features/onboarding/domain/onboarding_step.dart';
import 'package:playdata_lms/features/onboarding/domain/onboarding_target_registry.dart';
import 'package:playdata_lms/features/onboarding/presentation/onboarding_controller.dart';
import 'package:playdata_lms/features/onboarding/presentation/onboarding_host.dart';
import 'package:playdata_lms/features/onboarding/presentation/onboarding_overlay.dart';

const _steps = [
  OnboardingStep(
    id: 'a',
    title: 'First menu',
    body: 'First description',
    targetId: 'host-a',
    route: '/a',
  ),
  OnboardingStep(
    id: 'b',
    title: 'Second menu',
    body: 'Second description',
    targetId: 'host-b',
    route: '/b',
  ),
  OnboardingStep(
    id: 'c',
    title: 'Third menu',
    body: 'Third description',
    targetId: 'host-c',
    route: '/c',
  ),
];

class _StartedTour extends OnboardingTourNotifier {
  @override
  OnboardingTourState build() => const OnboardingTourState(
    tourId: 'test',
    version: 1,
    uid: 'test-user',
    steps: _steps,
    index: 0,
    active: true,
  );
}

void main() {
  testWidgets(
    'route and step change together without returning to the old route',
    (tester) async {
      final container = ProviderContainer(
        overrides: [
          currentUserProvider.overrideWith((ref) => Stream.value(null)),
          onboardingTourProvider.overrideWith(_StartedTour.new),
        ],
      );
      addTearDown(container.dispose);
      final router = GoRouter(
        initialLocation: '/a',
        routes: [
          ShellRoute(
            builder: (context, state, child) => OnboardingHost(
              tourId: 'test',
              version: 1,
              steps: _steps,
              child: Scaffold(
                body: Row(
                  children: [
                    Column(
                      children: [
                        for (final step in _steps)
                          SizedBox(
                            key: OnboardingTargetRegistry.keyOf(step.targetId),
                            width: 120,
                            height: 48,
                            child: Text('Menu ${step.id}'),
                          ),
                      ],
                    ),
                    Expanded(child: child),
                  ],
                ),
              ),
            ),
            routes: [
              for (final step in _steps)
                GoRoute(
                  path: step.route!,
                  builder: (context, state) => Text('Page ${step.id}'),
                ),
            ],
          ),
        ],
      );
      addTearDown(router.dispose);
      final visited = <String>[];
      router.routerDelegate.addListener(() {
        visited.add(router.routerDelegate.currentConfiguration.uri.path);
      });
      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: container,
          child: MaterialApp.router(routerConfig: router),
        ),
      );
      await tester.pumpAndSettle();
      visited.clear();

      await tester.tap(find.text('다음'));
      // The notifier must change during the same input event, without a timer.
      expect(container.read(onboardingTourProvider)!.index, 1);
      await tester.pump();
      expect(find.text('Page b'), findsOneWidget);
      await tester.pumpAndSettle();
      expect(visited, isNot(contains('/a')));
      expect(find.text('Second menu'), findsOneWidget);
      final highlight = find.byKey(const ValueKey('onboarding-highlight'));
      expect(
        tester.getRect(highlight),
        tester
            .getRect(
              find.byKey(
                OnboardingTargetRegistry.keyOf('host-b'),
              ),
            )
            .inflate(10),
      );

      await tester.tap(find.text('다음'));
      await tester.pumpAndSettle();
      expect(container.read(onboardingTourProvider)!.index, 2);
      visited.clear();
      // A duplicate callback from the old card must not move back twice.
      final previous = tester
          .widget<OnboardingOverlay>(find.byType(OnboardingOverlay))
          .onPrevious!;
      previous();
      previous();
      expect(container.read(onboardingTourProvider)!.index, 1);
      await tester.pumpAndSettle();
      expect(find.text('Page b'), findsOneWidget);
      expect(visited, isNot(contains('/c')));
      expect(visited, isNot(contains('/a')));
      expect(tester.takeException(), isNull);
    },
  );
}
