import '../instructor/instructor_onboarding_steps.dart';
import 'onboarding_host.dart';

/// 강사 셸용 온보딩 호스트
class InstructorOnboardingHost extends OnboardingHost {
  const InstructorOnboardingHost({super.key, required super.child})
      : super(
          tourId: InstructorOnboarding.tourId,
          version: InstructorOnboarding.version,
          steps: InstructorOnboarding.steps,
          rootRoutes: const {'/instructor'},
        );
}
