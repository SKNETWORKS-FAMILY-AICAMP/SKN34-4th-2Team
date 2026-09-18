import 'dart:async';

import '../../core/constants/mileage_constants.dart';
import '../models/domain_models.dart';
import '../models/mileage_models.dart';

/// Demo 모드용 Mileage Repository stub
class DemoMileageRepository {
  DemoMileageRepository() {
    _seed();
  }

  final _settingsController =
      StreamController<MileageSettingsModel>.broadcast();
  final _productsController =
      StreamController<List<MileageProductModel>>.broadcast();
  final _cartController = StreamController<MileageCartModel>.broadcast();
  final _requestsController =
      StreamController<List<PurchaseRequestModel>>.broadcast();
  final _txController =
      StreamController<List<MileageTransactionModel>>.broadcast();

  late MileageSettingsModel _settings;
  late List<MileageProductModel> _products;
  late MileageCartModel _cart;
  late List<PurchaseRequestModel> _requests;
  late List<MileageTransactionModel> _transactions;

  void _seed() {
    _settings = MileageSettingsModel.defaults();
    _products = [
      MileageProductModel(
        id: 'p1',
        name: '네이버페이 포인트 10,000원',
        category: MileageCategories.gifticon,
        pricingType: MileagePricingTypes.fixed,
        fixedPrice: 10000,
        sortOrder: 1,
      ),
      MileageProductModel(
        id: 'p2',
        name: '인프런 강의',
        category: MileageCategories.onlineCourse,
        pricingType: MileagePricingTypes.custom,
        sortOrder: 2,
      ),
      MileageProductModel(
        id: 'p3',
        name: 'yes24 도서',
        category: MileageCategories.book,
        pricingType: MileagePricingTypes.custom,
        sortOrder: 3,
      ),
    ];
    _cart = const MileageCartModel(userId: 'demo');
    _requests = [];
    _transactions = [];
    _emitAll();
  }

  void _emitAll() {
    _settingsController.add(_settings);
    _productsController.add(List.unmodifiable(_products));
    _cartController.add(_cart);
    _requestsController.add(List.unmodifiable(_requests));
    _txController.add(List.unmodifiable(_transactions));
  }

  Stream<MileageSettingsModel> watchMileageSettings(String cohortId) =>
      _startWith(_settings, _settingsController.stream);

  Future<void> saveMileageSettings(
    String cohortId,
    MileageSettingsModel settings, {
    required String updatedBy,
  }) async {
    _settings = settings;
    _settingsController.add(_settings);
  }

  Stream<List<MileageProductModel>> watchMileageProducts(String cohortId) =>
      _startWith(List<MileageProductModel>.unmodifiable(_products),
              _productsController.stream)
          .map((list) => list.where((p) => p.isActive).toList());

  Stream<List<MileageProductModel>> watchAllMileageProducts(String cohortId) =>
      _startWith(List.unmodifiable(_products), _productsController.stream);

  Future<String> saveMileageProduct({
    required String cohortId,
    required MileageProductModel product,
  }) async {
    final id = product.id.isNotEmpty ? product.id : 'p${_products.length + 1}';
    final saved = MileageProductModel(
      id: id,
      name: product.name,
      description: product.description,
      imageUrl: product.imageUrl,
      category: product.category,
      pricingType: product.pricingType,
      fixedPrice: product.fixedPrice,
      isActive: product.isActive,
      sortOrder: product.sortOrder,
    );
    final idx = _products.indexWhere((p) => p.id == id);
    if (idx >= 0) {
      _products[idx] = saved;
    } else {
      _products.add(saved);
    }
    _productsController.add(List.unmodifiable(_products));
    return id;
  }

  Future<void> deleteMileageProduct(String cohortId, String productId) async {
    _products.removeWhere((p) => p.id == productId);
    _productsController.add(List.unmodifiable(_products));
  }

  Stream<MileageCartModel> watchMileageCart(String cohortId, String userId) =>
      _startWith(_cart, _cartController.stream);

  Future<void> saveMileageCart({
    required String cohortId,
    required String userId,
    required List<MileageCartItemModel> items,
  }) async {
    _cart = MileageCartModel(userId: userId, items: items);
    _cartController.add(_cart);
  }

  Future<void> clearMileageCart(String cohortId, String userId) async {
    _cart = MileageCartModel(userId: userId);
    _cartController.add(_cart);
  }

  Stream<List<PurchaseRequestModel>> watchMyPurchaseRequests(
    String cohortId,
    String userId,
  ) =>
      _startWith(List.unmodifiable(_requests), _requestsController.stream);

  Stream<List<PurchaseRequestModel>> watchAllPurchaseRequests(String cohortId) =>
      _startWith(List.unmodifiable(_requests), _requestsController.stream);

  Stream<List<MileageTransactionModel>> watchMyMileageTransactions(
    String cohortId,
    String userId,
  ) =>
      _startWith(List.unmodifiable(_transactions), _txController.stream);

  Stream<List<MileageTransactionModel>> watchRecentMileageTransactions(
    String cohortId, {
    int limit = 30,
  }) =>
      _startWith(List.unmodifiable(_transactions), _txController.stream);

  Future<List<MileageCategoryUsageModel>> computeCategoryUsage({
    required String cohortId,
    required String userId,
    required MileageSettingsModel settings,
  }) async {
    return MileageCategories.all
        .map(
          (cat) => MileageCategoryUsageModel(
            category: cat,
            limit: settings.limitFor(cat),
            approved: 0,
            pending: 0,
            modifyRequested: 0,
          ),
        )
        .toList();
  }
}

/// broadcast 스트림은 구독 전에 보낸 값을 다시 주지 않는다. 화면이 늦게 구독해도
/// 로딩에 멈추지 않도록 현재 값을 앞에 붙인다.
Stream<T> _startWith<T>(T current, Stream<T> updates) async* {
  yield current;
  yield* updates;
}

final demoMileageRepository = DemoMileageRepository();
