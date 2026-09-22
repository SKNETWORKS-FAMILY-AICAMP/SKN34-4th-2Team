import '../../core/constants/mileage_constants.dart';
import '../../core/utils/date_utils.dart';
import '../models/domain_models.dart';
import '../models/mileage_models.dart';
import 'lms_api_client.dart';

class MileageRepository {
  MileageRepository(this._api);

  final LmsApiClient _api;

  Stream<T> _watch<T>(T Function() select) async* {
    if (_api.snapshot.isEmpty) {
      try {
        await _api.bootstrap();
      } catch (_) {}
    }
    yield select();
    await for (final _ in _api.changes) {
      yield select();
    }
  }

  List<Map<String, dynamic>> _forCohort(String key, String cohortId) =>
      _api.list(key).where((row) => '${row['cohortId']}' == cohortId).toList();

  Stream<MileageSettingsModel> watchMileageSettings(String cohortId) =>
      _watch(() {
        final row = _forCohort('mileageSettings', cohortId).firstOrNull;
        if (row == null) return MileageSettingsModel.defaults();
        return MileageSettingsModel(
          categoryLimits: Map<String, int>.from(
            (row['categoryLimits'] as Map? ?? {}).map(
              (key, value) => MapEntry('$key', (value as num?)?.toInt() ?? 0),
            ),
          ),
          accrualRules: Map<String, int>.from(
            (row['accrualRules'] as Map? ?? {}).map(
              (key, value) => MapEntry('$key', (value as num?)?.toInt() ?? 0),
            ),
          ),
          updatedAt: AppDateUtils.timestampToDateTime(row['updatedAt']),
          updatedBy: row['updatedBy']?.toString(),
        );
      });

  Future<void> saveMileageSettings(
    String cohortId,
    MileageSettingsModel settings, {
    required String updatedBy,
  }) =>
      _api.command('upsert', {'table': 'mileage_settings', 'action': 'update'});

  MileageProductModel _product(Map<String, dynamic> row) => MileageProductModel(
        id: '${row['id']}',
        name: row['name'] as String? ?? '',
        category: row['category'] as String? ?? '',
        pricingType: row['pricingType'] as String? ?? MileagePricingTypes.fixed,
        description: row['description'] as String? ?? '',
        imageUrl: row['imageUrl'] as String?,
        fixedPrice: (row['fixedPrice'] as num?)?.toInt(),
        isActive: row['isActive'] != false,
        sortOrder: (row['sortOrder'] as num?)?.toInt() ?? 0,
      );

  Stream<List<MileageProductModel>> watchMileageProducts(String cohortId) =>
      _watch(() => _forCohort('mileageProducts', cohortId)
          .map(_product)
          .where((p) => p.isActive)
          .toList());

  Stream<List<MileageProductModel>> watchAllMileageProducts(String cohortId) =>
      _watch(() => _forCohort('mileageProducts', cohortId).map(_product).toList());

  Future<String> saveMileageProduct({
    required String cohortId,
    required MileageProductModel product,
  }) =>
      _api.command('upsert', {
        'table': 'mileage_products',
        'action': product.id.isEmpty ? 'insert' : 'update',
        'id': product.id,
      }).then((value) => '${value['id'] ?? product.id}');

  Future<void> deleteMileageProduct(String cohortId, String productId) =>
      _api.command('upsert', {'table': 'mileage_products', 'id': productId, 'action': 'delete'});

  Stream<MileageCartModel> watchMileageCart(String cohortId, String userId) =>
      _watch(() {
        final items = _api
            .list('mileageCartItems')
            .map((row) => MileageCartItemModel.fromMap({
                  'productId': '${row['productId']}',
                  'productName': row['productName'] ?? '',
                  'category': row['category'] ?? '',
                  'pricingType': row['pricingType'] ?? MileagePricingTypes.fixed,
                  'unitPrice': row['unitPrice'] ?? row['unit_price'] ?? 0,
                  'quantity': row['quantity'] ?? 1,
                  'purchaseLink': row['purchaseLink'],
                }))
            .toList();
        return MileageCartModel(userId: userId, items: items);
      });

  Future<void> saveMileageCart({
    required String cohortId,
    required String userId,
    required List<MileageCartItemModel> items,
  }) =>
      _api.command('upsert', {'table': 'mileage_cart_items', 'action': 'insert'});

  Future<void> clearMileageCart(String cohortId, String userId) =>
      _api.command('upsert', {'table': 'mileage_cart_items', 'action': 'delete'});

  PurchaseRequestModel _request(Map<String, dynamic> row) => PurchaseRequestModel(
        id: '${row['id']}',
        userId: '${row['userId']}',
        userDisplayName: row['userDisplayName'] as String? ?? '',
        items: const [],
        totalAmount: (row['totalAmount'] as num?)?.toInt() ?? 0,
        status: row['status'] as String? ?? PurchaseRequestStatus.pending,
        createdAt: AppDateUtils.timestampToDateTime(row['createdAt']),
      );

  Stream<List<PurchaseRequestModel>> watchMyPurchaseRequests(
    String cohortId,
    String userId,
  ) =>
      _watch(() => _forCohort('purchaseRequests', cohortId)
          .where((row) => '${row['userId']}' == userId)
          .map(_request)
          .toList());

  Stream<List<PurchaseRequestModel>> watchAllPurchaseRequests(String cohortId) =>
      _watch(() => _forCohort('purchaseRequests', cohortId).map(_request).toList());

  MileageTransactionModel _tx(Map<String, dynamic> row) => MileageTransactionModel(
        id: '${row['id']}',
        userId: '${row['userId']}',
        amount: (row['amount'] as num?)?.toInt() ?? 0,
        reason: row['reason'] as String? ?? '',
        type: row['type'] as String?,
        createdAt: AppDateUtils.timestampToDateTime(row['createdAt']),
      );

  Stream<List<MileageTransactionModel>> watchMyMileageTransactions(
    String cohortId,
    String userId,
  ) =>
      _watch(() => _forCohort('mileageTransactions', cohortId)
          .where((row) => '${row['userId']}' == userId)
          .map(_tx)
          .toList());

  Stream<List<MileageTransactionModel>> watchRecentMileageTransactions(
    String cohortId, {
    int limit = 30,
  }) =>
      _watch(() => _forCohort('mileageTransactions', cohortId).map(_tx).take(limit).toList());

  Future<List<MileageCategoryUsageModel>> computeCategoryUsage({
    required String cohortId,
    required String userId,
    required MileageSettingsModel settings,
  }) async {
    final usage = <String, ({int approved, int pending, int modifyRequested})>{
      for (final c in MileageCategories.all)
        c: (approved: 0, pending: 0, modifyRequested: 0),
    };
    return MileageCategories.all
        .map(
          (cat) => MileageCategoryUsageModel(
            category: cat,
            limit: settings.limitFor(cat),
            approved: usage[cat]!.approved,
            pending: usage[cat]!.pending,
            modifyRequested: usage[cat]!.modifyRequested,
          ),
        )
        .toList();
  }
}
