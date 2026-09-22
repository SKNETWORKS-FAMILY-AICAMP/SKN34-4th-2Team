import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../features/auth/providers/auth_providers.dart';
import '../demo/demo_accounts.dart';
import '../models/mission_models.dart';
import '../providers/cohort_providers.dart';
import '../providers/lms_providers.dart';

final missionProgressProvider =
    StreamProvider.autoDispose<MissionProgressModel>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  final uid = ref.watch(sessionUidProvider).value;
  if (cohortId == null || uid == null || DemoConfig.enabled) {
    return Stream.value(const MissionProgressModel());
  }
  return ref.watch(lmsRepositoryProvider).watchMissionProgress(cohortId, uid);
});

final missionGuidanceProvider =
    Provider.autoDispose<List<MissionGuidanceItem>>((ref) {
  final progress =
      ref.watch(missionProgressProvider).asData?.value ??
          const MissionProgressModel();
  return buildMissionGuidance(progress);
});
