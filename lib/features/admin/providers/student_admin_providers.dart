import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/demo/demo_accounts.dart';
import '../../../shared/models/student_intake_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../data/student_admin_service.dart';

final cohortStudentIntakesProvider =
    StreamProvider.autoDispose<List<StudentIntakeModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null || DemoConfig.enabled) return Stream.value([]);
  return ref.watch(studentAdminServiceProvider).watchCohortIntakes(cohortId);
});

final studentIntakeDetailProvider = StreamProvider.autoDispose
    .family<StudentIntakeModel?, String>((ref, uid) {
  if (DemoConfig.enabled) return Stream.value(null);
  return ref.watch(studentAdminServiceProvider).watchIntake(uid);
});
