import '../presentation/onboarding_host.dart';
import 'student_onboarding_steps.dart';

class StudentOnboardingHost extends OnboardingHost {
  const StudentOnboardingHost({super.key, required super.child})
      : super(
          tourId: StudentOnboarding.tourId,
          version: StudentOnboarding.version,
          steps: StudentOnboarding.steps,
          rootRoutes: const {'/'},
        );
}
