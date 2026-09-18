import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../auth/providers/auth_providers.dart';
import '../domain/onboarding_step.dart';
import 'onboarding_controller.dart';
import 'onboarding_overlay.dart';

/// 역할 공통 온보딩 호스트 — 셸 위에 오버레이 + 스텝별 라우트 이동
class OnboardingHost extends ConsumerStatefulWidget {
  const OnboardingHost({
    super.key,
    required this.child,
    required this.tourId,
    required this.version,
    required this.steps,
    this.rootRoutes = const {},
  });

  final Widget child;
  final String tourId;
  final int version;
  final List<OnboardingStep> steps;

  /// exact match만 허용할 루트 경로 (`/`, `/admin`, `/instructor` 등)
  final Set<String> rootRoutes;

  @override
  ConsumerState<OnboardingHost> createState() => _OnboardingHostState();
}

class _OnboardingHostState extends ConsumerState<OnboardingHost> {
  String? _bootstrappedUid;
  String? _navigatingForStepId;

  void _tryBootstrap(String uid) {
    if (_bootstrappedUid == uid) return;
    _bootstrappedUid = uid;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      ref
          .read(onboardingTourProvider.notifier)
          .maybeStart(
            tourId: widget.tourId,
            version: widget.version,
            uid: uid,
            steps: widget.steps,
          );
    });
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(currentUserProvider).value;
    final tour = ref.watch(onboardingTourProvider);

    ref.listen(currentUserProvider, (prev, next) {
      final uid = next.value?.uid;
      if (uid == null || uid.isEmpty) return;
      _tryBootstrap(uid);
    });

    if (user != null && user.uid.isNotEmpty) {
      _tryBootstrap(user.uid);
    }

    ref.listen(onboardingTourProvider, (prev, next) {
      if (next == null || !next.active) return;
      if (next.tourId != widget.tourId) return;
      final step = next.currentStep;
      if (step?.route == null) return;
      _ensureRoute(step!.id, step.route!);
    });

    final activeTour =
        (tour != null && tour.active && tour.tourId == widget.tourId)
        ? tour
        : null;
    final activeStep = activeTour?.currentStep;

    if (activeStep?.route != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        _ensureRoute(activeStep!.id, activeStep.route!);
      });
    }

    return Stack(
      children: [
        widget.child,
        if (activeTour != null && activeStep != null)
          Positioned.fill(
            child: OnboardingOverlay(
              // 투어 하나에 오버레이 하나. 단계 id까지 키에 넣으면 다음을 누를
              // 때마다 오버레이가 통째로 새로 만들어져, 앞 단계의 자리를 잊고
              // 화면 한가운데에서 다시 시작한다.
              key: ValueKey(widget.tourId),
              step: activeStep,
              stepIndex: activeTour.index,
              totalSteps: activeTour.total,
              onNext: () => _onNext(activeTour),
              onPrevious: activeTour.index > 0
                  ? () => _onPrevious(activeTour)
                  : null,
              onDismissForever: () =>
                  ref.read(onboardingTourProvider.notifier).dismissForever(),
              onSkipMissing: () => _onSkipMissing(activeTour),
            ),
          ),
      ],
    );
  }

  bool _isAtRoute(String location, String route) {
    if (route == '/') return location == '/' || location.isEmpty;
    if (widget.rootRoutes.contains(route)) return location == route;
    return location == route || location.startsWith('$route/');
  }

  void _ensureRoute(String stepId, String route) {
    if (!mounted) return;
    // 이전 프레임에서 예약한 라우트 이동이 새 단계를 되돌리지 않게 한다.
    final current = ref.read(onboardingTourProvider);
    if (current?.tourId != widget.tourId ||
        current?.currentStep?.id != stepId) {
      return;
    }
    final location = GoRouterState.of(context).matchedLocation;
    if (_isAtRoute(location, route)) return;
    if (_navigatingForStepId == stepId) return;
    _navigatingForStepId = stepId;
    context.go(route);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _navigatingForStepId = null;
    });
  }

  Future<void> _onNext(OnboardingTourState tour) async {
    final notifier = ref.read(onboardingTourProvider.notifier);
    if (tour.isLast) {
      // 투어는 화면을 옮겨 다니므로 마지막 단계의 화면에서 끝난다. 첫 단계의
      // 화면으로 데려다 놓아야 둘러보기 전에 있던 자리로 돌아온 것이 된다.
      final home = tour.steps.first.route;
      await notifier.dismissForever();
      if (!mounted || home == null) return;
      context.go(home);
      return;
    }
    _goToIndex(tour, tour.index + 1);
  }

  void _goToIndex(OnboardingTourState tour, int index) {
    // 단계와 라우트를 같은 이벤트에서 갱신한다. 라우트만 먼저 바꾸면
    // 새 메뉴가 선택된 동안 이전 단계의 강조가 남고, build가 되돌아간다.
    final current = ref.read(onboardingTourProvider);
    if (!identical(current, tour)) return;
    ref.read(onboardingTourProvider.notifier).goToIndex(index);
  }

  void _onPrevious(OnboardingTourState tour) {
    if (tour.index <= 0) return;
    _goToIndex(tour, tour.index - 1);
  }

  Future<void> _onSkipMissing(OnboardingTourState tour) async {
    if (!identical(ref.read(onboardingTourProvider), tour)) return;
    if (tour.isLast) {
      await ref.read(onboardingTourProvider.notifier).dismissForever();
      return;
    }
    _goToIndex(tour, tour.index + 1);
  }
}
