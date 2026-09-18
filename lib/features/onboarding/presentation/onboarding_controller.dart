import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/onboarding_dismiss_store.dart';
import '../domain/onboarding_step.dart';

class OnboardingTourState {
  const OnboardingTourState({
    required this.tourId,
    required this.version,
    required this.uid,
    required this.steps,
    required this.index,
    required this.active,
  });

  final String tourId;
  final int version;
  final String uid;
  final List<OnboardingStep> steps;
  final int index;
  final bool active;

  OnboardingStep? get currentStep =>
      active && index >= 0 && index < steps.length ? steps[index] : null;

  int get total => steps.length;

  bool get isLast => index >= steps.length - 1;

  OnboardingTourState copyWith({
    int? index,
    bool? active,
  }) => OnboardingTourState(
    tourId: tourId,
    version: version,
    uid: uid,
    steps: steps,
    index: index ?? this.index,
    active: active ?? this.active,
  );
}

class OnboardingTourNotifier extends Notifier<OnboardingTourState?> {
  @override
  OnboardingTourState? build() => null;

  bool get isActive => state?.active == true;

  Future<void> maybeStart({
    required String tourId,
    required int version,
    required String uid,
    required List<OnboardingStep> steps,
  }) async {
    if (state?.active == true) return;
    if (uid.isEmpty || steps.isEmpty) return;

    final dismissed = await OnboardingDismissStore.isDismissed(
      tourId: tourId,
      version: version,
      uid: uid,
    );
    if (!ref.mounted || dismissed) return;

    state = OnboardingTourState(
      tourId: tourId,
      version: version,
      uid: uid,
      steps: steps,
      index: 0,
      active: true,
    );
  }

  void goToIndex(int index) {
    final s = state;
    if (s == null || !s.active) return;
    if (index < 0 || index >= s.steps.length) return;
    state = s.copyWith(index: index);
  }

  void next() {
    final s = state;
    if (s == null || !s.active) return;
    if (s.isLast) return;
    state = s.copyWith(index: s.index + 1);
  }

  void previous() {
    final s = state;
    if (s == null || !s.active) return;
    if (s.index <= 0) return;
    state = s.copyWith(index: s.index - 1);
  }

  void skipCurrent() {
    final s = state;
    if (s == null || !s.active) return;
    if (s.isLast) return;
    state = s.copyWith(index: s.index + 1);
  }

  Future<void> dismissForever() async {
    final s = state;
    if (s == null) return;
    await OnboardingDismissStore.dismiss(
      tourId: s.tourId,
      version: s.version,
      uid: s.uid,
    );
    if (!ref.mounted) return;
    state = null;
  }

  Future<void> restart({
    required String tourId,
    required int version,
    required String uid,
    required List<OnboardingStep> steps,
  }) async {
    await OnboardingDismissStore.clear(
      tourId: tourId,
      version: version,
      uid: uid,
    );
    if (!ref.mounted) return;
    state = OnboardingTourState(
      tourId: tourId,
      version: version,
      uid: uid,
      steps: steps,
      index: 0,
      active: true,
    );
  }
}

final onboardingTourProvider =
    NotifierProvider<OnboardingTourNotifier, OnboardingTourState?>(
      OnboardingTourNotifier.new,
    );
