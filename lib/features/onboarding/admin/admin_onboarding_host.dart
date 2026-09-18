import '../presentation/onboarding_host.dart';
import 'admin_onboarding_steps.dart';

class AdminOnboardingHost extends OnboardingHost {
  const AdminOnboardingHost({super.key, required super.child})
      : super(
          tourId: AdminOnboarding.tourId,
          version: AdminOnboarding.version,
          steps: AdminOnboarding.steps,
          rootRoutes: const {'/admin'},
        );
}
