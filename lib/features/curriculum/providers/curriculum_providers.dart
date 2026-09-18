import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/demo/demo_accounts.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../data/curriculum_repository.dart';
import '../models/curriculum_meta_model.dart';

final curriculumMetaProvider =
    StreamProvider.autoDispose<CurriculumMetaModel?>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null || DemoConfig.enabled) return Stream.value(null);
  return ref.watch(curriculumRepositoryProvider).watchMeta(cohortId);
});

/// 특정 기수 메타 (관리자 기수 수정 화면용)
final curriculumMetaForCohortProvider = StreamProvider.autoDispose
    .family<CurriculumMetaModel?, String>((ref, cohortId) {
  if (DemoConfig.enabled) return Stream.value(null);
  return ref.watch(curriculumRepositoryProvider).watchMeta(cohortId);
});
