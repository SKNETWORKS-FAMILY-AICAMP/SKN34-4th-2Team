import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../features/auth/providers/auth_providers.dart';
import '../../features/mileage/data/mileage_functions_service.dart';
import '../data/mileage_repository.dart';
import '../demo/demo_accounts.dart';
import '../demo/demo_mileage_repository.dart';
import '../models/domain_models.dart';
import '../models/mileage_models.dart';
import '../models/cohort_model.dart';
import '../providers/cohort_providers.dart';
import '../providers/firebase_providers.dart';
import 'package:cloud_functions/cloud_functions.dart';

final mileageRepositoryProvider = Provider<dynamic>((ref) {
  final uid = ref.watch(sessionUidProvider).value;
  if (DemoConfig.enabled && uid != null && DemoAccounts.isDemoUid(uid)) {
    return demoMileageRepository;
  }
  return MileageRepository(ref.watch(firestoreProvider));
});

final mileageFunctionsServiceProvider = Provider<MileageFunctionsService>((ref) {
  return MileageFunctionsService(
    FirebaseFunctions.instanceFor(region: 'asia-northeast3'),
  );
});

final mileageSettingsProvider =
    StreamProvider.autoDispose<MileageSettingsModel>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) {
    return Stream.value(MileageSettingsModel.defaults());
  }
  return ref.watch(mileageRepositoryProvider).watchMileageSettings(cohortId);
});

final mileageProductsProvider =
    StreamProvider.autoDispose<List<MileageProductModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref.watch(mileageRepositoryProvider).watchMileageProducts(cohortId);
});

final allMileageProductsProvider =
    StreamProvider.autoDispose<List<MileageProductModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref
      .watch(mileageRepositoryProvider)
      .watchAllMileageProducts(cohortId);
});

final mileageCartProvider =
    StreamProvider.autoDispose<MileageCartModel>((ref) {
  final user = ref.watch(currentUserSyncProvider);
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (user == null || cohortId == null) {
    return Stream.value(const MileageCartModel(userId: ''));
  }
  return ref
      .watch(mileageRepositoryProvider)
      .watchMileageCart(cohortId, user.uid);
});

final myPurchaseRequestsProvider =
    StreamProvider.autoDispose<List<PurchaseRequestModel>>((ref) {
  final user = ref.watch(currentUserSyncProvider);
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (user == null || cohortId == null) return Stream.value([]);
  return ref
      .watch(mileageRepositoryProvider)
      .watchMyPurchaseRequests(cohortId, user.uid);
});

final allPurchaseRequestsProvider =
    StreamProvider.autoDispose<List<PurchaseRequestModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref
      .watch(mileageRepositoryProvider)
      .watchAllPurchaseRequests(cohortId);
});

final mileageTransactionsProvider =
    StreamProvider.autoDispose<List<MileageTransactionModel>>((ref) {
  final user = ref.watch(currentUserSyncProvider);
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (user == null || cohortId == null) return Stream.value([]);
  return ref
      .watch(mileageRepositoryProvider)
      .watchMyMileageTransactions(cohortId, user.uid);
});

final mileageCategoryUsageProvider =
    FutureProvider.autoDispose<List<MileageCategoryUsageModel>>((ref) async {
  final user = ref.watch(currentUserSyncProvider);
  final cohortId = ref.watch(effectiveCohortIdProvider);
  final settings = ref.watch(mileageSettingsProvider).value ??
      MileageSettingsModel.defaults();
  if (user == null || cohortId == null) return [];
  // 구매 요청 변경 시 한도 재계산
  ref.watch(myPurchaseRequestsProvider);
  return ref.watch(mileageRepositoryProvider).computeCategoryUsage(
        cohortId: cohortId,
        userId: user.uid,
        settings: settings,
      );
});

final adminRecentMileageTransactionsProvider =
    StreamProvider.autoDispose<List<MileageTransactionModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value([]);
  return ref
      .watch(mileageRepositoryProvider)
      .watchRecentMileageTransactions(cohortId);
});

/// 마일리지 메인 탭 (0=내역, 1=구매요청)
final mileageMainTabProvider =
    NotifierProvider<MileageMainTabNotifier, int>(MileageMainTabNotifier.new);

class MileageMainTabNotifier extends Notifier<int> {
  @override
  int build() => 0;

  void select(int index) => state = index;

  void showRequests() => state = 1;
}

/// 기수 종강일
final effectiveCohortEndDateProvider = Provider<DateTime?>((ref) {
  return ref.watch(effectiveCohortDocProvider).value?.endDate;
});

final effectiveCohortDocProvider =
    StreamProvider.autoDispose<CohortModel?>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value(null);
  return ref
      .watch(firestoreProvider)
      .collection('cohorts')
      .doc(cohortId)
      .snapshots()
      .map((doc) => doc.exists ? CohortModel.fromFirestore(doc) : null);
});
