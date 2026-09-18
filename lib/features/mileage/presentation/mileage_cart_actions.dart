import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/models/mileage_models.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/mileage_providers.dart';

/// 장바구니에 상품 추가
Future<void> addItemToMileageCart(
  WidgetRef ref, {
  required MileageCartItemModel item,
}) async {
  final user = ref.read(currentUserSyncProvider);
  final cohortId = ref.read(effectiveCohortIdProvider);
  if (user == null || cohortId == null) return;

  final cartAsync = ref.read(mileageCartProvider);
  final current = cartAsync.value ?? MileageCartModel(userId: user.uid);
  final items = [...current.items, item];

  await ref.read(mileageRepositoryProvider).saveMileageCart(
        cohortId: cohortId,
        userId: user.uid,
        items: items,
      );
}

MileageCategoryUsageModel? usageForCategory(
  List<MileageCategoryUsageModel>? usages,
  String category,
) {
  if (usages == null) return null;
  return usages.where((u) => u.category == category).firstOrNull;
}
